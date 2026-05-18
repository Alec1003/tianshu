// AICC COMMAND -- Tactical Identity Terminal (Login + Register)
// =============================================================================
// 设计目标：把入口页从「企业 SaaS 登录页」升级为「下一代 AI 指挥控制平台入口」。
// 参考语言：Anduril Lattice / Palantir Gotham / Cursor / Windsurf 暗色科技风格。
//
// 布局：
//   - lg+ : grid 55% / 45%  左侧战场态势展示 / 右侧 Tactical Identity Terminal
//   - 移动端：单列堆叠
//
// 视觉：
//   - 背景多层：tactical grid + 扫描带 + 雷达波纹 + 稀疏数据粒子
//   - 玻璃拟态登录面板，多层 glow + 内 HUD 输入
//   - 左侧大型 SVG 雷达 + 航线 + AI 节点 + 战术地图轮廓
//
// 技术：React + TS + Tailwind + framer-motion + lucide-react
// =============================================================================

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Link as RouterLink,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  Activity,
  ArrowRight,
  Brain,
  ChevronRight,
  Crosshair,
  Eye,
  EyeOff,
  Fingerprint,
  Globe2,
  Hexagon,
  KeyRound,
  Layers3,
  Lock,
  Network,
  Radar,
  Radio,
  Satellite,
  ShieldCheck,
  Sparkles,
  Target,
  Terminal,
  UserCog,
  Zap,
} from "lucide-react";

import { ApiError } from "@/api/client";
import { cn } from "@/lib/utils";
import { useAuth } from "./AuthContext";

// -----------------------------------------------------------------------------
// 配置数据：左侧 AI 能力卡片 + 战术状态行
// -----------------------------------------------------------------------------

const CAPABILITIES: Array<{
  icon: typeof Radar;
  code: string;
  title: string;
  desc: string;
  metric: string;
}> = [
  {
    icon: Radar,
    code: "C-01",
    title: "实时态势感知",
    desc: "多源传感器融合,战场全域目标跟踪与威胁评估",
    metric: "1,284 TGT",
  },
  {
    icon: Brain,
    code: "C-02",
    title: "AI 智能推演",
    desc: "基于强化学习的对抗推演,毫秒级战术建议",
    metric: "98.3% ACC",
  },
  {
    icon: Network,
    code: "C-03",
    title: "多域协同作战",
    desc: "陆海空天电统一指挥,跨域力量自适应编组",
    metric: "5 DOMAINS",
  },
  {
    icon: Crosshair,
    code: "C-04",
    title: "自动战术规划",
    desc: "目标分配 / 路径规划 / 火力优化端到端自动化",
    metric: "< 240 ms",
  },
];

const STATUS_BAR: Array<{
  icon: typeof Activity;
  label: string;
  value: string;
  tone: "ok" | "warn" | "neutral";
}> = [
  { icon: ShieldCheck, label: "DEFCON", value: "LEVEL 3", tone: "ok" },
  { icon: Activity, label: "AI LATENCY", value: "186 ms", tone: "ok" },
  { icon: Radio, label: "LINK", value: "16 / 16", tone: "ok" },
  { icon: Satellite, label: "SATCOM", value: "NOMINAL", tone: "ok" },
];

// -----------------------------------------------------------------------------
// 主组件
// -----------------------------------------------------------------------------

type Tab = "login" | "register";
type LocationState = { from?: { pathname?: string } } | null;

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, register } = useAuth();
  const reduceMotion = useReducedMotion();

  const initialTab: Tab = location.pathname === "/register" ? "register" : "login";
  const [tab, setTab] = useState<Tab>(initialTab);
  useEffect(() => {
    setTab(location.pathname === "/register" ? "register" : "login");
  }, [location.pathname]);

  // 表单状态
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [password2, setPassword2] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    setInfo(null);
  }, [tab]);

  const postLoginTarget = useMemo(() => {
    const state = location.state as LocationState;
    return state?.from?.pathname ?? "/scenarios";
  }, [location.state]);

  // 任务时钟（顶部 ID 行展示）
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    if (reduceMotion) return;
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, [reduceMotion]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setInfo(null);
    if (tab === "register") {
      if (password.length < 8) {
        setError("访问密钥至少 8 位");
        return;
      }
      if (password !== password2) {
        setError("两次输入的访问密钥不一致");
        return;
      }
    }
    setSubmitting(true);
    try {
      if (tab === "login") {
        await login(email.trim(), password);
      } else {
        await register(email.trim(), password, displayName.trim());
      }
      navigate(postLoginTarget, { replace: true });
    } catch (err) {
      setError(humanizeError(err, tab));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="dark relative h-screen w-screen overflow-hidden bg-[#03070f] text-slate-100">
      <TacticalBackground reduce={reduceMotion ?? false} />

      {/* 顶部薄帧：模拟 HUD chrome */}
      <header className="pointer-events-none absolute inset-x-0 top-0 z-30 flex items-center justify-between px-6 py-3 text-[10px] tracking-[0.32em] text-slate-500">
        <div className="flex items-center gap-2">
          <span className="size-1.5 rounded-full bg-cyan-300 shadow-[0_0_8px_#67e8f9]" />
          AICC.COMMAND // TERMINAL
        </div>
        <div className="hidden items-center gap-3 md:flex">
          <span>NODE: TX-7A</span>
          <span className="text-slate-700">|</span>
          <span>SECURE BOOT OK</span>
          <span className="text-slate-700">|</span>
          <span>{fmtClockUTC(now)}</span>
        </div>
      </header>

      <div className="relative z-10 grid h-full w-full grid-cols-1 lg:grid-cols-[55fr_45fr]">
        {/* ========================= 左 : 战场态势展示 ========================= */}
        <section className="relative hidden h-full min-h-0 flex-col justify-between overflow-hidden px-10 pb-8 pt-16 lg:flex xl:px-14">
          {/* 顶部行：品牌 + 系统状态 pill */}
          <div className="flex items-start justify-between">
            <Brand />
            <div className="flex flex-col items-end gap-2">
              <StatusPill
                dotColor="bg-emerald-400"
                label="TACTICAL AI ONLINE"
                sub="OPERATIONAL"
              />
              <StatusPill
                dotColor="bg-cyan-300"
                label="C2 LINK SECURED"
                sub="TLS 1.3 · 256 AES"
              />
            </div>
          </div>

          {/* 标题 + 雷达可视化 */}
          <div className="relative mt-6 flex flex-1 items-center">
            {/* 后景雷达 */}
            <TacticalRadar reduce={reduceMotion ?? false} />

            {/* 主标题（绝对定位在雷达左上） */}
            <div className="relative z-10 max-w-[620px]">
              <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-300/[0.06] px-3 py-1 text-[11px] tracking-[0.32em] text-cyan-200/80">
                <Sparkles className="size-3" /> NEXT-GEN AI COMMAND PLATFORM
              </div>
              <h1 className="font-semibold leading-[1.05] tracking-tight text-slate-50">
                <span className="block text-[44px] xl:text-[52px]">
                  智能决策 ·{" "}
                  <span className="bg-gradient-to-r from-cyan-300 via-sky-300 to-blue-300 bg-clip-text text-transparent">
                    精准指挥
                  </span>
                </span>
                <span className="mt-1 block text-[28px] font-light text-slate-300 xl:text-[32px]">
                  掌控战场每一个瞬间
                </span>
              </h1>
              <p className="mt-4 max-w-md text-sm leading-relaxed text-slate-400">
                AICC COMMAND
                构建于多智能体推演引擎，将传感、决策、行动闭环压缩到秒级，
                为联合指挥所提供战术级 AI 协同。
              </p>
            </div>
          </div>

          {/* AI 能力卡片 2x2 */}
          <div className="relative z-10 mt-6 grid grid-cols-2 gap-3">
            {CAPABILITIES.map((c, idx) => (
              <CapabilityCard key={c.code} {...c} delay={idx * 0.06} />
            ))}
          </div>

          {/* 底部状态条 */}
          <div className="relative z-10 mt-5 flex items-stretch gap-2 overflow-hidden rounded-xl border border-cyan-300/10 bg-[#06101f]/60 px-3 py-2 backdrop-blur-sm">
            {STATUS_BAR.map((s, i) => (
              <StatusCell key={s.label} {...s} divider={i !== STATUS_BAR.length - 1} />
            ))}
          </div>
        </section>

        {/* ========================= 右 : Identity Terminal ========================= */}
        <section className="relative flex h-full min-h-0 items-center justify-center px-6 py-10 sm:px-10">
          {/* 右侧专属背景：竖直扫描带 */}
          {!reduceMotion && (
            <motion.div
              aria-hidden
              className="pointer-events-none absolute inset-y-0 left-0 right-0 overflow-hidden"
            >
              <motion.div
                className="absolute inset-x-0 h-[40%] bg-gradient-to-b from-transparent via-cyan-300/[0.06] to-transparent"
                animate={{ y: ["-30%", "120%"] }}
                transition={{ duration: 9, ease: "linear", repeat: Infinity }}
              />
            </motion.div>
          )}

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            className="relative z-10 w-full max-w-[440px]"
          >
            {/* 外层多边形发光描边 */}
            <div className="pointer-events-none absolute -inset-px rounded-[28px] bg-gradient-to-b from-cyan-400/30 via-cyan-300/5 to-blue-500/20 opacity-80" />
            <div className="pointer-events-none absolute -inset-[18px] rounded-[36px] bg-cyan-400/[0.04] blur-2xl" />

            {/* 玻璃面板 */}
            <div className="relative overflow-hidden rounded-[26px] border border-cyan-300/15 bg-[#070d18]/85 backdrop-blur-xl">
              {/* 内部 HUD 角标 */}
              <CornerTicks />

              {/* 顶栏：身份认证终端 */}
              <div className="flex items-center gap-2 border-b border-cyan-300/10 bg-gradient-to-r from-cyan-400/[0.06] via-transparent to-blue-500/[0.05] px-5 py-3">
                <span className="grid size-7 place-items-center rounded-md border border-cyan-300/30 bg-cyan-300/10 text-cyan-200">
                  <Fingerprint className="size-3.5" />
                </span>
                <div className="flex flex-1 items-baseline gap-2">
                  <span className="text-xs font-semibold tracking-[0.28em] text-slate-100">
                    IDENTITY TERMINAL
                  </span>
                  <span className="text-[10px] tracking-[0.28em] text-slate-500">
                    /{tab === "login" ? "AUTH" : "ENROLL"}
                  </span>
                </div>
                <span className="flex items-center gap-1 text-[10px] tracking-[0.28em] text-emerald-300/90">
                  <span className="size-1.5 animate-pulse rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
                  LINK · 99.97%
                </span>
              </div>

              {/* 系统状态 + 安全认证两行 */}
              <div className="grid grid-cols-2 gap-2 border-b border-cyan-300/10 px-5 py-3 text-[10px] tracking-[0.22em] text-slate-400">
                <SystemRow
                  icon={<Zap className="size-3" />}
                  label="SYSTEM STATUS"
                  value="Tactical AI Online"
                  ok
                />
                <SystemRow
                  icon={<ShieldCheck className="size-3" />}
                  label="SECURE ACCESS"
                  value="Military Grade"
                  ok
                />
              </div>

              {/* Tab */}
              <div className="grid grid-cols-2 border-b border-cyan-300/10">
                <TabHead
                  active={tab === "login"}
                  onClick={() => setTab("login")}
                  title="LOGIN"
                  subtitle="授权进入"
                />
                <TabHead
                  active={tab === "register"}
                  onClick={() => setTab("register")}
                  title="ENROLL"
                  subtitle="新建身份"
                />
              </div>

              <form onSubmit={handleSubmit} className="space-y-4 px-6 py-6 sm:px-7">
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div
                    key={tab}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -8 }}
                    transition={{ duration: 0.22, ease: "easeOut" }}
                    className="space-y-4"
                  >
                    <HudInput
                      icon={<UserCog className="size-4" />}
                      label="COMMANDER ID"
                      hint="01"
                    >
                      <input
                        type="email"
                        required
                        autoComplete="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="请输入指挥官编号 / 邮箱"
                        className="w-full bg-transparent font-mono text-sm tracking-wide text-slate-100 placeholder:text-slate-600 focus:outline-none"
                      />
                    </HudInput>

                    {tab === "register" && (
                      <HudInput
                        icon={<Terminal className="size-4" />}
                        label="CALLSIGN (OPTIONAL)"
                        hint="02"
                      >
                        <input
                          type="text"
                          maxLength={80}
                          autoComplete="nickname"
                          value={displayName}
                          onChange={(e) => setDisplayName(e.target.value)}
                          placeholder="如：Falcon-7 / 王指挥"
                          className="w-full bg-transparent font-mono text-sm tracking-wide text-slate-100 placeholder:text-slate-600 focus:outline-none"
                        />
                      </HudInput>
                    )}

                    <HudInput
                      icon={<KeyRound className="size-4" />}
                      label="ACCESS KEY"
                      hint={tab === "register" ? "03" : "02"}
                      trailing={
                        <button
                          type="button"
                          onClick={() => setShowPassword((v) => !v)}
                          title={showPassword ? "隐藏" : "显示"}
                          className="grid size-7 place-items-center rounded-md text-slate-400 hover:bg-white/5 hover:text-slate-200"
                        >
                          {showPassword ? (
                            <EyeOff className="size-4" />
                          ) : (
                            <Eye className="size-4" />
                          )}
                        </button>
                      }
                    >
                      <input
                        type={showPassword ? "text" : "password"}
                        required
                        minLength={tab === "register" ? 8 : undefined}
                        autoComplete={
                          tab === "register" ? "new-password" : "current-password"
                        }
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder={
                          tab === "register"
                            ? "请输入安全访问密钥（≥ 8 位）"
                            : "请输入安全访问密钥"
                        }
                        className="w-full bg-transparent font-mono text-sm tracking-wide text-slate-100 placeholder:text-slate-600 focus:outline-none"
                      />
                    </HudInput>

                    {tab === "register" && (
                      <HudInput
                        icon={<Lock className="size-4" />}
                        label="VERIFY KEY"
                        hint="04"
                      >
                        <input
                          type={showPassword ? "text" : "password"}
                          required
                          minLength={8}
                          autoComplete="new-password"
                          value={password2}
                          onChange={(e) => setPassword2(e.target.value)}
                          placeholder="再次输入以确认"
                          className="w-full bg-transparent font-mono text-sm tracking-wide text-slate-100 placeholder:text-slate-600 focus:outline-none"
                        />
                      </HudInput>
                    )}

                    {tab === "login" && (
                      <div className="flex items-center justify-between text-[11px] tracking-wider text-slate-400">
                        <label className="flex select-none items-center gap-2">
                          <input
                            type="checkbox"
                            defaultChecked
                            className="size-3.5 accent-cyan-400"
                          />
                          KEEP SESSION
                        </label>
                        <button
                          type="button"
                          onClick={() =>
                            setInfo("访问密钥重置请联系管理员或 v2 自助流程")
                          }
                          className="font-mono uppercase tracking-[0.18em] text-cyan-300/80 hover:text-cyan-200"
                        >
                          忘记密钥?
                        </button>
                      </div>
                    )}

                    {(error || info) && (
                      <motion.div
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        className={cn(
                          "flex items-start gap-2 rounded-lg border px-3 py-2 font-mono text-xs",
                          error
                            ? "border-red-500/30 bg-red-500/10 text-red-200"
                            : "border-cyan-300/25 bg-cyan-300/10 text-cyan-100"
                        )}
                      >
                        <span
                          className={cn(
                            "mt-0.5 size-1.5 shrink-0 rounded-full",
                            error ? "bg-red-400" : "bg-cyan-300"
                          )}
                        />
                        <span className="flex-1">{error ?? info}</span>
                      </motion.div>
                    )}

                    <TacticalSubmit
                      submitting={submitting}
                      label={tab === "login" ? "AUTHORIZE" : "ENROLL"}
                      sub={
                        tab === "login"
                          ? "进入战术指挥控制平台"
                          : "创建并完成身份注册"
                      }
                    />
                  </motion.div>
                </AnimatePresence>

                {/* 三方占位 */}
                <div className="pt-1">
                  <div className="relative my-1 flex items-center gap-3 text-[10px] tracking-[0.28em] text-slate-500">
                    <span className="h-px flex-1 bg-cyan-300/10" />
                    OR USE TRUSTED CHANNEL
                    <span className="h-px flex-1 bg-cyan-300/10" />
                  </div>
                  <div className="grid grid-cols-3 gap-2 pt-2">
                    <SsoChip
                      icon={<ShieldCheck className="size-3.5" />}
                      label="SSO"
                      onClick={() => setInfo("企业 SSO 将在私有部署版开放")}
                    />
                    <SsoChip
                      icon={<Globe2 className="size-3.5" />}
                      label="DINGTALK"
                      onClick={() => setInfo("钉钉扫码接入将在 v2 开放")}
                    />
                    <SsoChip
                      icon={<Layers3 className="size-3.5" />}
                      label="WECOM"
                      onClick={() => setInfo("企业微信接入将在 v2 开放")}
                    />
                  </div>
                </div>

                {/* 协议 / 切换 */}
                <div className="border-t border-cyan-300/10 pt-3 text-center text-[10px] leading-relaxed tracking-wider text-slate-500">
                  {tab === "login" ? "登录" : "注册"}即表示您同意{" "}
                  <button
                    type="button"
                    className="text-cyan-300/80 hover:text-cyan-200"
                    onClick={() => setInfo("用户协议将在正式发布版本提供")}
                  >
                    《用户协议》
                  </button>
                  {" / "}
                  <button
                    type="button"
                    className="text-cyan-300/80 hover:text-cyan-200"
                    onClick={() => setInfo("隐私政策将在正式发布版本提供")}
                  >
                    《隐私政策》
                  </button>
                  <div className="pt-1.5">
                    {tab === "login" ? (
                      <>
                        尚未持有指挥官身份?{" "}
                        <RouterLink
                          to="/register"
                          className="font-mono uppercase tracking-[0.18em] text-cyan-300 hover:text-cyan-200"
                        >
                          申请注册
                        </RouterLink>
                      </>
                    ) : (
                      <>
                        已有身份?{" "}
                        <RouterLink
                          to="/login"
                          className="font-mono uppercase tracking-[0.18em] text-cyan-300 hover:text-cyan-200"
                        >
                          返回登录
                        </RouterLink>
                      </>
                    )}
                  </div>
                </div>
              </form>

              {/* 底部安全条 */}
              <div className="flex items-center justify-between border-t border-cyan-300/10 bg-[#040912]/60 px-5 py-2 font-mono text-[10px] tracking-[0.22em] text-slate-500">
                <span className="flex items-center gap-1.5">
                  <Lock className="size-3 text-emerald-300" />
                  CONNECTION ENCRYPTED · TLS 1.3
                </span>
                <span>v0.2.0</span>
              </div>
            </div>
          </motion.div>
        </section>
      </div>

      {/* 底部 footer 行（绝对定位，不影响主网格高度） */}
      <footer className="pointer-events-none absolute inset-x-0 bottom-0 z-30 hidden items-center justify-between px-6 py-3 font-mono text-[10px] tracking-[0.22em] text-slate-600 lg:flex">
        <span>© 2026 AICC COMMAND · ALL DOMAINS RESERVED</span>
        <span>UNAUTHORIZED ACCESS WILL BE RECORDED</span>
      </footer>
    </div>
  );
}

// =============================================================================
// 子组件 -- 背景层
// =============================================================================

function TacticalBackground({ reduce }: { reduce: boolean }) {
  return (
    <>
      {/* base color wash */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(120%_80%_at_30%_30%,rgba(34,135,180,0.16),transparent_60%),radial-gradient(80%_60%_at_85%_75%,rgba(72,98,239,0.12),transparent_55%),linear-gradient(180deg,#03070f_0%,#040a14_60%,#02060d_100%)]" />
      {/* 网格 */}
      <div className="pointer-events-none absolute inset-0 tactical-grid opacity-[0.55]" />
      {/* 第二层细网格（45° 仅左侧） */}
      <div
        className="pointer-events-none absolute inset-y-0 left-0 w-[55%] opacity-30"
        style={{
          backgroundImage:
            "linear-gradient(45deg, rgba(76,201,240,0.05) 1px, transparent 1px), linear-gradient(-45deg, rgba(76,201,240,0.05) 1px, transparent 1px)",
          backgroundSize: "120px 120px",
          maskImage:
            "radial-gradient(80% 60% at 30% 50%, black 40%, transparent 80%)",
        }}
      />

      {/* 角落雷达 ping */}
      <RadarPing className="left-[-10%] top-[-10%]" delay={0} reduce={reduce} />
      <RadarPing
        className="bottom-[-10%] right-[-8%]"
        delay={1.4}
        reduce={reduce}
      />

      {/* 横向扫描带 */}
      {!reduce && (
        <motion.div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-[200%] [mask-image:linear-gradient(to_bottom,transparent,black_20%,black_80%,transparent)]"
        >
          <motion.div
            className="absolute inset-x-0 h-px bg-gradient-to-r from-transparent via-cyan-300/40 to-transparent"
            animate={{ y: ["0%", "100%"] }}
            transition={{ duration: 6, ease: "linear", repeat: Infinity }}
          />
        </motion.div>
      )}

      {/* 散落数据粒子 */}
      <ParticleField reduce={reduce} />

      {/* vignette */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(120%_80%_at_50%_50%,transparent_55%,rgba(0,0,0,0.45)_100%)]" />
    </>
  );
}

function RadarPing({
  className,
  delay,
  reduce,
}: {
  className?: string;
  delay: number;
  reduce: boolean;
}) {
  const rings = [0, 1, 2];
  return (
    <div
      aria-hidden
      className={cn(
        "pointer-events-none absolute size-[36rem] rounded-full",
        className
      )}
    >
      {rings.map((i) => (
        <motion.span
          key={i}
          className="absolute inset-0 rounded-full border border-cyan-300/15"
          initial={{ scale: 0.4, opacity: 0.0 }}
          animate={
            reduce
              ? { opacity: 0.18 }
              : { scale: [0.4, 1.05], opacity: [0.0, 0.25, 0.0] }
          }
          transition={
            reduce
              ? undefined
              : {
                  duration: 5.5,
                  delay: delay + i * 1.4,
                  ease: "easeOut",
                  repeat: Infinity,
                }
          }
        />
      ))}
    </div>
  );
}

function ParticleField({ reduce }: { reduce: boolean }) {
  // 用确定性的伪随机点位，避免每次渲染抖动
  const dots = useMemo(() => {
    const arr: Array<{ x: number; y: number; r: number; d: number }> = [];
    let seed = 17;
    const rand = () => {
      seed = (seed * 9301 + 49297) % 233280;
      return seed / 233280;
    };
    for (let i = 0; i < 38; i += 1) {
      arr.push({
        x: rand() * 100,
        y: rand() * 100,
        r: rand() * 1.4 + 0.4,
        d: rand() * 4,
      });
    }
    return arr;
  }, []);

  return (
    <svg
      aria-hidden
      className="pointer-events-none absolute inset-0 h-full w-full"
    >
      {dots.map((p, i) => (
        <motion.circle
          key={i}
          cx={`${p.x}%`}
          cy={`${p.y}%`}
          r={p.r}
          fill="rgba(125,211,252,0.55)"
          initial={{ opacity: 0.2 }}
          animate={
            reduce
              ? { opacity: 0.4 }
              : { opacity: [0.2, 0.9, 0.2] }
          }
          transition={
            reduce
              ? undefined
              : { duration: 3 + p.d, repeat: Infinity, ease: "easeInOut" }
          }
        />
      ))}
    </svg>
  );
}

// =============================================================================
// 子组件 -- 战术雷达
// =============================================================================

function TacticalRadar({ reduce }: { reduce: boolean }) {
  // 五个固定 blip，避免随机抖动；带状态颜色
  const blips: Array<{ x: number; y: number; tone: string; key: string; label?: string }> = [
    { x: 220, y: 120, tone: "fill-cyan-300", key: "n1", label: "BLUE-A1" },
    { x: 360, y: 220, tone: "fill-cyan-300", key: "n2", label: "BLUE-A2" },
    { x: 480, y: 150, tone: "fill-amber-300", key: "n3", label: "UNK-3" },
    { x: 540, y: 320, tone: "fill-red-400", key: "n4", label: "RED-7" },
    { x: 280, y: 360, tone: "fill-emerald-300", key: "n5", label: "ALLY" },
  ];

  // 航线（贝塞尔虚线）
  const routes = [
    "M120,360 C 240,280 320,260 380,200",
    "M520,400 C 460,330 420,310 380,280",
  ];

  return (
    <svg
      aria-hidden
      viewBox="0 0 720 480"
      className="pointer-events-none absolute inset-0 h-full w-full opacity-90"
    >
      <defs>
        <radialGradient id="radarGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="rgba(76,201,240,0.18)" />
          <stop offset="60%" stopColor="rgba(76,201,240,0.04)" />
          <stop offset="100%" stopColor="rgba(76,201,240,0)" />
        </radialGradient>
        <linearGradient id="sweepGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="rgba(76,201,240,0)" />
          <stop offset="100%" stopColor="rgba(76,201,240,0.65)" />
        </linearGradient>
        {/* 战术地图轮廓（极简虚拟海岸线） */}
        <pattern id="hex" width="36" height="32" patternUnits="userSpaceOnUse">
          <path
            d="M18,0 L36,8 L36,24 L18,32 L0,24 L0,8 Z"
            fill="none"
            stroke="rgba(76,201,240,0.06)"
            strokeWidth="0.6"
          />
        </pattern>
      </defs>

      {/* 蜂窝纹理 */}
      <rect width="720" height="480" fill="url(#hex)" />

      {/* 雷达辉光圆 */}
      <circle cx="430" cy="260" r="220" fill="url(#radarGlow)" />

      {/* 同心圆 */}
      {[60, 120, 180, 220].map((r) => (
        <circle
          key={r}
          cx="430"
          cy="260"
          r={r}
          fill="none"
          stroke="rgba(125,211,252,0.18)"
          strokeWidth={r === 220 ? 1.2 : 0.8}
          strokeDasharray={r === 220 ? undefined : "2 4"}
        />
      ))}
      {/* 十字 */}
      <line x1="210" y1="260" x2="650" y2="260" stroke="rgba(125,211,252,0.15)" />
      <line x1="430" y1="40" x2="430" y2="480" stroke="rgba(125,211,252,0.15)" />

      {/* 扫描扇形（旋转） */}
      <g style={{ transformOrigin: "430px 260px" }}>
        <motion.g
          initial={{ rotate: 0 }}
          animate={reduce ? { rotate: 0 } : { rotate: 360 }}
          transition={
            reduce ? undefined : { duration: 7.5, ease: "linear", repeat: Infinity }
          }
        >
          <path
            d="M430,260 L650,260 A220,220 0 0 0 590,108 Z"
            fill="url(#sweepGrad)"
            opacity="0.45"
          />
          {/* 扫描前沿亮线 */}
          <line
            x1="430"
            y1="260"
            x2="650"
            y2="260"
            stroke="rgba(125,211,252,0.85)"
            strokeWidth="1.2"
          />
        </motion.g>
      </g>

      {/* 航线虚线 */}
      {routes.map((d, i) => (
        <motion.path
          key={i}
          d={d}
          fill="none"
          stroke={i === 0 ? "rgba(125,211,252,0.55)" : "rgba(248,113,113,0.45)"}
          strokeWidth="1.1"
          strokeDasharray="4 6"
          initial={{ pathLength: 0, opacity: 0.2 }}
          animate={reduce ? { pathLength: 1, opacity: 0.7 } : { pathLength: [0.2, 1], opacity: [0.4, 0.9, 0.4] }}
          transition={
            reduce ? undefined : { duration: 5 + i, ease: "easeInOut", repeat: Infinity }
          }
        />
      ))}

      {/* blips */}
      {blips.map((b, i) => (
        <g key={b.key}>
          <motion.circle
            cx={b.x}
            cy={b.y}
            r={3}
            className={b.tone}
            initial={{ opacity: 0.5 }}
            animate={
              reduce ? { opacity: 1 } : { opacity: [0.4, 1, 0.4] }
            }
            transition={
              reduce ? undefined : { duration: 1.6 + i * 0.3, ease: "easeInOut", repeat: Infinity }
            }
          />
          {/* 血统连线只画一对 */}
          {i === 0 && (
            <line
              x1={b.x}
              y1={b.y}
              x2={b.x + 18}
              y2={b.y - 10}
              stroke="rgba(125,211,252,0.4)"
            />
          )}
          {b.label && (
            <text
              x={b.x + 8}
              y={b.y - 8}
              fontSize="9"
              letterSpacing="2"
              fill="rgba(186,230,253,0.75)"
              fontFamily="JetBrains Mono, monospace"
            >
              {b.label}
            </text>
          )}
        </g>
      ))}

      {/* 网格坐标标签 */}
      <g
        fontSize="9"
        letterSpacing="2"
        fill="rgba(148,163,184,0.55)"
        fontFamily="JetBrains Mono, monospace"
      >
        <text x="220" y="262">100</text>
        <text x="340" y="262">200</text>
        <text x="430" y="56">N</text>
        <text x="430" y="476">S</text>
      </g>
    </svg>
  );
}

// =============================================================================
// 子组件 -- 表单 / UI 原子
// =============================================================================

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <div
        aria-hidden
        className="relative grid size-12 place-items-center rounded-2xl border border-cyan-300/30 bg-gradient-to-br from-cyan-400/30 to-blue-500/20 text-cyan-50 shadow-[0_0_24px_rgba(76,201,240,0.25)]"
      >
        <Hexagon className="size-6 text-cyan-100/90" strokeWidth={1.4} />
        <Sparkles className="absolute size-3 text-cyan-200" />
      </div>
      <div className="leading-tight">
        <div className="text-base font-semibold tracking-[0.32em] text-slate-50">
          AICC · COMMAND
        </div>
        <div className="text-[11px] tracking-[0.32em] text-slate-400">
          AI TACTICAL CONTROL // v0.2
        </div>
      </div>
    </div>
  );
}

function StatusPill({
  dotColor,
  label,
  sub,
}: {
  dotColor: string;
  label: string;
  sub: string;
}) {
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-cyan-300/15 bg-[#06101f]/70 px-3 py-1 backdrop-blur-sm">
      <span className={cn("size-1.5 animate-pulse rounded-full", dotColor)} />
      <span className="font-mono text-[10px] tracking-[0.28em] text-slate-100">
        {label}
      </span>
      <span className="font-mono text-[10px] tracking-[0.28em] text-slate-500">
        · {sub}
      </span>
    </div>
  );
}

function CapabilityCard({
  icon: Icon,
  code,
  title,
  desc,
  metric,
  delay,
}: (typeof CAPABILITIES)[number] & { delay: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 + delay, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ y: -2 }}
      className="group relative overflow-hidden rounded-xl border border-cyan-300/12 bg-gradient-to-br from-[#091522]/85 to-[#040b16]/85 p-3 backdrop-blur-md transition-colors hover:border-cyan-300/30"
    >
      {/* 顶部细线 */}
      <span className="pointer-events-none absolute inset-x-3 top-0 h-px bg-gradient-to-r from-transparent via-cyan-300/40 to-transparent opacity-60 group-hover:opacity-100" />
      {/* 角标 ticks */}
      <span className="pointer-events-none absolute right-2 top-2 font-mono text-[9px] tracking-[0.28em] text-slate-500">
        {code}
      </span>
      {/* hover glow */}
      <span
        aria-hidden
        className="pointer-events-none absolute -inset-px rounded-xl opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{
          background:
            "radial-gradient(160px 90px at 20% 0%, rgba(76,201,240,0.18), transparent 60%)",
        }}
      />
      <div className="relative flex items-start gap-3">
        <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg border border-cyan-300/20 bg-cyan-300/10 text-cyan-200 shadow-[0_0_18px_rgba(76,201,240,0.18)] transition-transform group-hover:scale-[1.04]">
          <Icon className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <div className="text-[13px] font-semibold tracking-wide text-slate-100">
              {title}
            </div>
            <span className="ml-auto font-mono text-[10px] tracking-[0.18em] text-cyan-200/80">
              {metric}
            </span>
          </div>
          <div className="mt-1 text-[11px] leading-relaxed text-slate-400">
            {desc}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function StatusCell({
  icon: Icon,
  label,
  value,
  tone,
  divider,
}: {
  icon: typeof Activity;
  label: string;
  value: string;
  tone: "ok" | "warn" | "neutral";
  divider: boolean;
}) {
  const toneCls =
    tone === "ok"
      ? "text-emerald-300"
      : tone === "warn"
        ? "text-amber-300"
        : "text-slate-200";
  return (
    <div
      className={cn(
        "relative flex flex-1 items-center gap-2 px-3 py-1.5",
        divider && "after:absolute after:inset-y-2 after:right-0 after:w-px after:bg-cyan-300/10"
      )}
    >
      <Icon className={cn("size-3.5", toneCls)} />
      <div className="flex flex-col leading-tight">
        <span className="font-mono text-[9px] tracking-[0.28em] text-slate-500">
          {label}
        </span>
        <span className={cn("font-mono text-[11px] tracking-wider", toneCls)}>
          {value}
        </span>
      </div>
    </div>
  );
}

function CornerTicks() {
  // 玻璃面板四角小直角，呼应 HUD 视觉
  const ticks = [
    "left-2 top-2 border-l border-t",
    "right-2 top-2 border-r border-t",
    "left-2 bottom-2 border-l border-b",
    "right-2 bottom-2 border-r border-b",
  ];
  return (
    <>
      {ticks.map((c) => (
        <span
          key={c}
          aria-hidden
          className={cn(
            "pointer-events-none absolute size-3 border-cyan-300/40",
            c
          )}
        />
      ))}
    </>
  );
}

function SystemRow({
  icon,
  label,
  value,
  ok,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  ok?: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="grid size-6 place-items-center rounded-md border border-cyan-300/20 bg-cyan-300/[0.06] text-cyan-200">
        {icon}
      </span>
      <div className="leading-tight">
        <div className="font-mono text-[9px] tracking-[0.28em] text-slate-500">
          {label}
        </div>
        <div
          className={cn(
            "font-mono text-[11px] tracking-wider",
            ok ? "text-emerald-300" : "text-slate-100"
          )}
        >
          {value}
        </div>
      </div>
    </div>
  );
}

function TabHead({
  active,
  onClick,
  title,
  subtitle,
}: {
  active: boolean;
  onClick: () => void;
  title: string;
  subtitle: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "relative flex flex-col items-center justify-center gap-0.5 px-3 py-3 transition-colors",
        active ? "text-cyan-200" : "text-slate-500 hover:text-slate-300"
      )}
    >
      <span className="font-mono text-[12px] tracking-[0.32em]">{title}</span>
      <span className="text-[10px] tracking-[0.22em] text-slate-500">
        {subtitle}
      </span>
      {active && (
        <motion.span
          layoutId="auth-tab-underline"
          className="absolute inset-x-6 -bottom-px h-[2px] rounded-full bg-gradient-to-r from-cyan-400 to-blue-400 shadow-[0_0_14px_rgba(76,201,240,0.7)]"
        />
      )}
    </button>
  );
}

function HudInput({
  icon,
  label,
  hint,
  trailing,
  children,
}: {
  icon: ReactNode;
  label: string;
  hint: string;
  trailing?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between font-mono text-[10px] tracking-[0.28em] text-slate-500">
        <span>{label}</span>
        <span className="text-slate-600">/{hint}</span>
      </div>
      <div className="group relative">
        <span
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-xl bg-gradient-to-r from-cyan-300/0 via-cyan-300/0 to-blue-400/0 opacity-0 transition-opacity duration-300 group-focus-within:opacity-100"
          style={{
            background:
              "linear-gradient(90deg, rgba(76,201,240,0.0), rgba(76,201,240,0.18), rgba(72,149,239,0.0))",
            filter: "blur(8px)",
          }}
        />
        <div className="relative flex items-center gap-3 rounded-xl border border-cyan-300/15 bg-[#040b16]/70 px-3 py-2.5 transition-colors duration-200 focus-within:border-cyan-300/55 focus-within:bg-[#040b16]/85 focus-within:shadow-[inset_0_0_0_1px_rgba(76,201,240,0.35),0_0_0_1px_rgba(76,201,240,0.15),0_0_22px_rgba(76,201,240,0.18)]">
          <span className="grid size-7 place-items-center rounded-md border border-cyan-300/15 bg-cyan-300/[0.06] text-cyan-300">
            {icon}
          </span>
          <div className="min-w-0 flex-1">{children}</div>
          {trailing}
          <span className="pointer-events-none ml-1 hidden h-[14px] w-px bg-cyan-300/30 group-focus-within:block group-focus-within:animate-pulse" />
        </div>
      </div>
    </div>
  );
}

function TacticalSubmit({
  submitting,
  label,
  sub,
}: {
  submitting: boolean;
  label: string;
  sub: string;
}) {
  return (
    <button
      type="submit"
      disabled={submitting}
      className={cn(
        "group relative mt-2 flex w-full items-center justify-between overflow-hidden rounded-xl border border-cyan-300/35",
        "bg-[linear-gradient(135deg,rgba(76,201,240,0.95),rgba(72,149,239,0.95))]",
        "px-4 py-3 text-left text-slate-950 shadow-[0_0_0_1px_rgba(76,201,240,0.5),0_12px_36px_-8px_rgba(76,201,240,0.55)]",
        "transition-transform duration-200 hover:-translate-y-[1px] hover:shadow-[0_0_0_1px_rgba(76,201,240,0.7),0_18px_40px_-8px_rgba(76,201,240,0.7)]",
        "active:translate-y-0 disabled:opacity-70"
      )}
    >
      {/* sweep highlight */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 -translate-x-full bg-[linear-gradient(120deg,transparent,rgba(255,255,255,0.45),transparent)] transition-transform duration-700 group-hover:translate-x-full"
      />
      <span className="relative flex items-center gap-2.5">
        <Target className="size-4" />
        <span className="flex flex-col leading-tight">
          <span className="font-mono text-[13px] font-bold tracking-[0.28em]">
            {submitting ? "AUTHORIZING…" : label}
          </span>
          <span className="text-[10px] font-medium tracking-[0.18em] text-slate-900/70">
            {submitting ? "ESTABLISHING SECURE CHANNEL" : sub}
          </span>
        </span>
      </span>
      <span className="relative flex items-center gap-1 font-mono text-[11px] tracking-[0.28em]">
        ENTER
        {submitting ? (
          <motion.span
            animate={{ rotate: 360 }}
            transition={{ duration: 1, ease: "linear", repeat: Infinity }}
            className="ml-1 inline-block size-3 rounded-full border-2 border-slate-900/40 border-t-slate-900"
          />
        ) : (
          <ArrowRight className="size-4" />
        )}
      </span>
    </button>
  );
}

function SsoChip({
  icon,
  label,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex items-center justify-between rounded-lg border border-cyan-300/15 bg-[#04101e]/60 px-3 py-2 font-mono text-[10px] tracking-[0.22em] text-slate-300 transition-all hover:border-cyan-300/40 hover:bg-[#04101e]/90 hover:text-cyan-100"
    >
      <span className="flex items-center gap-2">
        <span className="text-cyan-300/90">{icon}</span>
        {label}
      </span>
      <ChevronRight className="size-3 text-slate-500 group-hover:text-cyan-200" />
    </button>
  );
}

// =============================================================================
// 工具
// =============================================================================

function fmtClockUTC(d: Date): string {
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  const ss = String(d.getUTCSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss} UTC`;
}

function humanizeError(err: unknown, tab: Tab): string {
  if (!(err instanceof ApiError)) return "操作失败,请稍后重试";
  const detail =
    typeof err.detail === "object" && err.detail !== null
      ? (err.detail as { detail?: unknown }).detail
      : null;
  const code =
    typeof detail === "string"
      ? detail
      : (detail as { code?: string } | null)?.code ?? null;
  if (tab === "login") {
    if (code === "LOGIN_BAD_CREDENTIALS") return "指挥官编号或访问密钥错误";
    if (code === "LOGIN_USER_NOT_VERIFIED") return "身份未验证,请联系管理员";
  } else {
    if (code === "REGISTER_USER_ALREADY_EXISTS") return "该编号已被注册";
    if (code === "REGISTER_INVALID_PASSWORD") return "访问密钥不符合要求";
  }
  return err.message || "操作失败";
}
