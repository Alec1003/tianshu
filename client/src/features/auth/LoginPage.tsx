import {
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  BrainCircuit,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  Mail,
  Network,
  ShieldCheck,
} from "lucide-react";

import { ApiError } from "@/api/client";
import BrandLogo from "@/components/brand/BrandLogo";
import { Badge } from "@/components/ui/badge";
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
    text: "围绕场景、模型、MCP 工具和审批链路组织推演任务。",
  },
  {
    icon: Network,
    label: "统一工作区",
    text: "将项目、模板、单位库和 AI 配置放在同一操作界面。",
  },
  {
    icon: ShieldCheck,
    label: "可信访问",
    text: "登录态、后端运行时和用户操作保持清晰边界。",
  },
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
    <main className="dark h-screen overflow-y-auto bg-[#050812] text-slate-100">
      <div className="tactical-grid mx-auto flex min-h-screen w-full max-w-[1440px] flex-col px-4 py-4 lg:px-5">
        <header className="flex min-h-14 items-center justify-between gap-3 border-b border-cyan-300/10 pb-3">
          <BrandMark />
          <div className="hidden items-center gap-2 sm:flex">
            <Badge variant="info">AI Runtime</Badge>
            <Badge variant="success">Backend Online</Badge>
          </div>
        </header>

        <section className="grid flex-1 items-center gap-4 py-4 lg:grid-cols-[minmax(0,1fr)_420px] xl:grid-cols-[minmax(0,1fr)_460px]">
          <div className="hidden min-h-[560px] flex-col justify-between rounded-lg border border-cyan-300/10 bg-[#08111c] p-5 shadow-[0_1px_0_rgba(255,255,255,0.03)] lg:flex">
            <div>
              <div className="flex items-center gap-2">
                <Badge variant="info">Command Workspace</Badge>
                <Badge variant="offline">v0.2.0</Badge>
              </div>
              <h1 className="mt-5 max-w-2xl text-2xl font-semibold leading-tight tracking-normal text-slate-50 xl:text-3xl">
                天枢 AI 指挥控制平台
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">
                面向战术场景、模型配置、后端运行时和 MCP 工具的统一操作入口。
              </p>

              <div className="mt-6 grid max-w-3xl grid-cols-3 gap-3">
                <LoginMetric label="入口" value="Scenarios" />
                <LoginMetric label="运行边界" value="Backend" />
                <LoginMetric label="身份模式" value="JWT" />
              </div>
            </div>

            <div className="grid gap-3">
              {PLATFORM_POINTS.map((item) => (
                <PlatformPoint key={item.label} {...item} />
              ))}
            </div>
          </div>

          <Card className="mx-auto w-full max-w-[420px] p-5 lg:mx-0 lg:max-w-none">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-medium text-cyan-200">
                  {isRegister ? "创建访问身份" : "访问工作区"}
                </p>
                <h2 className="mt-1 text-lg font-semibold tracking-normal text-slate-50">
                  {isRegister ? "注册天枢平台" : "登录天枢平台"}
                </h2>
              </div>
              <div className="inline-flex rounded-md border border-cyan-300/12 bg-slate-950/55 p-0.5">
                <TabButton active={!isRegister} onClick={() => switchTab("login")}>
                  登录
                </TabButton>
                <TabButton active={isRegister} onClick={() => switchTab("register")}>
                  注册
                </TabButton>
              </div>
            </div>

            <p className="mb-5 text-xs leading-5 text-slate-500">
              {isRegister
                ? "使用邮箱和密码创建账户，随后进入项目管理工作台。"
                : "使用已注册账户继续进入项目、模板和模型配置中心。"}
            </p>

            <form className="space-y-4" onSubmit={handleSubmit}>
              <AuthField icon={<Mail className="size-4" />} label="邮箱" htmlFor="auth-email">
                <input
                  id="auth-email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="name@example.com"
                  className="h-10 w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-600"
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
                    className="grid size-8 place-items-center rounded-md text-slate-500 transition-colors hover:bg-white/[0.06] hover:text-slate-200"
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
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder={isRegister ? "设置登录密码" : "输入登录密码"}
                  className="h-10 w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-600"
                />
              </AuthField>

              {error ? (
                <div className="rounded-md border border-red-400/25 bg-red-500/[0.08] px-3 py-2 text-xs leading-5 text-red-100">
                  {error}
                </div>
              ) : null}

              <Button className="h-10 w-full" disabled={submitting} type="submit">
                {submitting ? <Loader2 className="size-4 animate-spin" /> : null}
                {submitting
                  ? isRegister
                    ? "正在创建"
                    : "正在登录"
                  : isRegister
                    ? "创建账户"
                    : "继续登录"}
                {!submitting ? <ArrowRight className="size-4" /> : null}
              </Button>
            </form>

            <div className="mt-5 border-t border-cyan-300/10 pt-4 text-center text-xs text-slate-500">
              {isRegister ? "已有账户？" : "还没有账户？"}
              <button
                type="button"
                onClick={() => switchTab(isRegister ? "login" : "register")}
                className="ml-2 font-medium text-cyan-200 transition-colors hover:text-cyan-50"
              >
                {isRegister ? "返回登录" : "立即注册"}
              </button>
            </div>
          </Card>
        </section>
      </div>
    </main>
  );
}

function BrandMark() {
  return (
    <div className="flex items-center gap-3">
      <BrandLogo frameClassName="size-10" imageClassName="scale-[1.08]" />
      <div>
        <div className="text-sm font-semibold tracking-normal text-slate-50">
          TianShu
        </div>
        <div className="mt-0.5 text-[11px] text-slate-500">
          AI Command Center
        </div>
      </div>
    </div>
  );
}

function PlatformPoint({
  icon: Icon,
  label,
  text,
}: (typeof PLATFORM_POINTS)[number]) {
  return (
    <div className="flex items-start gap-3 rounded-md border border-cyan-300/10 bg-slate-950/45 p-3">
      <span className="grid size-8 shrink-0 place-items-center rounded-md border border-cyan-300/14 bg-cyan-300/8 text-cyan-200">
        <Icon className="size-4" />
      </span>
      <div className="min-w-0">
        <div className="text-sm font-medium text-slate-100">{label}</div>
        <p className="mt-1 text-xs leading-5 text-slate-500">{text}</p>
      </div>
    </div>
  );
}

function LoginMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-cyan-300/10 bg-slate-950/45 p-3">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-1 truncate text-sm font-medium text-slate-100">
        {value}
      </div>
    </div>
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
        "h-8 rounded px-3 text-xs font-medium transition-colors",
        active ? "bg-cyan-300/12 text-cyan-100" : "text-slate-500 hover:text-slate-200"
      )}
    >
      {children}
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
      <div className="mb-1.5 flex items-center justify-between text-xs">
        <span className="font-medium text-slate-300">{label}</span>
        {hint ? <span className="text-slate-600">{hint}</span> : null}
      </div>
      <div className="flex items-center gap-2 rounded-md border border-cyan-300/12 bg-slate-950/60 px-3 transition-colors focus-within:border-cyan-300/35 focus-within:ring-2 focus-within:ring-cyan-300/10">
        <span className="grid size-8 shrink-0 place-items-center text-slate-500">
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
