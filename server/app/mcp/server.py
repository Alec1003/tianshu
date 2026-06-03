"""FastMCP server: TianShu scenario / units / AAR exposed over MCP.

Tools 设计原则（来自 api 技能 "AI tool calling API"）：
- 每个工具参数 schema 严格（Pydantic 模型/函数签名注解）；
- 写工具返回稳定 ``ToolError`` envelope；LLM 只能基于 ``code`` 做分支，
  不能解析 ``message``；
- 业务异常 (``ScenarioServiceError``) 一律收敛进 envelope，不直接 raise
  到 MCP 协议层（否则 LLM 只会看到 stack 报错，丢失结构化信息）；
- session 作用域 per-tool（pyd 反例 4 "全局复用 session"）。

Lifespan 注入：启动时通过 env (``TIANSHU_MCP_TOKEN`` 或 ``TIANSHU_MCP_USER_ID``)
解析 ``User``，注入到 ``Context.request_context.lifespan_context.user``，
后续所有 tool 调用都拿这个 user 走 service 层权限。
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from mcp.server.fastmcp import Context, FastMCP

from app.ai.command_governance import CommandApprovalQueue
from app.ai.command_service import save_command_proposal
from app.ai.skill_registry import TianShuSkillRegistry
from app.tianshu_runtime.persistence import ensure_runtime_state_loaded
from app.tianshu_runtime.timeline import record_runtime_event
from app.auth.models import User
from app.db.session import async_session_maker, create_db_and_tables
from app.mcp.auth import McpAuthError, resolve_user_from_env
from app.mcp.runtime_provider import create_runtime_async, run_in_runtime
from app.mcp.schemas import (
    AarRecordOut,
    ListUnitsResult,
    QueryThreatsResult,
    RuntimeOutcome,
    RuntimeSavedScenario,
    RuntimeSideStat,
    RuntimeStatus,
    ScenarioFull,
    ScenarioStatistics,
    ScenarioSummary,
    ThreatItem,
    ToolError,
    UnitBrief,
    UnitDetail,
)
from app.mcp.utils import (
    UNIT_TYPES,
    find_unit,
    get_current_scenario,
    get_side,
    get_sides,
    hostile_side_ids,
    iter_units,
    unit_brief,
)
from app.tianshu_runtime.runtime import TianShuRuntime
from app.scenarios import service as scenario_service
from app.scenarios.errors import ScenarioServiceError
from app.scenarios.models import Scenario


logger = logging.getLogger(__name__)


# ---------- lifespan ----------------------------------------------------------


# ----- Cross-mode injection points ------------------------------------------
# Two MCP transports share one tool surface:
#   - stdio  : user resolved once from ENV at lifespan; new TianShuRuntime
#              created per process (single-user scope).
#   - http   : runtime is resolved per request from FastAPI's per-user bridge
#              registry; user is resolved per-request from the Bearer token
#              via ``app.mcp.http_auth.BearerAuthASGI``.
#
# These module-level slots let the host (FastAPI app or stdio __main__) plug
# in the right pieces before MCP starts handling traffic, without forking
# the lifespan or the tool registry.
# ---------------------------------------------------------------------------

_shared_runtime: TianShuRuntime | None = None
_shared_runtime_provider: Callable[[User], TianShuRuntime] | None = None
_shared_bridge_provider: Callable[[User], Any] | None = None
_request_user_var: contextvars.ContextVar[User | None] = contextvars.ContextVar(
    "_tianshu_mcp_request_user", default=None
)


def set_shared_runtime(runtime: TianShuRuntime | None) -> None:
    """Bind a long-lived ``TianShuRuntime`` for HTTP transport.

    Must be called **before** ``mcp_lifespan`` enters (i.e. before the FastAPI
    lifespan hands control to ``session_manager.run()``); after that the
    binding is read-only for the life of the server.
    """
    global _shared_runtime
    _shared_runtime = runtime


def get_shared_runtime() -> TianShuRuntime | None:
    return _shared_runtime


def set_shared_runtime_provider(
    provider: Callable[[User], TianShuRuntime] | None,
) -> None:
    """Bind a per-user runtime provider for HTTP transport."""
    global _shared_runtime_provider
    _shared_runtime_provider = provider


def get_shared_runtime_provider() -> Callable[[User], TianShuRuntime] | None:
    return _shared_runtime_provider


def set_shared_bridge_provider(provider: Callable[[User], Any] | None) -> None:
    """Bind a per-user bridge provider so MCP writes can enter approvals."""
    global _shared_bridge_provider
    _shared_bridge_provider = provider


def get_shared_bridge_provider() -> Callable[[User], Any] | None:
    return _shared_bridge_provider


def set_request_user(user: User | None) -> contextvars.Token[User | None]:
    """HTTP middleware hook: per-request Bearer-resolved user goes here.

    Returns the contextvar token so the middleware can ``reset`` after the
    request finishes (avoids leaking a user identity across requests reusing
    the same task / event-loop slot).
    """
    return _request_user_var.set(user)


def reset_request_user(token: contextvars.Token[User | None]) -> None:
    _request_user_var.reset(token)


@dataclass
class McpAppContext:
    """Lifespan-scoped state injected into every tool/resource call.

    - ``user``: stdio mode -> resolved once at startup; http mode -> ``None``
      and tools should pull from ``_request_user_var`` instead
      (see ``_get_user``).
    - ``runtime``: shared with FastAPI in http mode, freshly created in
      stdio mode. Either way it persists across tool calls so AI can step
      the same game.
    """

    user: User | None
    runtime: TianShuRuntime | None
    command_approvals: CommandApprovalQueue | None = None


@asynccontextmanager
async def mcp_lifespan(server: FastMCP) -> AsyncIterator[McpAppContext]:  # noqa: ARG001
    # Ensure DB schema exists so Claude Desktop's first launch on a fresh
    # clone doesn't blow up with "no such table". Idempotent.
    await create_db_and_tables()

    shared_provider = get_shared_runtime_provider()
    shared = get_shared_runtime()
    command_approvals: CommandApprovalQueue | None = None
    if shared_provider is not None:
        runtime = None
        user = None
    elif shared is not None:
        # HTTP mode: the FastAPI host already owns the runtime + auth flow.
        # We deliberately skip ENV-based user resolution here -- requests
        # carry their own Bearer token, and lifespan-scoped user would just
        # be a confusing fallback that hides auth bugs.
        runtime = shared
        user: User | None = None
        logger.info(
            "mcp.lifespan: http mode; reusing shared runtime (scenario=%s, sides=%d)",
            runtime.game.current_scenario.name,
            len(runtime.game.current_scenario.sides),
        )
    else:
        # stdio mode (default): resolve a single user + boot a private runtime.
        async with async_session_maker() as session:
            user = await resolve_user_from_env(session)
        logger.info("mcp.lifespan: stdio mode; authenticated user=%s", user.email)
        runtime = await create_runtime_async()
        logger.info(
            "mcp.lifespan: runtime ready (scenario=%s, sides=%d)",
            runtime.game.current_scenario.name,
            len(runtime.game.current_scenario.sides),
        )
    if runtime is not None:
        command_approvals = CommandApprovalQueue(
            runtime=runtime,
            registry=TianShuSkillRegistry(runtime),
        )
    try:
        yield McpAppContext(
            user=user,
            runtime=runtime,
            command_approvals=command_approvals,
        )
    finally:
        # No explicit shutdown hook on TianShuRuntime; in stdio mode GC
        # reclaims it when the process exits, in HTTP mode the FastAPI host
        # owns its lifecycle.
        pass


mcp = FastMCP(
    name="天枢平台",
    lifespan=mcp_lifespan,
    json_response=True,
    # Streamable HTTP gets mounted under FastAPI's ``/api/mcp`` prefix; we
    # set the inner path to ``/`` so the final URL stays ``/api/mcp``
    # (default would have produced ``/api/mcp/mcp``).
    streamable_http_path="/",
    # Stateless mode: no server-side session tracking. Each request is handled
    # independently, so server restarts never invalidate client connections.
    stateless_http=True,
)


def _mcp_tool_description(description: str | None) -> str:
    if not description:
        return ""
    for line in description.splitlines():
        text = line.strip()
        if text:
            return text
    return ""


async def list_builtin_mcp_tool_definitions() -> list[dict[str, Any]]:
    """Return the real tool registry exposed by the built-in TianShu MCP."""
    tools = await mcp.list_tools()
    return [
        {
            "server": "TianShu MCP",
            "name": tool.name,
            "description": _mcp_tool_description(tool.description),
            "inputSchema": tool.inputSchema or {},
            "outputSchema": tool.outputSchema or {},
        }
        for tool in tools
    ]


# ---------- helpers -----------------------------------------------------------


class _UnauthenticatedError(Exception):
    """Raised when a tool requires a user but none is present.

    Tools convert this to a stable ``ToolError`` envelope (``code="unauthenticated"``)
    so LLMs can branch on the code without parsing English error text.
    """


def _get_user(ctx: Context) -> User:
    """Return the calling user.

    Resolution order:
    1. ``_request_user_var`` (set by HTTP Bearer middleware per request).
    2. ``McpAppContext.user`` from lifespan (stdio single-user mode).

    Raises ``_UnauthenticatedError`` if neither is set so tools can return a
    structured ``ToolError`` instead of a 500 stack.
    """
    request_user = _request_user_var.get()
    if request_user is not None:
        return request_user
    app_ctx: McpAppContext = ctx.request_context.lifespan_context
    if app_ctx.user is not None:
        return app_ctx.user
    raise _UnauthenticatedError(
        "no authenticated user; HTTP transport requires a valid Bearer token"
    )


def _get_runtime(ctx: Context) -> TianShuRuntime:
    provider = get_shared_runtime_provider()
    if provider is not None:
        return provider(_get_user(ctx))
    app_ctx: McpAppContext = ctx.request_context.lifespan_context
    if app_ctx.runtime is None:
        raise _UnauthenticatedError(
            "no runtime bound; HTTP transport requires a valid Bearer token"
        )
    return app_ctx.runtime


async def _get_runtime_loaded(ctx: Context) -> TianShuRuntime:
    user = _get_user(ctx)
    provider = get_shared_runtime_provider()
    if provider is not None:
        runtime = provider(user)
    else:
        app_ctx: McpAppContext = ctx.request_context.lifespan_context
        if app_ctx.runtime is None:
            raise _UnauthenticatedError(
                "no runtime bound; HTTP transport requires a valid Bearer token"
            )
        runtime = app_ctx.runtime
    async with async_session_maker() as session:
        await ensure_runtime_state_loaded(session, user, runtime)
    return runtime


def _get_bridge(ctx: Context) -> Any | None:
    provider = get_shared_bridge_provider()
    if provider is None:
        return None
    return provider(_get_user(ctx))


def _get_approval_queue(ctx: Context) -> CommandApprovalQueue:
    bridge = _get_bridge(ctx)
    if bridge is not None:
        queue = getattr(bridge, "command_approvals", None)
        if queue is not None:
            return queue
    app_ctx: McpAppContext = ctx.request_context.lifespan_context
    if app_ctx.command_approvals is not None:
        return app_ctx.command_approvals
    raise _UnauthenticatedError(
        "no command approval queue bound for this MCP transport"
    )


async def _create_runtime_proposal(
    ctx: Context,
    *,
    command: str,
    skill: str,
    parameters: dict[str, Any],
    source_text: str = "",
) -> dict[str, Any]:
    try:
        user = _get_user(ctx)
        queue = _get_approval_queue(ctx)
    except _UnauthenticatedError as exc:
        return ToolError(
            code="unauthenticated",
            message=str(exc),
        ).model_dump()

    runtime = getattr(queue, "runtime", None)
    if runtime is not None:
        async with async_session_maker() as session:
            await ensure_runtime_state_loaded(session, user, runtime)
    proposal = queue.create_single_step_proposal(
        command=command,
        skill=skill,
        parameters=parameters,
        source="mcp",
        source_text=source_text or command,
    )
    async with async_session_maker() as session:
        proposal = await save_command_proposal(session, user, proposal)
        await record_runtime_event(
            session,
            user,
            event_type="command.proposed",
            action="proposal_created",
            actor="mcp",
            summary=f"命令提案：{proposal.command}",
            payload=proposal.model_dump(mode="json"),
            runtime=runtime,
            proposal_id=proposal.id,
        )
    queue.hydrate(proposal)
    return {
        "ok": True,
        "action": "command_proposal_created",
        "state": {
            "proposalId": proposal.id,
            "proposalStatus": proposal.status,
            "requiresApproval": True,
        },
        "proposal": proposal.model_dump(mode="json"),
    }


def _err(exc: ScenarioServiceError) -> dict[str, Any]:
    return ToolError(
        code=exc.code,
        message=exc.message,
        retryable=exc.retryable,
        details=exc.details,
    ).model_dump()


def _scenario_summary(sc: Scenario) -> dict[str, Any]:
    return {
        "ok": True,
        **ScenarioSummary.model_validate(sc, from_attributes=True).model_dump(
            mode="json"
        ),
    }


def _scenario_full(sc: Scenario) -> dict[str, Any]:
    return {
        "ok": True,
        **ScenarioFull.model_validate(sc, from_attributes=True).model_dump(
            mode="json"
        ),
    }


# ---------- resources --------------------------------------------------------


@mcp.resource("tianshu://scenarios", name="scenarios-index")
async def resource_scenarios_index() -> str:
    """所有当前用户可见的想定（自己的 + 系统模板）的轻量列表。

    用作 LLM 启动对话时的"清单页"：模型读取后能立即列出所有可操作的
    想定 id 和名字，再决定调用 ``get_scenario`` 取详情。
    """
    ctx: Context = mcp.get_context()
    user = _get_user(ctx)
    async with async_session_maker() as session:
        rows = await scenario_service.list_scenarios(session, user, include_templates=True)
        items = [
            ScenarioSummary.model_validate(r, from_attributes=True).model_dump(mode="json")
            for r in rows
        ]
    return json.dumps({"scenarios": items}, ensure_ascii=False, indent=2)


@mcp.resource("tianshu://scenario/{scenario_id}", name="scenario-detail")
async def resource_scenario_detail(scenario_id: str) -> str:
    """单个想定的完整 JSON（含 ``data``）。"""
    ctx: Context = mcp.get_context()
    user = _get_user(ctx)
    async with async_session_maker() as session:
        try:
            sc = await scenario_service.get_scenario(session, user, scenario_id)
        except ScenarioServiceError as exc:
            return json.dumps(_err(exc), ensure_ascii=False, indent=2)
        payload = ScenarioFull.model_validate(sc, from_attributes=True).model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------- tools: read scenarios -------------------------------------------


@mcp.tool()
async def list_scenarios(
    ctx: Context,
    include_templates: bool = True,
) -> dict[str, Any]:
    """列出当前用户可访问的所有想定（自有 + 系统模板）。

    Args:
        include_templates: 是否包含系统模板。默认 True，前端我的想定页同款行为。

    Returns:
        ``{"ok": true, "scenarios": [ScenarioSummary, ...]}``。
    """
    user = _get_user(ctx)
    async with async_session_maker() as session:
        rows = await scenario_service.list_scenarios(
            session, user, include_templates=include_templates
        )
        items = [
            ScenarioSummary.model_validate(r, from_attributes=True).model_dump(mode="json")
            for r in rows
        ]
    return {"ok": True, "scenarios": items, "total": len(items)}


@mcp.tool()
async def get_scenario(ctx: Context, scenario_id: str) -> dict[str, Any]:
    """获取单个想定的完整数据（含整个 scenario JSON）。

    Args:
        scenario_id: 想定 ID。系统模板形如 ``tpl-blank_scenario``，
            用户想定形如 UUID。

    Returns:
        成功：``{"ok": true, ...ScenarioFull}``。
        失败：``ToolError`` envelope，``code`` ∈ {scenario_not_found, scenario_forbidden}。
    """
    user = _get_user(ctx)
    async with async_session_maker() as session:
        try:
            sc = await scenario_service.get_scenario(session, user, scenario_id)
        except ScenarioServiceError as exc:
            return _err(exc)
    return _scenario_full(sc)


@mcp.tool()
async def get_scenario_statistics(ctx: Context, scenario_id: str) -> dict[str, Any]:
    """获取想定的态势统计：side 列表 + 各类单位数量 + 任务数 + 时间窗口。

    比 ``get_scenario`` 轻量得多，适合 LLM "先看概况再决定怎么细看"。
    """
    user = _get_user(ctx)
    async with async_session_maker() as session:
        try:
            sc = await scenario_service.get_scenario(session, user, scenario_id)
        except ScenarioServiceError as exc:
            return _err(exc)
    inner = get_current_scenario(sc.data)
    counts = {
        ut: len(
            [u for u in iter_units(sc.data, types=(ut,))]  # noqa
        )
        for ut in UNIT_TYPES
    }
    missions = inner.get("missions", []) if isinstance(inner.get("missions"), list) else []
    stats = ScenarioStatistics(
        scenario_id=sc.id,
        name=sc.name,
        start_time=inner.get("startTime"),
        current_time=inner.get("currentTime"),
        duration=inner.get("duration"),
        sides=[
            {"id": s.get("id"), "name": s.get("name"), "color": s.get("color"),
             "total_score": s.get("totalScore", 0)}
            for s in get_sides(sc.data)
        ],
        counts=counts,
        mission_count=len(missions),
    )
    return {"ok": True, **stats.model_dump(mode="json")}


# ---------- tools: read units / threats ------------------------------------


@mcp.tool()
async def list_units(
    ctx: Context,
    scenario_id: str,
    side_id: str | None = None,
    unit_type: str | None = None,
) -> dict[str, Any]:
    """列出想定中的单位（可按阵营和类型过滤）。

    Args:
        scenario_id: 想定 ID。
        side_id: 阵营 ID。可选；不传则返回所有阵营单位。
        unit_type: 单位类型。可选；取值 ∈ aircraft / ship / facility / airbase / weapon / referencePoint / obstacle。

    Returns:
        ``{"ok": true, "scenario_id": "...", "total": N, "units": [UnitBrief, ...]}``。
    """
    user = _get_user(ctx)
    async with async_session_maker() as session:
        try:
            sc = await scenario_service.get_scenario(session, user, scenario_id)
        except ScenarioServiceError as exc:
            return _err(exc)

    types = None
    if unit_type:
        if unit_type not in UNIT_TYPES:
            return ToolError(
                code="scenario_invalid",
                message=f"unit_type must be one of {list(UNIT_TYPES)}",
                details={"unit_type": unit_type},
            ).model_dump()
        types = (unit_type,)  # type: ignore[assignment]

    rows = iter_units(sc.data, types=types)
    if side_id:
        rows = [u for u in rows if u.get("sideId") == side_id]
    briefs = [UnitBrief.model_validate(unit_brief(u)) for u in rows]
    return {
        "ok": True,
        **ListUnitsResult(
            scenario_id=sc.id,
            total=len(briefs),
            units=briefs,
        ).model_dump(mode="json"),
    }


@mcp.tool()
async def get_unit_detail(
    ctx: Context, scenario_id: str, unit_id: str
) -> dict[str, Any]:
    """获取单个单位的详情（含武器挂载和原始 JSON 透传）。"""
    user = _get_user(ctx)
    async with async_session_maker() as session:
        try:
            sc = await scenario_service.get_scenario(session, user, scenario_id)
        except ScenarioServiceError as exc:
            return _err(exc)

    unit = find_unit(sc.data, unit_id)
    if unit is None:
        return ToolError(
            code="unit_not_found",
            message=f"unit not found: {unit_id}",
            details={"scenario_id": scenario_id, "unit_id": unit_id},
        ).model_dump()
    weapons = unit.get("weapons", []) if isinstance(unit.get("weapons"), list) else []
    detail = UnitDetail(
        brief=UnitBrief.model_validate(unit_brief(unit)),
        weapons=[w for w in weapons if isinstance(w, dict)],
        raw={k: v for k, v in unit.items() if k != "weapons"},
    )
    return {"ok": True, **detail.model_dump(mode="json")}


@mcp.tool()
async def query_threats(
    ctx: Context, scenario_id: str, from_side_id: str
) -> dict[str, Any]:
    """从指定 side 视角列出敌对单位，按到最近己方单位的距离升序排序。

    距离用大圆公式（haversine）；没有己方单位时 distance_km 为 null。
    威胁定义复用 scenario.relationships.hostiles。
    """
    user = _get_user(ctx)
    async with async_session_maker() as session:
        try:
            sc = await scenario_service.get_scenario(session, user, scenario_id)
        except ScenarioServiceError as exc:
            return _err(exc)

    side = get_side(sc.data, from_side_id)
    if side is None:
        return ToolError(
            code="side_not_found",
            message=f"side not found: {from_side_id}",
            details={"scenario_id": scenario_id, "side_id": from_side_id},
        ).model_dump()

    hostile_ids = hostile_side_ids(sc.data, from_side_id)
    all_units = iter_units(sc.data)
    own_units = [u for u in all_units if u.get("sideId") == from_side_id]
    threats = [u for u in all_units if u.get("sideId") in hostile_ids]

    items: list[ThreatItem] = []
    for t in threats:
        dist = _nearest_distance_km(t, own_units)
        items.append(
            ThreatItem(
                unit=UnitBrief.model_validate(unit_brief(t)),
                distance_km=dist,
            )
        )
    # Sort by distance asc, None last.
    items.sort(key=lambda x: (x.distance_km is None, x.distance_km or 0.0))

    return {
        "ok": True,
        **QueryThreatsResult(
            scenario_id=sc.id,
            from_side_id=from_side_id,
            total=len(items),
            threats=items,
        ).model_dump(mode="json"),
    }


# ---------- tools: write scenarios ------------------------------------------


@mcp.tool()
async def create_scenario(
    ctx: Context,
    name: str,
    data: dict[str, Any],
    description: str = "",
    status: str = "draft",
) -> dict[str, Any]:
    """创建一个新的（用户拥有的）想定。

    Args:
        name: 想定名称（1..120 字符）。
        data: 完整想定 JSON。必须是对象；可以包含 ``currentScenario`` 包装
            或直接是 scenario body，与前端导出格式一致即可。
        description: 备注（最多 2000 字符）。
        status: 初始状态。非法值会被改回 ``draft``，绝不允许 LLM 写入垃圾状态。

    Returns:
        成功：``{"ok": true, ...ScenarioFull}``；
        失败：``ToolError`` envelope（``code = scenario_invalid``）。
    """
    user = _get_user(ctx)
    async with async_session_maker() as session:
        try:
            sc = await scenario_service.create_scenario(
                session,
                user,
                name=name,
                description=description,
                data=data,
                status=status,
            )
        except ScenarioServiceError as exc:
            return _err(exc)
    await ctx.info(f"created scenario {sc.id} ({sc.name!r})")
    return _scenario_full(sc)


@mcp.tool()
async def update_scenario_meta(
    ctx: Context,
    scenario_id: str,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """更新想定的元信息（不动 ``data``）。

    系统模板默认只允许 superuser 编辑；普通用户应用 ``create_scenario``
    复制出自己的副本。
    """
    user = _get_user(ctx)
    async with async_session_maker() as session:
        try:
            sc = await scenario_service.update_scenario(
                session,
                user,
                scenario_id,
                name=name,
                description=description,
                status=status,
            )
        except ScenarioServiceError as exc:
            return _err(exc)
    return _scenario_summary(sc)


@mcp.tool()
async def update_scenario_data(
    ctx: Context,
    scenario_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """整体替换想定的 ``data``，version 自动 +1。

    使用场景：LLM 修改了 sides / units / missions / relationships 后整体
    回写。注意这是**整体替换**，不是 patch。若只想动单位位置等小字段，
    后续切片会出更细的 ``set_unit_position`` 类工具。
    """
    user = _get_user(ctx)
    async with async_session_maker() as session:
        try:
            sc = await scenario_service.update_scenario(
                session, user, scenario_id, data=data
            )
        except ScenarioServiceError as exc:
            return _err(exc)
    await ctx.info(f"updated scenario.data {sc.id} (version={sc.version})")
    return _scenario_full(sc)


@mcp.tool()
async def delete_scenario(ctx: Context, scenario_id: str) -> dict[str, Any]:
    """删除一个用户拥有的想定。系统模板不可删除。"""
    user = _get_user(ctx)
    async with async_session_maker() as session:
        try:
            await scenario_service.delete_scenario(session, user, scenario_id)
        except ScenarioServiceError as exc:
            return _err(exc)
    await ctx.info(f"deleted scenario {scenario_id}")
    return {"ok": True, "deleted_id": scenario_id}


# ---------- tools: AAR ------------------------------------------------------


@mcp.tool()
async def list_aar_records(
    ctx: Context, scenario_id: str, limit: int = 20
) -> dict[str, Any]:
    """列出某想定的 AAR（After-Action-Review）记录，按时间倒序。"""
    user = _get_user(ctx)
    async with async_session_maker() as session:
        try:
            rows = await scenario_service.list_aar_records(
                session, user, scenario_id, limit=limit
            )
        except ScenarioServiceError as exc:
            return _err(exc)
        items = [
            AarRecordOut.model_validate(r, from_attributes=True).model_dump(mode="json")
            for r in rows
        ]
    return {"ok": True, "scenario_id": scenario_id, "total": len(items), "records": items}


@mcp.tool()
async def post_aar_record(
    ctx: Context,
    scenario_id: str,
    outcome_reason: str,
    summary: dict[str, Any],
    ended_at: datetime,
    winner_side_id: str = "",
) -> dict[str, Any]:
    """追加一条 AAR 记录。``scenario_id`` 是相关性 tag，可指向未持久化的临时想定。"""
    user = _get_user(ctx)
    async with async_session_maker() as session:
        try:
            rec = await scenario_service.create_aar_record(
                session,
                user,
                scenario_id,
                outcome_reason=outcome_reason,
                winner_side_id=winner_side_id,
                summary=summary,
                ended_at=ended_at,
            )
        except ScenarioServiceError as exc:
            return _err(exc)
    return {
        "ok": True,
        **AarRecordOut.model_validate(rec, from_attributes=True).model_dump(mode="json"),
    }


# ---------- geo helper -----------------------------------------------------


def _nearest_distance_km(
    unit: dict[str, Any], references: list[dict[str, Any]]
) -> float | None:
    """Great-circle distance (km) to the closest reference unit. None if no ref."""
    if not references:
        return None
    try:
        lat1 = float(unit["latitude"])
        lon1 = float(unit["longitude"])
    except (KeyError, TypeError, ValueError):
        return None

    import math

    def _haversine(la1: float, lo1: float, la2: float, lo2: float) -> float:
        r = 6371.0088
        p1, p2 = math.radians(la1), math.radians(la2)
        dp = math.radians(la2 - la1)
        dl = math.radians(lo2 - lo1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(math.sqrt(a))

    best: float | None = None
    for ref in references:
        try:
            la2 = float(ref["latitude"])
            lo2 = float(ref["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        d = _haversine(lat1, lon1, la2, lo2)
        if best is None or d < best:
            best = d
    return best


# ===========================================================================
# Runtime tools: live scenario driven by authoritative TianShuRuntime.
# Note: the per-user live runtime now restores from/saves to ``runtime_state``;
# ``runtime_save_to_db`` still creates a separate static Scenario row.
#
# 边界（重要，给 LLM 看也给运维看）：
# - "Runtime" 是 stdio 进程内一个 TianShuRuntime 实例，跑的是活想定；
#   这一组工具改变的状态**不会自动写回 DB**。
# - "DB scenarios" 是 ``Scenario`` 表，是用户保存的静态快照。
#   要把当前 runtime 状态持久化，必须显式调用 ``runtime_save_to_db``。
# - 想把一个 DB 想定接管进 runtime 继续推演，调 ``runtime_load_scenario_from_db``。
# ===========================================================================


_RUNTIME_UNIT_FIELDS: tuple[tuple[str, str], ...] = (
    # (Python attr name on Scenario, MCP-facing key)
    ("aircraft", "aircraft"),
    ("ships", "ship"),
    ("facilities", "facility"),
    ("airbases", "airbase"),
    ("weapons", "weapon"),
    ("reference_points", "referencePoint"),
    ("obstacles", "obstacle"),
)


def _runtime_unit_counts(runtime: TianShuRuntime) -> dict[str, int]:
    scenario = runtime.game.current_scenario
    counts: dict[str, int] = {}
    for attr, key in _RUNTIME_UNIT_FIELDS:
        bucket = getattr(scenario, attr, None) or []
        counts[key] = len(bucket)
    return counts


def _runtime_side_stats(runtime: TianShuRuntime) -> list[RuntimeSideStat]:
    out: list[RuntimeSideStat] = []
    for s in runtime.game.current_scenario.sides:
        color = getattr(s.color, "value", s.color)
        out.append(
            RuntimeSideStat(
                id=s.id,
                name=s.name,
                color=str(color) if color is not None else None,
                total_score=float(getattr(s, "total_score", 0) or 0),
            )
        )
    return out


def _runtime_status_payload(runtime: TianShuRuntime) -> dict[str, Any]:
    scenario = runtime.game.current_scenario
    start = int(scenario.start_time or 0)
    duration = int(scenario.duration or 0)
    current = int(scenario.current_time or start)
    elapsed = max(0, current - start)
    duration_left = max(0, start + duration - current)
    status = RuntimeStatus(
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        paused=bool(getattr(runtime.game, "scenario_paused", True)),
        start_time=start,
        current_time=current,
        duration=duration,
        elapsed=elapsed,
        duration_left=duration_left,
        counts=_runtime_unit_counts(runtime),
        sides=_runtime_side_stats(runtime),
    )
    return status.model_dump(mode="json")


@mcp.resource("tianshu://runtime", name="runtime-status")
async def resource_runtime_status() -> str:
    """正在跑的内存活想定的实时快照。

    与 ``tianshu://scenarios`` / ``tianshu://scenario/{id}`` 不同源 —— 那两个读
    DB 静态行，这个读 runtime 内存态。AI 在做推演决策时应该读这个。
    """
    ctx: Context = mcp.get_context()
    runtime = await _get_runtime_loaded(ctx)
    payload = _runtime_status_payload(runtime)
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------- runtime: lifecycle + status -------------------------------------


@mcp.tool()
async def runtime_status(ctx: Context) -> dict[str, Any]:
    """正在跑的活想定的态势概览（时间窗、暂停状态、单位计数、阵营）。

    与 DB 中静态的 ``get_scenario`` 不同源；要读 AI 当前正在操控的想定，
    必须用这个工具。
    """
    runtime = await _get_runtime_loaded(ctx)
    return _runtime_status_payload(runtime)


@mcp.tool()
async def runtime_start(ctx: Context) -> dict[str, Any]:
    """启动/继续推演（取消暂停）。"""
    return await _create_runtime_proposal(
        ctx,
        command="MCP runtime_start",
        skill="simulation_start",
        parameters={},
    )


@mcp.tool()
async def runtime_pause(ctx: Context) -> dict[str, Any]:
    """暂停推演（仿真时间停滞，单位指令仍可下达）。"""
    return await _create_runtime_proposal(
        ctx,
        command="MCP runtime_pause",
        skill="simulation_pause",
        parameters={},
    )


@mcp.tool()
async def runtime_reset(ctx: Context) -> dict[str, Any]:
    """重置推演状态（回到当前 scenario 的初始时刻）。"""
    return await _create_runtime_proposal(
        ctx,
        command="MCP runtime_reset",
        skill="simulation_reset",
        parameters={},
    )


@mcp.tool()
async def runtime_step(ctx: Context, steps: int = 1) -> dict[str, Any]:
    """推进 N 个仿真步（每步 = 1 仿真秒，包含交战 / 探测 / 单位运动）。

    建议批量推进（``steps=30``～``300``）减少 tool-call 往返开销；推完后
    再用 ``runtime_status`` / ``runtime_get_outcome`` / ``runtime_query_threats``
    观察结果。
    """
    if steps < 1:
        return ToolError(
            code="runtime_invalid",
            message="steps must be >= 1",
            details={"steps": steps},
        ).model_dump()
    if steps > 7200:
        # 7200 步 = 2 小时仿真，单次 tool 调用不该再大；超过应分多次。
        return ToolError(
            code="runtime_invalid",
            message="steps too large; split into multiple calls (max 7200 per call)",
            details={"steps": steps, "max": 7200},
        ).model_dump()
    return await _create_runtime_proposal(
        ctx,
        command=f"MCP runtime_step steps={steps}",
        skill="simulation_step",
        parameters={"steps": steps},
    )


# ---------- runtime: scenario load / save bridging --------------------------


@mcp.tool()
async def runtime_load_scenario_from_db(
    ctx: Context, scenario_id: str
) -> dict[str, Any]:
    """把 DB 中的某个 scenario 加载进 runtime，**会覆盖当前活想定**。

    工作流：
    1. 走 service 层取 DB 行（权限校验：own / template）；
    2. 调 runtime.load_scenario_from_json 进内存；
    3. 返回新 runtime 的 status。

    Args:
        scenario_id: DB scenario 的 ID（模板形如 ``tpl-SCS``，用户行 UUID）。
    """
    user = _get_user(ctx)
    async with async_session_maker() as session:
        try:
            sc = await scenario_service.get_scenario(session, user, scenario_id)
        except ScenarioServiceError as exc:
            return _err(exc)
    scenario_json = json.dumps(sc.data, ensure_ascii=False)
    return await _create_runtime_proposal(
        ctx,
        command=f"MCP runtime_load_scenario_from_db scenario_id={sc.id}",
        skill="load_scenario_snapshot",
        parameters={
            "scenario_json": scenario_json,
            "scenario_id": sc.id,
            "name": sc.name,
        },
    )


@mcp.tool()
async def runtime_export_scenario(ctx: Context) -> dict[str, Any]:
    """导出当前 runtime 活想定为 frontend-shaped JSON（不写 DB）。

    返回的 ``data`` 字段结构跟 ``Scenario.data`` 一致；如需持久化，紧接
    着用 ``runtime_save_to_db`` 把它当新 scenario 行写入。
    """
    runtime = await _get_runtime_loaded(ctx)
    exported = await run_in_runtime(runtime.get_exported_scenario)
    return {"ok": True, "data": exported}


@mcp.tool()
async def runtime_save_to_db(
    ctx: Context,
    name: str,
    description: str = "",
    status: str = "running",
) -> dict[str, Any]:
    """把当前 runtime 活想定 export 后**新建**一行 DB scenario 保存下来。

    P0 阶段总是 create-new（不覆盖原行），避免误改模板；想覆盖请显式
    走 ``update_scenario_data``。

    Args:
        name: 新 scenario 的名称。
        description: 备注。
        status: ``draft`` / ``running`` / ``completed`` 之一，默认 running。
    """
    user = _get_user(ctx)
    runtime = await _get_runtime_loaded(ctx)
    exported = await run_in_runtime(runtime.get_exported_scenario)
    async with async_session_maker() as session:
        try:
            sc = await scenario_service.create_scenario(
                session,
                user,
                name=name,
                description=description,
                data=exported,
                status=status,
            )
        except ScenarioServiceError as exc:
            return _err(exc)
    await ctx.info(f"runtime: saved as scenario {sc.id} ({sc.name!r})")
    return RuntimeSavedScenario(
        saved_scenario_id=sc.id,
        name=sc.name,
        version=sc.version,
        current_time=int(runtime.game.current_scenario.current_time or 0),
    ).model_dump(mode="json")


# ---------- runtime: deploy units -------------------------------------------


@mcp.tool()
async def runtime_deploy_aircraft(
    ctx: Context,
    class_name: str,
    latitude: float,
    longitude: float,
    side: str | None = None,
    name: str | None = None,
    altitude: float = 10000.0,
) -> dict[str, Any]:
    """在活想定中部署一架飞机。``side`` 可传 side_id 或 side 名（如 "RED"）。

    ``class_name`` 必须命中后端 AircraftDb（默认未命中会回落到首行）；建
    议先用 DB 工具读 SCS 模板看可选机型，再传入这里。
    """
    return await _create_runtime_proposal(
        ctx,
        command=f"MCP runtime_deploy_aircraft class_name={class_name}",
        skill="deploy_aircraft",
        parameters={
            "class_name": class_name,
            "latitude": latitude,
            "longitude": longitude,
            "side": side,
            "name": name,
            "altitude": altitude,
        },
    )


@mcp.tool()
async def runtime_deploy_ship(
    ctx: Context,
    class_name: str,
    latitude: float,
    longitude: float,
    side: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """在活想定中部署一艘舰艇。"""
    return await _create_runtime_proposal(
        ctx,
        command=f"MCP runtime_deploy_ship class_name={class_name}",
        skill="deploy_ship",
        parameters={
            "class_name": class_name,
            "latitude": latitude,
            "longitude": longitude,
            "side": side,
            "name": name,
        },
    )


@mcp.tool()
async def runtime_deploy_facility(
    ctx: Context,
    class_name: str,
    latitude: float,
    longitude: float,
    side: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """在活想定中部署一处地面设施（防空 / 雷达 / 指挥所等）。"""
    return await _create_runtime_proposal(
        ctx,
        command=f"MCP runtime_deploy_facility class_name={class_name}",
        skill="deploy_facility",
        parameters={
            "class_name": class_name,
            "latitude": latitude,
            "longitude": longitude,
            "side": side,
            "name": name,
        },
    )


@mcp.tool()
async def runtime_deploy_airbase(
    ctx: Context,
    class_name: str,
    latitude: float,
    longitude: float,
    side: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """在活想定中部署一座机场（aircraft 的 homeBase）。"""
    return await _create_runtime_proposal(
        ctx,
        command=f"MCP runtime_deploy_airbase class_name={class_name}",
        skill="deploy_airbase",
        parameters={
            "class_name": class_name,
            "latitude": latitude,
            "longitude": longitude,
            "side": side,
            "name": name,
        },
    )


@mcp.tool()
async def runtime_deploy_obstacle(
    ctx: Context,
    class_name: str,
    latitude: float,
    longitude: float,
    side: str | None = None,
    name: str | None = None,
    radius_nm: float = 15.0,
    obstacle_type: str = "no_go",
    movement_penalty: float = 1.0,
    detection_penalty: float = 0.0,
    communication_penalty: float = 0.0,
    affected_domains: list[str] | None = None,
) -> dict[str, Any]:
    """在活想定中部署环境障碍/约束区。

    障碍物不是火力单位，只作为仿真世界约束：禁行区会阻断机动，
    地形/天气会降低机动速度，雷达遮蔽/天气/地形会降低探测距离。
    """
    return await _create_runtime_proposal(
        ctx,
        command=f"MCP runtime_deploy_obstacle class_name={class_name}",
        skill="deploy_obstacle",
        parameters={
            "class_name": class_name,
            "latitude": latitude,
            "longitude": longitude,
            "side": side,
            "name": name,
            "radius_nm": radius_nm,
            "obstacle_type": obstacle_type,
            "movement_penalty": movement_penalty,
            "detection_penalty": detection_penalty,
            "communication_penalty": communication_penalty,
            "affected_domains": affected_domains,
        },
    )


# ---------- runtime: unit control -------------------------------------------


@mcp.tool()
async def runtime_move_unit(
    ctx: Context,
    unit_type: str,
    unit_id: str,
    route: list[list[float]],
) -> dict[str, Any]:
    """给一个 aircraft / ship 设定多段航点 route。

    Args:
        unit_type: ``aircraft`` 或 ``ship``（facility / airbase 不可移动）。
        unit_id: 目标单位 ID。
        route: 经纬度航点序列，每个点是 ``[latitude, longitude]``；至少一段。

    后续推演会让单位按 route 顺序前进；新调用会**替换**当前未走完的航点。
    """
    if unit_type not in ("aircraft", "ship"):
        return ToolError(
            code="runtime_invalid",
            message="unit_type must be 'aircraft' or 'ship'",
            details={"unit_type": unit_type},
        ).model_dump()
    if not isinstance(route, list) or not route:
        return ToolError(
            code="runtime_invalid",
            message="route must be a non-empty list of [lat, lon] pairs",
            details={},
        ).model_dump()
    return await _create_runtime_proposal(
        ctx,
        command=f"MCP runtime_move_unit unit_type={unit_type} unit_id={unit_id}",
        skill="move_unit",
        parameters={"unit_type": unit_type, "unit_id": unit_id, "route": route},
    )


@mcp.tool()
async def runtime_delete_unit(
    ctx: Context, unit_type: str, unit_id: str
) -> dict[str, Any]:
    """从活想定中移除一个单位（aircraft / ship / facility / airbase /
    reference_point / obstacle）。"""
    return await _create_runtime_proposal(
        ctx,
        command=f"MCP runtime_delete_unit unit_type={unit_type} unit_id={unit_id}",
        skill="delete_unit",
        parameters={"unit_type": unit_type, "unit_id": unit_id},
    )


# ---------- runtime: tactical events ----------------------------------------


@mcp.tool()
async def runtime_set_relationship(
    ctx: Context,
    side: str,
    hostiles: list[str],
    allies: list[str] | None = None,
) -> dict[str, Any]:
    """重设某 side 视角的敌我关系（覆盖式，非增量）。

    Args:
        side: side_id 或 side 名。
        hostiles: 敌对方 side_id 列表。
        allies: 友方 side_id 列表，可省略（默认空）。
    """
    payload = {
        "side": side,
        "hostiles": hostiles,
        "allies": allies or [],
    }
    return await _create_runtime_proposal(
        ctx,
        command=f"MCP runtime_set_relationship side={side}",
        skill="trigger_tactical_event",
        parameters={"event_name": "set_relationship", "payload": payload},
    )


@mcp.tool()
async def runtime_set_current_side(ctx: Context, side: str) -> dict[str, Any]:
    """切换 runtime 当前激活的 side。

    很多 deploy_* / move_* 内部会用 ``current_side_id`` 作为兜底，AI 在
    扮演双方时必须显式切换，避免单位落到错的阵营。
    """
    return await _create_runtime_proposal(
        ctx,
        command=f"MCP runtime_set_current_side side={side}",
        skill="trigger_tactical_event",
        parameters={"event_name": "set_current_side", "payload": {"side": side}},
    )


# ---------- runtime: outcome ------------------------------------------------


def _runtime_outcome_payload(runtime: TianShuRuntime) -> dict[str, Any]:
    """Return authoritative runtime outcome plus survival signals."""
    scenario = runtime.game.current_scenario
    start = int(scenario.start_time or 0)
    duration = int(scenario.duration or 0)
    current = int(scenario.current_time or start)
    duration_left = max(0, start + duration - current)
    time_up = duration > 0 and current >= start + duration
    raw_outcome = getattr(runtime.game, "game_outcome", {}) or {}
    ended = bool(raw_outcome.get("ended", False))
    winner_side_id = (
        raw_outcome.get("winner_side_id") or raw_outcome.get("winnerSideId") or None
    )
    reason = raw_outcome.get("reason", "") or ""
    ended_at = int(raw_outcome.get("ended_at") or raw_outcome.get("endedAt") or 0)
    objective_destroyed = getattr(scenario, "last_objective_destroyed", None)

    # Per-side surviving unit counts (exclude reference points: they're
    # navigational, not combat assets).
    sides = list(scenario.sides)
    surviving: list[str] = []
    annihilated: list[str] = []
    combat_attrs = ("aircraft", "ships", "facilities", "airbases", "weapons")
    for side in sides:
        side_id = side.id
        alive = 0
        for attr in combat_attrs:
            bucket = getattr(scenario, attr, None) or []
            alive += sum(1 for u in bucket if getattr(u, "side_id", None) == side_id)
        (surviving if alive > 0 else annihilated).append(side_id)

    return RuntimeOutcome(
        ended=ended,
        winner_side_id=winner_side_id if ended else None,
        reason=reason,
        ended_at=ended_at,
        objective_destroyed=objective_destroyed,
        time_up=time_up,
        annihilated_side_ids=annihilated,
        surviving_side_ids=surviving,
        inferred_winner_side_id=winner_side_id if ended else None,
        current_time=current,
        duration_left=duration_left,
    ).model_dump(mode="json")


@mcp.tool()
async def runtime_get_outcome(ctx: Context) -> dict[str, Any]:
    """读取当前推演的胜负信号。

    返回后端仿真引擎的权威 ``ended`` / ``winner_side_id`` / ``reason``，
    同时保留 ``time_up``、各方存活和全灭状态作为辅助态势信号。
    """
    runtime = await _get_runtime_loaded(ctx)
    return _runtime_outcome_payload(runtime)


__all__ = ["mcp"]
