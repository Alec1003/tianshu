import {
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  Eye,
  EyeOff,
  Loader2,
  Lock,
  Mail,
  RotateCw,
  ShieldCheck,
  Zap,
} from "lucide-react";

import { ApiError } from "@/api/client";
import BrandLogo from "@/components/brand/BrandLogo";
import ThemeModeToggle from "@/components/theme/ThemeModeToggle";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useAuth } from "./useAuth";

type Tab = "login" | "register";
type LocationState = { from?: { pathname?: string } } | null;

const VISUAL_NODES = [
  { label: "项目库", position: "left-[8%] top-[34%]" },
  { label: "运行时", position: "left-[78%] top-[25%]" },
  { label: "单位数据", position: "left-[12%] top-[74%]" },
  { label: "参谋工具", position: "left-[84%] top-[68%]" },
];

const TRUST_METRICS = [
  { icon: ShieldCheck, value: "项目", label: "场景工作区" },
  { icon: Zap, value: "运行时", label: "推演同步" },
  { icon: RotateCw, value: "MCP", label: "工具链接入" },
];

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, register } = useAuth();

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
    <main className="min-h-dvh overflow-y-auto overflow-x-hidden bg-tactical-bg text-slate-100 lg:overflow-hidden">
      <div className="relative min-h-dvh overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_16%,rgba(103,199,216,0.07),transparent_30%),radial-gradient(circle_at_74%_24%,rgba(148,163,184,0.06),transparent_34%),linear-gradient(135deg,#0a1018_0%,#04070d_54%,#02050a_100%)]" />
        <div className="absolute inset-0 tactical-grid" />
        <div className="absolute inset-y-0 right-0 w-[32%] bg-tactical-panel/70" />

        <div className="relative grid min-h-dvh w-full grid-cols-1 lg:grid-cols-[minmax(0,7fr)_minmax(430px,3fr)]">
          <section className="relative flex min-h-[360px] flex-col px-6 py-6 sm:min-h-[520px] sm:px-10 lg:min-h-dvh lg:px-16 xl:px-20 2xl:px-24">
            <div className="relative z-20 flex items-center justify-between gap-4">
              <BrandMark />
              <ThemeModeToggle />
            </div>

            <div className="relative z-10 mt-9 max-w-4xl lg:mt-14 xl:mt-16">
              <div className="inline-flex rounded-md border border-tactical-line bg-white/[0.04] px-4 py-1 text-[11px] font-medium tracking-[0.12em] text-slate-300 sm:text-xs">
                TIANSHU COMMAND
              </div>
              <h1 className="mt-6 text-[36px] font-semibold leading-[1.05] tracking-normal text-slate-50 sm:text-[56px] xl:text-[68px]">
                天枢战术推演<span className="text-tactical-accent">控制台</span>
              </h1>
              <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-300 sm:text-base sm:leading-8 lg:text-slate-400">
                连接项目、模板、单位库与运行时，在同一态势图上完成推演控制。
              </p>
            </div>

            <TechVisual />
            <TrustMetrics />
          </section>

          <aside className="relative flex min-h-[420px] items-center justify-center border-t border-tactical-line bg-tactical-panel/82 px-5 py-8 backdrop-blur-sm sm:px-6 lg:min-h-dvh lg:justify-end lg:border-l lg:border-t-0 lg:bg-tactical-panel/70 lg:px-4 xl:px-6 2xl:px-14">
            <LoginPanel
              isRegister={isRegister}
              submitting={submitting}
              error={error}
              email={email}
              password={password}
              showPassword={showPassword}
              onEmailChange={setEmail}
              onPasswordChange={setPassword}
              onTogglePassword={() => setShowPassword((value) => !value)}
              onSwitchTab={switchTab}
              onSubmit={handleSubmit}
            />
          </aside>
        </div>
      </div>
    </main>
  );
}

function BrandMark() {
  return (
    <div className="flex items-center gap-4">
      <BrandLogo
        frameClassName="size-12 rounded-xl border-tactical-line bg-white/[0.04] shadow-none"
        imageClassName="scale-[1.08]"
      />
      <div>
        <div className="text-sm font-semibold tracking-[0.32em] text-slate-50">
          TIANSHU · COMMAND
        </div>
        <div className="mt-1 text-xs tracking-[0.22em] text-slate-500">
          TACTICAL WORKSTATION
        </div>
      </div>
    </div>
  );
}

function TechVisual() {
  return (
    <div
      className="pointer-events-none relative -ml-3 mt-5 hidden h-[340px] w-full max-w-[1120px] overflow-visible sm:block sm:h-[400px] lg:-ml-6 lg:h-[470px] xl:h-[535px] 2xl:h-[590px]"
      aria-hidden="true"
    >
      <div className="absolute inset-x-8 bottom-3 h-[150px] rounded-[50%] bg-[linear-gradient(180deg,transparent,rgba(14,165,233,0.06))]" />
      <div className="absolute left-[49%] top-[56%] h-[430px] w-[980px] -translate-x-1/2 -translate-y-1/2 rounded-[50%] border border-tactical-line" />
      <div className="absolute left-[49%] top-[56%] h-[342px] w-[800px] -translate-x-1/2 -translate-y-1/2 rounded-[50%] border border-cyan-300/18" />
      <div className="absolute left-[49%] top-[56%] h-[254px] w-[610px] -translate-x-1/2 -translate-y-1/2 rounded-[50%] border border-cyan-300/24" />
      <div className="absolute left-[49%] top-[56%] h-[150px] w-[360px] -translate-x-1/2 -translate-y-1/2 rounded-[50%] border border-cyan-200/38" />

      <div className="absolute left-[49%] top-[56%] h-px w-[1040px] -translate-x-1/2 rotate-[-10deg] bg-cyan-300/12" />
      <div className="absolute left-[49%] top-[56%] h-px w-[920px] -translate-x-1/2 rotate-[22deg] bg-cyan-300/12" />
      <div className="absolute left-[49%] top-[56%] h-[500px] w-px -translate-y-1/2 rotate-[3deg] bg-cyan-300/18" />

      <div className="absolute left-[49%] top-[56%] grid size-28 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-2xl border border-cyan-200/45 bg-cyan-300/[0.08] shadow-[0_0_48px_rgba(34,211,238,0.18)]">
        <div className="size-14 rounded-xl border border-cyan-100/50 bg-cyan-300/18 shadow-[0_0_28px_rgba(34,211,238,0.22)]" />
      </div>
      <div className="absolute left-[49%] top-[56%] h-[210px] w-px -translate-x-1/2 -translate-y-full bg-gradient-to-t from-cyan-300/55 to-transparent" />
      <div className="absolute left-[49%] top-[42%] h-[150px] w-[280px] -translate-x-1/2 rounded-[50%] border-t border-cyan-300/20" />

      {VISUAL_NODES.map((node) => (
        <div key={node.label} className={cn("absolute", node.position)}>
          <span className="absolute -left-6 top-3 size-2 rounded-full bg-cyan-300 shadow-[0_0_18px_rgba(34,211,238,0.7)]" />
          <div className="rounded-md border border-tactical-line bg-slate-950/45 px-3 py-1.5 text-xs text-slate-400">
            {node.label}
          </div>
        </div>
      ))}

      <span className="absolute left-[18%] top-[42%] size-2 rounded-full bg-cyan-300 shadow-[0_0_16px_rgba(34,211,238,0.65)]" />
      <span className="absolute left-[35%] top-[34%] size-1.5 rounded-full bg-cyan-200 shadow-[0_0_14px_rgba(125,211,252,0.55)]" />
      <span className="absolute left-[59%] top-[30%] size-2 rounded-full bg-cyan-300 shadow-[0_0_16px_rgba(34,211,238,0.65)]" />
      <span className="absolute left-[68%] top-[61%] size-2 rounded-full bg-cyan-200 shadow-[0_0_14px_rgba(125,211,252,0.55)]" />
      <span className="absolute left-[42%] top-[77%] size-1.5 rounded-full bg-cyan-300 shadow-[0_0_14px_rgba(34,211,238,0.55)]" />
      <span className="absolute left-[83%] top-[49%] size-2.5 rounded-full bg-cyan-300 shadow-[0_0_18px_rgba(34,211,238,0.68)]" />
    </div>
  );
}

function TrustMetrics() {
  return (
    <div className="relative z-10 mt-auto hidden max-w-[760px] grid-cols-3 gap-0 border-t border-tactical-line pt-5 sm:grid lg:pt-6">
      {TRUST_METRICS.map(({ icon: Icon, value, label }, index) => (
        <div
          key={label}
          className={cn(
            "flex items-center gap-3 px-4 first:pl-0 sm:gap-4 sm:px-6",
            index > 0 ? "border-l border-tactical-line" : ""
          )}
        >
          <span className="grid size-10 shrink-0 place-items-center rounded-full border border-tactical-line bg-white/[0.035] text-tactical-accent sm:size-11">
            <Icon className="size-4 sm:size-5" />
          </span>
          <div>
            <div className="text-xl font-semibold text-slate-100 sm:text-2xl">
              {value}
            </div>
            <div className="mt-1 text-xs text-slate-500">{label}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function LoginPanel({
  isRegister,
  submitting,
  error,
  email,
  password,
  showPassword,
  onEmailChange,
  onPasswordChange,
  onTogglePassword,
  onSwitchTab,
  onSubmit,
}: {
  isRegister: boolean;
  submitting: boolean;
  error: string | null;
  email: string;
  password: string;
  showPassword: boolean;
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onTogglePassword: () => void;
  onSwitchTab: (tab: Tab) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  return (
    <Card className="w-full max-w-[410px] overflow-hidden border-tactical-line bg-tactical-panel/78 shadow-[0_24px_80px_rgba(0,0,0,0.28)] backdrop-blur-xl">
      <div className="px-8 pb-8 pt-9">
        <div className="text-center">
          <h2 className="text-2xl font-semibold tracking-normal text-slate-50">
            {isRegister ? "创建账户" : "欢迎回来"}
          </h2>
          <p className="mt-3 text-sm leading-6 text-slate-400">
            {isRegister
              ? "注册后进入 TianShu Command 平台"
              : "登录以继续使用 TianShu Command 平台"}
          </p>
        </div>

        <div className="mt-8 grid grid-cols-2 border-b border-sky-300/10">
          <PanelTabButton
            active={!isRegister}
            onClick={() => onSwitchTab("login")}
          >
            登录
          </PanelTabButton>
          <PanelTabButton
            active={isRegister}
            onClick={() => onSwitchTab("register")}
          >
            注册
          </PanelTabButton>
        </div>

        <form className="mt-8 space-y-5" onSubmit={onSubmit}>
          <AuthField
            icon={<Mail className="size-4" />}
            label="邮箱"
            htmlFor="auth-email"
          >
            <input
              id="auth-email"
              type="email"
              required
              autoCapitalize="none"
              autoComplete="email"
              autoCorrect="off"
              value={email}
              onChange={(event) => onEmailChange(event.target.value)}
              placeholder="请输入邮箱"
              className="h-12 w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-500"
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
                onClick={onTogglePassword}
                className="grid size-9 place-items-center rounded-md text-slate-400 transition-colors hover:bg-white/[0.06] hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tactical-accent/55"
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
              autoComplete={isRegister ? "new-password" : "current-password"}
              value={password}
              onChange={(event) => onPasswordChange(event.target.value)}
              placeholder={isRegister ? "请设置登录密码" : "请输入密码"}
              className="h-12 w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-500"
            />
          </AuthField>

          {error ? (
            <div
              className="rounded-md border border-red-400/25 bg-red-500/[0.08] px-3 py-2 text-xs leading-5 text-red-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.035)]"
              role="alert"
            >
              <span className="font-medium">无法继续：</span>
              {error}
            </div>
          ) : null}

          <Button
            aria-busy={submitting}
            className="h-12 w-full border-sky-300/35 bg-[linear-gradient(90deg,#0ea5e9,#2563eb)] text-sm text-white shadow-[0_0_28px_rgba(37,99,235,0.24)] hover:border-sky-200/60 hover:brightness-110"
            disabled={submitting}
            type="submit"
          >
            {submitting ? <Loader2 className="size-4 animate-spin" /> : null}
            {submitting
              ? isRegister
                ? "正在创建"
                : "正在登录"
              : isRegister
                ? "注册"
                : "登录"}
          </Button>
        </form>

        <div className="mt-7 text-center text-xs text-slate-500">
          {isRegister ? "已有账户？" : "还没有账户？"}
          <button
            type="button"
            onClick={() => onSwitchTab(isRegister ? "login" : "register")}
            className="ml-2 font-medium text-cyan-300 transition-colors hover:text-cyan-100"
          >
            {isRegister ? "返回登录" : "立即注册"}
          </button>
        </div>
      </div>
    </Card>
  );
}

function PanelTabButton({
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
        "relative h-12 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tactical-accent/55 focus-visible:ring-offset-2 focus-visible:ring-offset-[#071323]",
        active ? "text-cyan-300" : "text-slate-400 hover:text-slate-200"
      )}
    >
      {children}
      <span
        className={cn(
          "absolute bottom-[-1px] left-0 h-px w-full transition-colors",
          active ? "bg-cyan-300" : "bg-transparent"
        )}
      />
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
        <span className="font-medium text-slate-200">{label}</span>
        {hint ? <span className="text-xs text-slate-500">{hint}</span> : null}
      </div>
      <div className="flex items-center gap-3 rounded-md border border-slate-500/25 bg-slate-900/45 px-4 transition-colors focus-within:border-cyan-300/55 focus-within:shadow-[0_0_0_3px_rgba(34,211,238,0.09),0_0_26px_rgba(14,165,233,0.16)]">
        <span className="grid size-8 shrink-0 place-items-center text-slate-400">
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
