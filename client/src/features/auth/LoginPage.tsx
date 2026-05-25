import {
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  BrainCircuit,
  Cpu,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  Mail,
  Network,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useAuth } from "./useAuth";

type Tab = "login" | "register";
type LocationState = { from?: { pathname?: string } } | null;

const PLATFORM_POINTS = [
  {
    icon: BrainCircuit,
    label: "智能推演",
    text: "面向复杂场景的辅助分析与决策生成。",
  },
  {
    icon: Network,
    label: "协同空间",
    text: "把数据、模型与人类判断组织在同一工作流。",
  },
  {
    icon: ShieldCheck,
    label: "可信运行",
    text: "清晰的身份边界与可追溯的平台访问。",
  },
];

const PARTICLES = [
  "left-[12%] top-[18%]",
  "left-[31%] top-[72%]",
  "left-[48%] top-[28%]",
  "left-[66%] top-[58%]",
  "left-[82%] top-[22%]",
  "left-[88%] top-[78%]",
];

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, register } = useAuth();
  const reduceMotion = useReducedMotion();

  const initialTab: Tab =
    location.pathname === "/register" ? "register" : "login";
  const [tab, setTab] = useState<Tab>(initialTab);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTab(location.pathname === "/register" ? "register" : "login");
  }, [location.pathname]);

  useEffect(() => {
    setError(null);
  }, [tab]);

  const postLoginTarget = useMemo(() => {
    const state = location.state as LocationState;
    return state?.from?.pathname ?? "/scenarios";
  }, [location.state]);

  const switchTab = (next: Tab) => {
    setTab(next);
    const nextPath = next === "register" ? "/register" : "/login";
    if (location.pathname !== nextPath) {
      navigate(nextPath, { replace: true, state: location.state });
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);

    if (tab === "register" && password.length < 8) {
      setError("密码至少需要 8 位。");
      return;
    }

    setSubmitting(true);
    try {
      if (tab === "login") {
        await login(email.trim(), password);
      } else {
        await register(email.trim(), password);
      }
      navigate(postLoginTarget, { replace: true });
    } catch (err) {
      setError(humanizeError(err, tab));
    } finally {
      setSubmitting(false);
    }
  };

  const isRegister = tab === "register";

  return (
    <main className="dark relative min-h-screen overflow-hidden bg-[#020612] text-slate-100">
      <AuthBackground reduce={reduceMotion ?? false} />

      <div className="relative z-10 min-h-screen">
        <GlobalOrbitField reduce={reduceMotion ?? false} />

        <section className="pointer-events-none absolute inset-0 z-10 hidden min-h-screen overflow-hidden px-10 py-8 lg:flex xl:px-16">
          <div className="flex w-full flex-col justify-between pr-[440px] xl:pr-[520px] 2xl:pr-[600px]">
            <BrandMark />

            <div className="max-w-4xl">
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
              >
                <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs text-slate-300 shadow-[0_0_40px_rgba(56,189,248,0.08)] backdrop-blur-xl">
                  <Sparkles className="size-3.5 text-cyan-300" />
                  AI Native Scenario Intelligence
                </div>

                <h1 className="max-w-[760px] text-[40px] font-semibold leading-[1.05] text-white sm:text-[52px] xl:text-[62px]">
                  <span className="block">以更少界面，</span>
                  <span className="block bg-gradient-to-r from-cyan-200 via-sky-300 to-blue-400 bg-clip-text text-transparent">
                    驱动更清晰的
                  </span>
                  <span className="block bg-gradient-to-r from-cyan-100 via-sky-300 to-blue-400 bg-clip-text text-transparent">
                    智能决策。
                  </span>
                </h1>

                <p className="mt-5 max-w-[620px] text-base leading-7 text-slate-400">
                  AICC 将场景、模型与推演流程连接成一个克制、高效、可协作的 AI
                  平台。
                </p>
              </motion.div>

              <div className="h-[260px]" />
            </div>

            <div className="pointer-events-auto grid max-w-4xl grid-cols-3 gap-6 border-t border-white/10 pt-5">
              {PLATFORM_POINTS.map((item, index) => (
                <PlatformPoint key={item.label} index={index} {...item} />
              ))}
            </div>
          </div>
        </section>

        <section className="relative z-20 ml-auto flex min-h-screen flex-col items-center justify-center px-5 py-8 sm:px-8 lg:w-[470px] lg:items-stretch lg:px-10 xl:mr-10">
          <div className="mb-8 flex w-full max-w-[420px] flex-col lg:hidden">
            <BrandMark />
          </div>

          <motion.div
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
            className="w-full max-w-[420px]"
          >
            <Card className="relative overflow-hidden rounded-[24px] border-white/[0.12] bg-[#07111f]/75 shadow-[0_24px_90px_rgba(0,0,0,0.42),0_0_0_1px_rgba(125,211,252,0.06)] backdrop-blur-2xl">
              <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(56,189,248,0.18),transparent_36%),linear-gradient(180deg,rgba(255,255,255,0.055),transparent_34%)]" />
              <div className="pointer-events-none absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-cyan-200/70 to-transparent" />

              <div className="relative p-6 sm:p-8">
                <div className="mb-8">
                  <div className="mb-6 inline-flex rounded-full border border-white/10 bg-white/[0.035] p-1">
                    <TabButton
                      active={!isRegister}
                      onClick={() => switchTab("login")}
                    >
                      登录
                    </TabButton>
                    <TabButton
                      active={isRegister}
                      onClick={() => switchTab("register")}
                    >
                      注册
                    </TabButton>
                  </div>

                  <AnimatePresence mode="wait" initial={false}>
                    <motion.div
                      key={tab}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      transition={{ duration: 0.18, ease: "easeOut" }}
                    >
                      <p className="text-sm font-medium text-cyan-200/90">
                        {isRegister ? "创建访问身份" : "欢迎回来"}
                      </p>
                      <h2 className="mt-2 text-2xl font-semibold tracking-normal text-white">
                        {isRegister ? "开始使用 AICC" : "登录 AICC AI 平台"}
                      </h2>
                      <p className="mt-3 text-sm leading-6 text-slate-400">
                        {isRegister
                          ? "使用邮箱和密码创建账户，进入统一的智能推演工作区。"
                          : "使用你的邮箱和密码继续进入工作区。"}
                      </p>
                    </motion.div>
                  </AnimatePresence>
                </div>

                <form onSubmit={handleSubmit} className="space-y-5">
                  <AuthField
                    icon={<Mail className="size-4" />}
                    label="邮箱"
                    htmlFor="auth-email"
                  >
                    <input
                      id="auth-email"
                      type="email"
                      required
                      autoComplete="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder="name@example.com"
                      className="h-12 w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-600"
                    />
                  </AuthField>

                  <AuthField
                    icon={<Lock className="size-4" />}
                    label="密码"
                    htmlFor="auth-password"
                    hint={isRegister ? "至少 8 位" : undefined}
                    trailing={
                      <button
                        type="button"
                        onClick={() => setShowPassword((value) => !value)}
                        className="grid size-9 place-items-center rounded-lg text-slate-500 transition-colors hover:bg-white/[0.06] hover:text-slate-200"
                        aria-label={showPassword ? "隐藏密码" : "显示密码"}
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
                      id="auth-password"
                      type={showPassword ? "text" : "password"}
                      required
                      minLength={isRegister ? 8 : undefined}
                      autoComplete={
                        isRegister ? "new-password" : "current-password"
                      }
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      placeholder={isRegister ? "设置登录密码" : "输入登录密码"}
                      className="h-12 w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-600"
                    />
                  </AuthField>

                  <AnimatePresence initial={false}>
                    {error && (
                      <motion.div
                        initial={{ opacity: 0, y: -6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -6 }}
                        className="rounded-xl border border-red-400/25 bg-red-500/[0.08] px-4 py-3 text-sm leading-6 text-red-100"
                      >
                        {error}
                      </motion.div>
                    )}
                  </AnimatePresence>

                  <Button
                    type="submit"
                    disabled={submitting}
                    className="group relative h-12 w-full overflow-hidden rounded-xl border border-cyan-200/20 bg-gradient-to-r from-cyan-400 via-sky-500 to-blue-600 text-sm font-semibold text-white shadow-[0_16px_42px_rgba(14,165,233,0.28)] hover:border-cyan-100/40 hover:shadow-[0_20px_56px_rgba(14,165,233,0.38)]"
                  >
                    <span className="pointer-events-none absolute inset-0 -translate-x-full bg-[linear-gradient(120deg,transparent,rgba(255,255,255,0.36),transparent)] transition-transform duration-700 group-hover:translate-x-full" />
                    <span className="relative flex items-center gap-2">
                      {submitting && (
                        <Loader2 className="size-4 animate-spin" />
                      )}
                      {submitting
                        ? isRegister
                          ? "正在创建..."
                          : "正在登录..."
                        : isRegister
                          ? "创建账户"
                          : "继续登录"}
                    </span>
                    {!submitting && (
                      <ArrowRight className="relative ml-1 size-4 transition-transform group-hover:translate-x-0.5" />
                    )}
                  </Button>
                </form>

                <div className="mt-6 text-center text-sm text-slate-500">
                  {isRegister ? "已有账户？" : "还没有账户？"}
                  <button
                    type="button"
                    onClick={() => switchTab(isRegister ? "login" : "register")}
                    className="ml-2 font-medium text-cyan-200 transition-colors hover:text-white"
                  >
                    {isRegister ? "返回登录" : "立即注册"}
                  </button>
                </div>
              </div>
            </Card>
          </motion.div>
        </section>
      </div>
    </main>
  );
}

function AuthBackground({ reduce }: { reduce: boolean }) {
  return (
    <>
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(circle at 18% 18%, rgba(14,165,233,0.18), transparent 30%), radial-gradient(circle at 78% 22%, rgba(59,130,246,0.16), transparent 28%), radial-gradient(circle at 52% 94%, rgba(8,47,73,0.48), transparent 42%), linear-gradient(135deg, #020612 0%, #06101d 48%, #02040b 100%)",
        }}
      />
      <div className="pointer-events-none absolute inset-0 tactical-grid opacity-[0.36]" />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,rgba(2,6,18,0.86)_0%,rgba(2,6,18,0.34)_48%,rgba(2,6,18,0.76)_100%)]" />
      {!reduce && (
        <motion.div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-40"
          animate={{ backgroundPosition: ["0% 0%", "100% 100%"] }}
          transition={{ duration: 22, ease: "linear", repeat: Infinity }}
          style={{
            backgroundImage:
              "linear-gradient(115deg, transparent 0%, rgba(125,211,252,0.08) 45%, transparent 58%)",
            backgroundSize: "220% 220%",
          }}
        />
      )}
      {PARTICLES.map((position, index) => (
        <motion.span
          key={position}
          aria-hidden
          className={cn(
            "pointer-events-none absolute size-1 rounded-full bg-cyan-200/70 shadow-[0_0_18px_rgba(125,211,252,0.75)]",
            position
          )}
          animate={
            reduce
              ? undefined
              : { opacity: [0.28, 0.82, 0.28], scale: [1, 1.35, 1] }
          }
          transition={{
            duration: 4.5 + index * 0.4,
            ease: "easeInOut",
            repeat: Infinity,
          }}
        />
      ))}
    </>
  );
}

function BrandMark() {
  return (
    <div className="flex items-center gap-3">
      <div className="relative grid size-11 place-items-center rounded-2xl border border-cyan-200/20 bg-white/[0.04] shadow-[0_0_32px_rgba(56,189,248,0.16)] backdrop-blur-xl">
        <div className="absolute inset-2 rounded-xl bg-gradient-to-br from-cyan-300/25 to-blue-500/20" />
        <Cpu className="relative size-5 text-cyan-100" strokeWidth={1.6} />
      </div>
      <div>
        <div className="text-sm font-semibold tracking-[0.34em] text-white">
          AICC
        </div>
        <div className="mt-1 text-xs tracking-[0.18em] text-slate-500">
          AI PLATFORM
        </div>
      </div>
    </div>
  );
}

function GlobalOrbitField({ reduce }: { reduce: boolean }) {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 z-0 hidden overflow-hidden lg:block"
    >
      <div className="absolute left-[44%] top-[57%] h-[560px] w-[980px] -translate-x-1/2 -translate-y-1/2">
        <div className="absolute left-1/2 top-1/2 size-32 -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-200/20 bg-cyan-300/[0.06] shadow-[0_0_110px_rgba(56,189,248,0.24)]" />
        <div className="absolute left-1/2 top-1/2 size-12 -translate-x-1/2 -translate-y-1/2 rounded-full bg-gradient-to-br from-cyan-100 to-blue-500 shadow-[0_0_54px_rgba(14,165,233,0.58)]" />

        {[0, 1, 2, 3].map((index) => (
          <motion.div
            key={index}
            className="absolute left-1/2 top-1/2 rounded-[50%] border border-cyan-200/[0.12]"
            style={{
              width: 310 + index * 154,
              height: 118 + index * 70,
              marginLeft: -(310 + index * 154) / 2,
              marginTop: -(118 + index * 70) / 2,
              rotate: `${-18 + index * 14}deg`,
            }}
            animate={reduce ? undefined : { rotate: 342 + index * 14 }}
            transition={{
              duration: 42 + index * 12,
              ease: "linear",
              repeat: Infinity,
            }}
          />
        ))}

        {[
          "left-[28%] top-[35%]",
          "left-[68%] top-[39%]",
          "left-[40%] top-[70%]",
          "left-[83%] top-[58%]",
        ].map((position, index) => (
          <motion.span
            key={position}
            className={cn(
              "absolute size-2 rounded-full bg-cyan-100 shadow-[0_0_22px_rgba(125,211,252,0.9)]",
              position
            )}
            animate={reduce ? undefined : { opacity: [0.38, 1, 0.38] }}
            transition={{
              duration: 2.8 + index * 0.7,
              repeat: Infinity,
              ease: "easeInOut",
            }}
          />
        ))}

        <div className="absolute inset-x-8 top-1/2 h-px bg-gradient-to-r from-transparent via-cyan-200/28 to-transparent" />
        <div className="absolute inset-y-6 left-1/2 w-px bg-gradient-to-b from-transparent via-cyan-200/18 to-transparent" />
        <div className="absolute -right-28 top-1/2 h-[420px] w-[420px] -translate-y-1/2 rounded-full bg-sky-500/[0.07] blur-3xl" />
      </div>
    </div>
  );
}

function PlatformPoint({
  icon: Icon,
  label,
  text,
  index,
}: (typeof PLATFORM_POINTS)[number] & { index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        delay: 0.18 + index * 0.08,
        duration: 0.45,
        ease: [0.22, 1, 0.36, 1],
      }}
      className="min-w-0"
    >
      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-100">
        <span className="grid size-8 place-items-center rounded-lg border border-white/10 bg-white/[0.035] text-cyan-200">
          <Icon className="size-4" />
        </span>
        {label}
      </div>
      <p className="text-xs leading-6 text-slate-500">{text}</p>
    </motion.div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "relative h-9 rounded-full px-5 text-sm font-medium transition-colors",
        active ? "text-white" : "text-slate-500 hover:text-slate-200"
      )}
    >
      {active && (
        <motion.span
          layoutId="auth-mode-pill"
          className="absolute inset-0 rounded-full border border-white/10 bg-white/[0.08] shadow-[0_0_28px_rgba(56,189,248,0.12)]"
          transition={{ type: "spring", stiffness: 420, damping: 34 }}
        />
      )}
      <span className="relative">{children}</span>
    </button>
  );
}

function AuthField({
  icon,
  label,
  htmlFor,
  hint,
  trailing,
  children,
}: {
  icon: ReactNode;
  label: string;
  htmlFor: string;
  hint?: string;
  trailing?: ReactNode;
  children: ReactNode;
}) {
  return (
    <label className="block" htmlFor={htmlFor}>
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="font-medium text-slate-300">{label}</span>
        {hint && <span className="text-xs text-slate-600">{hint}</span>}
      </div>
      <div className="group flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.035] px-3 transition-all duration-200 focus-within:border-cyan-200/45 focus-within:bg-cyan-200/[0.035] focus-within:shadow-[0_0_0_1px_rgba(125,211,252,0.18),0_0_30px_rgba(14,165,233,0.16)]">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg text-slate-500 transition-colors group-focus-within:text-cyan-200">
          {icon}
        </span>
        <div className="min-w-0 flex-1">{children}</div>
        {trailing}
      </div>
    </label>
  );
}

function humanizeError(err: unknown, tab: Tab): string {
  if (!(err instanceof ApiError)) return "操作失败，请稍后重试。";

  const detail =
    typeof err.detail === "object" && err.detail !== null
      ? (err.detail as { detail?: unknown }).detail
      : null;
  const code =
    typeof detail === "string"
      ? detail
      : ((detail as { code?: string } | null)?.code ?? null);

  if (tab === "login") {
    if (code === "LOGIN_BAD_CREDENTIALS") return "邮箱或密码不正确。";
    if (code === "LOGIN_USER_NOT_VERIFIED") return "账户尚未验证。";
  } else {
    if (code === "REGISTER_USER_ALREADY_EXISTS") return "该邮箱已注册。";
    if (code === "REGISTER_INVALID_PASSWORD") return "密码不符合安全要求。";
  }

  return err.message || "操作失败，请稍后重试。";
}
