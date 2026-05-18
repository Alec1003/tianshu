// AICC COMMAND -- Tactical Identity Terminal (精简版)
// =============================================================================
// 设计目标：在保留「AI 指挥控制平台」识别度的前提下大幅降低视觉密度。
//
// 取舍（相对前一版）：
//   - 删除：顶部时钟、底部 footer、双 status pill、底部状态条、CornerTicks
//     四角、SystemRow 双行、三方 SSO chip、双层网格、38 粒子场、双 RadarPing、
//     vignette。
//   - 雷达精简到 3 同心圆 + 1 扫描扇形 + 3 blip + 1 航线，不再有标签。
//   - 能力卡只有 3 张、横向一行，去掉 code / metric 副信息。
//   - 全局动效降到 4 个：背景扫描线、雷达扫描、blip pulse、按钮 hover sweep。
//
// 技术：React + TS + Tailwind + framer-motion + lucide-react
// =============================================================================

import {
  useEffect,
  useMemo,
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
  ArrowRight,
  Brain,
  Eye,
  EyeOff,
  Hexagon,
  KeyRound,
  Lock,
  Network,
  Radar,
  ShieldCheck,
  Terminal,
  UserCog,
} from "lucide-react";

import { ApiError } from "@/api/client";
import { cn } from "@/lib/utils";
import { useAuth } from "./AuthContext";

const CAPABILITIES: Array<{
  icon: typeof Radar;
  title: string;
  desc: string;
}> = [
  {
    icon: Radar,
    title: "实时态势感知",
    desc: "多源传感器融合 / 全域目标跟踪",
  },
  {
    icon: Brain,
    title: "AI 智能推演",
    desc: "毫秒级对抗推演 / 战术建议生成",
  },
  {
    icon: Network,
    title: "多域协同作战",
    desc: "陆海空天电统一指挥 / 自适应编组",
  },
];

type Tab = "login" | "register";
type LocationState = { from?: { pathname?: string } } | null;

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, register } = useAuth();
  const reduceMotion = useReducedMotion();

  const initialTab: Tab =
    location.pathname === "/register" ? "register" : "login";
  const [tab, setTab] = useState<Tab>(initialTab);
  useEffect(() => {
    setTab(location.pathname === "/register" ? "register" : "login");
  }, [location.pathname]);

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
      <Background reduce={reduceMotion ?? false} />

      <div className="relative z-10 grid h-full w-full grid-cols-1 lg:grid-cols-[55fr_45fr]">
        {/* ============== 左侧：战场态势展示 ============== */}
        <section className="relative hidden h-full flex-col justify-between overflow-hidden px-10 py-12 lg:flex xl:px-14">
          <Brand />

          <div className="relative my-auto flex flex-col">
            <div className="mb-4 inline-flex items-center gap-2 self-start rounded-full border border-cyan-300/20 bg-cyan-300/[0.06] px-3 py-1 font-mono text-[10px] tracking-[0.32em] text-cyan-200/80">
              <span className="size-1.5 animate-pulse rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
              TACTICAL AI ONLINE
            </div>

            <h1 className="font-semibold leading-[1.05] tracking-tight text-slate-50">
              <span className="block text-[44px] xl:text-[52px]">
                智能决策 ·{" "}
                <span className="bg-gradient-to-r from-cyan-300 via-sky-300 to-blue-300 bg-clip-text text-transparent">
                  精准指挥
                </span>
              </span>
              <span className="mt-1 block text-[26px] font-light text-slate-300 xl:text-[30px]">
                掌控战场每一个瞬间
              </span>
            </h1>
            <p className="mt-4 max-w-md text-sm leading-relaxed text-slate-400">
              下一代 AI 战术指挥控制平台 —— 把传感、决策、行动闭环压缩到秒级。
            </p>

            {/* 雷达可视化 */}
            <div className="relative mt-8 h-[260px] w-full max-w-[560px] xl:h-[300px]">
              <TacticalRadar reduce={reduceMotion ?? false} />
            </div>
          </div>

          {/* 3 张能力卡，横向一行 */}
          <div className="grid grid-cols-3 gap-3">
            {CAPABILITIES.map((c, idx) => (
              <CapabilityCard key={c.title} {...c} delay={idx * 0.06} />
            ))}
          </div>
        </section>

        {/* ============== 右侧：Identity Terminal ============== */}
        <section className="relative flex h-full items-center justify-center px-6 py-10 sm:px-10">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="relative z-10 w-full max-w-[400px]"
          >
            {/* 外层柔光描边 */}
            <div className="pointer-events-none absolute -inset-px rounded-[24px] bg-gradient-to-b from-cyan-400/25 via-cyan-300/[0.05] to-blue-500/15 opacity-80" />
            <div className="pointer-events-none absolute -inset-3 rounded-[28px] bg-cyan-400/[0.04] blur-2xl" />

            {/* 玻璃面板 */}
            <div className="relative overflow-hidden rounded-[22px] border border-cyan-300/15 bg-[#070d18]/85 backdrop-blur-xl">
              {/* 顶栏 */}
              <div className="flex items-center justify-between gap-2 border-b border-cyan-300/10 bg-gradient-to-r from-cyan-400/[0.06] via-transparent to-blue-500/[0.05] px-5 py-3">
                <div className="flex items-center gap-2">
                  <span className="grid size-7 place-items-center rounded-md border border-cyan-300/30 bg-cyan-300/10 text-cyan-200">
                    <ShieldCheck className="size-3.5" />
                  </span>
                  <span className="font-mono text-xs font-semibold tracking-[0.28em] text-slate-100">
                    IDENTITY TERMINAL
                  </span>
                </div>
                <span className="flex items-center gap-1.5 font-mono text-[10px] tracking-[0.24em] text-emerald-300/90">
                  <span className="size-1.5 animate-pulse rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
                  SECURE LINK
                </span>
              </div>

              {/* Tab */}
              <div className="grid grid-cols-2 border-b border-cyan-300/10">
                <TabHead
                  active={tab === "login"}
                  onClick={() => setTab("login")}
                  title="LOGIN"
                />
                <TabHead
                  active={tab === "register"}
                  onClick={() => setTab("register")}
                  title="ENROLL"
                />
              </div>

              <form
                onSubmit={handleSubmit}
                className="space-y-4 px-6 py-6 sm:px-7"
              >
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div
                    key={tab}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.2, ease: "easeOut" }}
                    className="space-y-4"
                  >
                    <HudInput
                      icon={<UserCog className="size-4" />}
                      label="COMMANDER ID"
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
                          tab === "register"
                            ? "new-password"
                            : "current-password"
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
                      <div className="flex items-center justify-between font-mono text-[11px] tracking-wider text-slate-400">
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
                          className="uppercase tracking-[0.18em] text-cyan-300/80 hover:text-cyan-200"
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
                    />
                  </motion.div>
                </AnimatePresence>

                {/* 协议 + 切换链接合并到一行 */}
                <div className="border-t border-cyan-300/10 pt-3 text-center font-mono text-[10px] leading-relaxed tracking-wider text-slate-500">
                  {tab === "login" ? (
                    <>
                      未持有指挥官身份?{" "}
                      <RouterLink
                        to="/register"
                        className="uppercase tracking-[0.18em] text-cyan-300 hover:text-cyan-200"
                      >
                        申请注册
                      </RouterLink>
                    </>
                  ) : (
                    <>
                      已有身份?{" "}
                      <RouterLink
                        to="/login"
                        className="uppercase tracking-[0.18em] text-cyan-300 hover:text-cyan-200"
                      >
                        返回登录
                      </RouterLink>
                    </>
                  )}
                </div>
              </form>

              {/* 底部安全条 */}
              <div className="flex items-center justify-between border-t border-cyan-300/10 bg-[#040912]/60 px-5 py-2 font-mono text-[10px] tracking-[0.22em] text-slate-500">
                <span className="flex items-center gap-1.5">
                  <Lock className="size-3 text-emerald-300" />
                  TLS 1.3 · MILITARY GRADE
                </span>
                <span>v0.2.0</span>
              </div>
            </div>
          </motion.div>
        </section>
      </div>
    </div>
  );
}

// =============================================================================
// 背景层（精简）：tactical grid + 角落辉光 + 单条扫描线
// =============================================================================

function Background({ reduce }: { reduce: boolean }) {
  return (
    <>
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(110% 80% at 25% 20%, rgba(34,135,180,0.16), transparent 60%), radial-gradient(80% 60% at 90% 85%, rgba(72,98,239,0.12), transparent 55%), linear-gradient(180deg,#03070f 0%, #040a14 60%, #02060d 100%)",
        }}
      />
      <div className="pointer-events-none absolute inset-0 tactical-grid opacity-50" />
      {!reduce && (
        <motion.div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-[200%] [mask-image:linear-gradient(to_bottom,transparent,black_20%,black_80%,transparent)]"
        >
          <motion.div
            className="absolute inset-x-0 h-px bg-gradient-to-r from-transparent via-cyan-300/35 to-transparent"
            animate={{ y: ["0%", "100%"] }}
            transition={{ duration: 7, ease: "linear", repeat: Infinity }}
          />
        </motion.div>
      )}
    </>
  );
}

// =============================================================================
// 战术雷达（精简）：3 同心圆 + 1 扫描扇形 + 3 blip + 1 航线
// =============================================================================

function TacticalRadar({ reduce }: { reduce: boolean }) {
  // 雷达中心 (cx, cy) 与最大半径 R，blip 用极坐标定义后转直角
  const cx = 280;
  const cy = 150;
  const R = 130;

  const blips = [
    { angle: -40, dist: 0.55, tone: "fill-cyan-300" },
    { angle: 25, dist: 0.78, tone: "fill-amber-300" },
    { angle: 110, dist: 0.62, tone: "fill-emerald-300" },
  ].map((b, i) => {
    const rad = (b.angle * Math.PI) / 180;
    return {
      ...b,
      x: cx + Math.cos(rad) * R * b.dist,
      y: cy + Math.sin(rad) * R * b.dist,
      key: `b${i}`,
    };
  });

  return (
    <svg
      aria-hidden
      viewBox="0 0 560 300"
      className="absolute inset-0 h-full w-full"
    >
      <defs>
        <radialGradient id="radarGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="rgba(76,201,240,0.14)" />
          <stop offset="100%" stopColor="rgba(76,201,240,0)" />
        </radialGradient>
        <linearGradient id="sweep" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="rgba(76,201,240,0)" />
          <stop offset="100%" stopColor="rgba(76,201,240,0.55)" />
        </linearGradient>
      </defs>

      {/* 辉光底圆 */}
      <circle cx={cx} cy={cy} r={R} fill="url(#radarGlow)" />

      {/* 同心圆 */}
      {[R * 0.4, R * 0.7, R].map((r, i) => (
        <circle
          key={i}
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke="rgba(125,211,252,0.18)"
          strokeWidth={i === 2 ? 1.1 : 0.8}
          strokeDasharray={i === 2 ? undefined : "2 4"}
        />
      ))}

      {/* 十字 */}
      <line
        x1={cx - R}
        y1={cy}
        x2={cx + R}
        y2={cy}
        stroke="rgba(125,211,252,0.14)"
      />
      <line
        x1={cx}
        y1={cy - R}
        x2={cx}
        y2={cy + R}
        stroke="rgba(125,211,252,0.14)"
      />

      {/* 扫描扇形 */}
      <g style={{ transformOrigin: `${cx}px ${cy}px` }}>
        <motion.g
          initial={{ rotate: 0 }}
          animate={reduce ? { rotate: 0 } : { rotate: 360 }}
          transition={
            reduce
              ? undefined
              : { duration: 7.5, ease: "linear", repeat: Infinity }
          }
        >
          {/* 扇形：从 0° 到 -60°（顶部偏右） */}
          <path
            d={`M${cx},${cy} L${cx + R},${cy} A${R},${R} 0 0 0 ${cx + R * Math.cos((-60 * Math.PI) / 180)},${cy + R * Math.sin((-60 * Math.PI) / 180)} Z`}
            fill="url(#sweep)"
            opacity="0.5"
          />
          <line
            x1={cx}
            y1={cy}
            x2={cx + R}
            y2={cy}
            stroke="rgba(125,211,252,0.85)"
            strokeWidth="1.2"
          />
        </motion.g>
      </g>

      {/* 单条航线虚线（从左下进入到中央上方目标点） */}
      <motion.path
        d={`M${cx - 180},${cy + 90} C ${cx - 90},${cy + 30} ${cx - 30},${cy - 60} ${blips[0].x},${blips[0].y}`}
        fill="none"
        stroke="rgba(125,211,252,0.5)"
        strokeWidth="1.1"
        strokeDasharray="4 6"
        initial={{ pathLength: 0.2, opacity: 0.4 }}
        animate={
          reduce
            ? { pathLength: 1, opacity: 0.7 }
            : { pathLength: [0.3, 1], opacity: [0.4, 0.85, 0.4] }
        }
        transition={
          reduce
            ? undefined
            : { duration: 5, ease: "easeInOut", repeat: Infinity }
        }
      />

      {/* blips */}
      {blips.map((b, i) => (
        <motion.circle
          key={b.key}
          cx={b.x}
          cy={b.y}
          r={3}
          className={b.tone}
          initial={{ opacity: 0.5 }}
          animate={reduce ? { opacity: 1 } : { opacity: [0.4, 1, 0.4] }}
          transition={
            reduce
              ? undefined
              : {
                  duration: 1.6 + i * 0.3,
                  ease: "easeInOut",
                  repeat: Infinity,
                }
          }
        />
      ))}
    </svg>
  );
}

// =============================================================================
// 子组件：Brand / TabHead / HudInput / TacticalSubmit / CapabilityCard
// =============================================================================

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <div
        aria-hidden
        className="relative grid size-11 place-items-center rounded-xl border border-cyan-300/30 bg-gradient-to-br from-cyan-400/30 to-blue-500/20 text-cyan-50 shadow-[0_0_20px_rgba(76,201,240,0.22)]"
      >
        <Hexagon className="size-5 text-cyan-100/90" strokeWidth={1.4} />
      </div>
      <div className="leading-tight">
        <div className="font-mono text-sm font-semibold tracking-[0.28em] text-slate-50">
          AICC · COMMAND
        </div>
        <div className="font-mono text-[10px] tracking-[0.28em] text-slate-500">
          AI TACTICAL CONTROL
        </div>
      </div>
    </div>
  );
}

function TabHead({
  active,
  onClick,
  title,
}: {
  active: boolean;
  onClick: () => void;
  title: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "relative px-3 py-3 font-mono text-[12px] tracking-[0.32em] transition-colors",
        active ? "text-cyan-200" : "text-slate-500 hover:text-slate-300"
      )}
    >
      {title}
      {active && (
        <motion.span
          layoutId="auth-tab-underline"
          className="absolute inset-x-6 -bottom-px h-[2px] rounded-full bg-gradient-to-r from-cyan-400 to-blue-400 shadow-[0_0_12px_rgba(76,201,240,0.6)]"
        />
      )}
    </button>
  );
}

function HudInput({
  icon,
  label,
  trailing,
  children,
}: {
  icon: ReactNode;
  label: string;
  trailing?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div>
      <div className="mb-1.5 font-mono text-[10px] tracking-[0.28em] text-slate-500">
        {label}
      </div>
      <div className="group relative flex items-center gap-3 rounded-xl border border-cyan-300/15 bg-[#040b16]/70 px-3 py-2.5 transition-all duration-200 focus-within:border-cyan-300/55 focus-within:bg-[#040b16]/85 focus-within:shadow-[inset_0_0_0_1px_rgba(76,201,240,0.3),0_0_20px_rgba(76,201,240,0.18)]">
        <span className="grid size-7 place-items-center rounded-md border border-cyan-300/15 bg-cyan-300/[0.06] text-cyan-300">
          {icon}
        </span>
        <div className="min-w-0 flex-1">{children}</div>
        {trailing}
      </div>
    </div>
  );
}

function TacticalSubmit({
  submitting,
  label,
}: {
  submitting: boolean;
  label: string;
}) {
  return (
    <button
      type="submit"
      disabled={submitting}
      className={cn(
        "group relative mt-1 flex w-full items-center justify-between overflow-hidden rounded-xl border border-cyan-300/35",
        "bg-[linear-gradient(135deg,rgba(76,201,240,0.95),rgba(72,149,239,0.95))]",
        "px-4 py-3 text-slate-950",
        "shadow-[0_0_0_1px_rgba(76,201,240,0.4),0_10px_30px_-8px_rgba(76,201,240,0.5)]",
        "transition-all duration-200 hover:-translate-y-[1px] hover:shadow-[0_0_0_1px_rgba(76,201,240,0.65),0_16px_36px_-8px_rgba(76,201,240,0.65)]",
        "active:translate-y-0 disabled:opacity-70"
      )}
    >
      {/* hover sweep */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 -translate-x-full bg-[linear-gradient(120deg,transparent,rgba(255,255,255,0.45),transparent)] transition-transform duration-700 group-hover:translate-x-full"
      />
      <span className="relative font-mono text-[13px] font-bold tracking-[0.32em]">
        {submitting ? "AUTHORIZING…" : label}
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

function CapabilityCard({
  icon: Icon,
  title,
  desc,
  delay,
}: (typeof CAPABILITIES)[number] & { delay: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 + delay, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ y: -2 }}
      className="group relative overflow-hidden rounded-xl border border-cyan-300/12 bg-[#091522]/70 p-3 backdrop-blur-md transition-colors hover:border-cyan-300/30"
    >
      <span className="pointer-events-none absolute inset-x-3 top-0 h-px bg-gradient-to-r from-transparent via-cyan-300/35 to-transparent opacity-60 group-hover:opacity-100" />
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg border border-cyan-300/20 bg-cyan-300/10 text-cyan-200 shadow-[0_0_14px_rgba(76,201,240,0.15)] transition-transform group-hover:scale-105">
          <Icon className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold tracking-wide text-slate-100">
            {title}
          </div>
          <div className="mt-0.5 text-[11px] leading-relaxed text-slate-400">
            {desc}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

// =============================================================================
// Helpers
// =============================================================================

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
