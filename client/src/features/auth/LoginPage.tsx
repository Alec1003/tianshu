// 登录 + 注册 Tab 合一页面（按设计图）。
//
// 视觉策略：
//   - 整页 50/50 分屏，左侧品牌 + feature 介绍，右侧表单卡片。
//   - 全程 Tailwind 暗色 cyan HUD 风格，复用 tactical-grid / shadow-hud-cyan
//     等项目已有 token，避免引入新 UI 库。
//   - "/login" 默认进入登录 tab，"/register" 进入注册 tab；二者共用同一组件
//     以省去重复布局。
//
// 注意：忘记密码 + SSO/钉钉/企业微信 在 v1 仅占位，点击给出 toast 提示。

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
import {
  Brain,
  Eye,
  EyeOff,
  Globe,
  Lock,
  Mail,
  MessageSquare,
  Moon,
  Network,
  Radar,
  ShieldCheck,
  Sparkles,
  User as UserIcon,
} from "lucide-react";

import { ApiError } from "@/api/client";
import { cn } from "@/lib/utils";
import { useAuth } from "./AuthContext";

type Tab = "login" | "register";

type LocationState = { from?: { pathname?: string } } | null;

const FEATURES: Array<{
  icon: typeof Brain;
  title: string;
  desc: string;
}> = [
  {
    icon: Radar,
    title: "实时态势感知",
    desc: "多源数据融合,战场态势一目了然",
  },
  {
    icon: Brain,
    title: "智能辅助决策",
    desc: "AI 算法驱动,提供最优作战方案",
  },
  {
    icon: Sparkles,
    title: "仿真推演系统",
    desc: "高精度仿真推演,预见战场未来",
  },
  {
    icon: Network,
    title: "多域协同作战",
    desc: "陆海空天电多域协同,体系化作战",
  },
];

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, register } = useAuth();

  // /register 进入直接选中注册 tab，/login 选中登录 tab。
  const initialTab: Tab = location.pathname === "/register" ? "register" : "login";
  const [tab, setTab] = useState<Tab>(initialTab);
  useEffect(() => {
    setTab(location.pathname === "/register" ? "register" : "login");
  }, [location.pathname]);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);

  // 注册专用字段
  const [displayName, setDisplayName] = useState("");
  const [password2, setPassword2] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  // 切 tab 时清错误，但保留邮箱（提升体验）
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
        setError("密码至少 8 位");
        return;
      }
      if (password !== password2) {
        setError("两次输入的密码不一致");
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
    <div className="dark relative min-h-screen overflow-hidden bg-[#050914] text-slate-100">
      {/* 背景网格 + 几个柔光圆，呈现指挥中心氛围 */}
      <div className="pointer-events-none absolute inset-0 tactical-grid opacity-50" />
      <div
        className="pointer-events-none absolute -left-40 top-1/3 h-[36rem] w-[36rem] rounded-full opacity-60 blur-3xl"
        style={{
          background:
            "radial-gradient(closest-side, rgba(56,189,248,0.18), transparent 70%)",
        }}
      />
      <div
        className="pointer-events-none absolute -right-40 -top-40 h-[40rem] w-[40rem] rounded-full opacity-40 blur-3xl"
        style={{
          background:
            "radial-gradient(closest-side, rgba(99,102,241,0.18), transparent 70%)",
        }}
      />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-[#050914] via-[#050914]/60 to-transparent" />

      {/* 顶部右上：主题切换按钮（v1 占位） */}
      <button
        type="button"
        title="主题切换 (v1 暂未开放)"
        onClick={() => setInfo("主题切换将在后续版本开放")}
        className="absolute right-6 top-6 z-20 inline-flex items-center gap-1 rounded-full border border-cyan-300/20 bg-white/5 px-2 py-1 text-xs text-slate-300 hover:bg-white/10"
      >
        <Sparkles className="size-3.5 text-cyan-300" />
        <Moon className="size-3.5" />
      </button>

      <div className="relative z-10 mx-auto flex min-h-screen max-w-7xl flex-col px-6 py-8 lg:flex-row lg:items-stretch lg:gap-10">
        {/* ============== 左侧：品牌 + 介绍 ============== */}
        <section className="flex flex-1 flex-col justify-between pb-10 pt-2 lg:py-6">
          <div>
            <Brand />
            <h1 className="mt-12 max-w-xl text-3xl font-semibold leading-tight text-slate-50 sm:text-4xl lg:text-[2.4rem]">
              智能决策 · 精准指挥
              <br />
              掌控
              <span className="bg-gradient-to-r from-cyan-300 to-sky-400 bg-clip-text text-transparent">
                战场
              </span>
              每一个瞬间
            </h1>
            <p className="mt-3 text-sm text-slate-400">
              AI 驱动的下一代作战指挥控制系统
            </p>

            <ul className="mt-10 grid max-w-xl grid-cols-1 gap-3 sm:grid-cols-2">
              {FEATURES.map(({ icon: Icon, title, desc }) => (
                <li
                  key={title}
                  className="group flex items-start gap-3 rounded-2xl border border-cyan-300/10 bg-white/[0.02] px-4 py-3 backdrop-blur-sm transition-colors hover:border-cyan-300/25 hover:bg-white/[0.04]"
                >
                  <span className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-xl border border-cyan-300/15 bg-cyan-300/10 text-cyan-200">
                    <Icon className="size-4" />
                  </span>
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-slate-100">
                      {title}
                    </div>
                    <div className="mt-0.5 text-xs leading-relaxed text-slate-400">
                      {desc}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <blockquote className="mt-10 max-w-md border-l-2 border-cyan-300/30 pl-4 text-xs leading-relaxed text-slate-400">
            在不确定的战场环境中，
            <br />
            我们提供确定的决策支持。
            <div className="mt-1 text-[10px] tracking-[0.18em] text-cyan-200/70">
              AICC COMMAND
            </div>
          </blockquote>
        </section>

        {/* ============== 右侧：表单卡片 ============== */}
        <section className="flex w-full flex-col items-center justify-center lg:w-[28rem] xl:w-[32rem]">
          <div className="w-full rounded-3xl border border-cyan-300/15 bg-[#0a1224]/85 p-7 shadow-hud-cyan backdrop-blur-md sm:p-9">
            {/* Tab 头 */}
            <div className="grid grid-cols-2 gap-1 border-b border-cyan-300/10">
              <TabButton
                active={tab === "login"}
                onClick={() => setTab("login")}
                title="登录"
                subtitle="欢迎回来,指挥官"
              />
              <TabButton
                active={tab === "register"}
                onClick={() => setTab("register")}
                title="注册"
                subtitle="创建新账户"
              />
            </div>

            <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
              <Field
                icon={<UserIcon className="size-4" />}
                label="账号"
              >
                <input
                  type="email"
                  required
                  autoComplete="email"
                  placeholder="请输入账号或邮箱"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-transparent text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none"
                />
              </Field>

              {tab === "register" && (
                <Field
                  icon={<Mail className="size-4" />}
                  label="昵称（可选）"
                >
                  <input
                    type="text"
                    maxLength={80}
                    autoComplete="nickname"
                    placeholder="例如：王指挥"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    className="w-full bg-transparent text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none"
                  />
                </Field>
              )}

              <Field
                icon={<Lock className="size-4" />}
                label="密码"
                trailing={
                  <button
                    type="button"
                    title={showPassword ? "隐藏密码" : "显示密码"}
                    onClick={() => setShowPassword((v) => !v)}
                    className="grid size-7 place-items-center rounded-md text-slate-400 hover:bg-white/10 hover:text-slate-200"
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
                  placeholder={
                    tab === "register" ? "至少 8 位" : "请输入密码"
                  }
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-transparent text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none"
                />
              </Field>

              {tab === "register" && (
                <Field
                  icon={<Lock className="size-4" />}
                  label="再次输入密码"
                >
                  <input
                    type={showPassword ? "text" : "password"}
                    required
                    minLength={8}
                    autoComplete="new-password"
                    placeholder="再次输入以确认"
                    value={password2}
                    onChange={(e) => setPassword2(e.target.value)}
                    className="w-full bg-transparent text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none"
                  />
                </Field>
              )}

              {tab === "login" && (
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <label className="flex select-none items-center gap-2">
                    <input
                      type="checkbox"
                      className="size-3.5 accent-cyan-400"
                      checked={rememberMe}
                      onChange={(e) => setRememberMe(e.target.checked)}
                    />
                    记住我
                  </label>
                  <button
                    type="button"
                    onClick={() => setInfo("找回密码功能将在 v2 开放，请联系管理员重置")}
                    className="text-cyan-300/80 hover:text-cyan-200"
                  >
                    忘记密码？
                  </button>
                </div>
              )}

              {(error || info) && (
                <div
                  className={cn(
                    "rounded-lg border px-3 py-2 text-xs",
                    error
                      ? "border-red-500/30 bg-red-500/10 text-red-200"
                      : "border-cyan-300/25 bg-cyan-300/10 text-cyan-100"
                  )}
                >
                  {error ?? info}
                </div>
              )}

              <button
                type="submit"
                disabled={submitting}
                className="mt-2 flex w-full items-center justify-center rounded-xl bg-gradient-to-r from-cyan-400 to-sky-400 py-2.5 text-sm font-semibold text-slate-950 shadow-hud-cyan transition-opacity hover:opacity-95 disabled:opacity-60"
              >
                {submitting
                  ? tab === "login"
                    ? "登录中…"
                    : "注册中…"
                  : tab === "login"
                    ? "登录"
                    : "注册并登录"}
              </button>

              {/* 三方登录区（v1 占位） */}
              <div className="pt-2">
                <div className="relative my-2 text-center">
                  <span className="relative z-10 bg-[#0a1224]/85 px-3 text-[11px] text-slate-500">
                    或使用以下方式登录
                  </span>
                  <span className="absolute inset-x-0 top-1/2 -z-0 h-px bg-cyan-300/10" />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <SsoButton
                    icon={<ShieldCheck className="size-4" />}
                    label="SSO 登录"
                    onClick={() =>
                      setInfo("SSO 登录将在企业部署版开放")
                    }
                  />
                  <SsoButton
                    icon={<Globe className="size-4" />}
                    label="钉钉登录"
                    onClick={() => setInfo("钉钉扫码登录将在 v2 开放")}
                  />
                  <SsoButton
                    icon={<MessageSquare className="size-4" />}
                    label="企业微信"
                    onClick={() => setInfo("企业微信登录将在 v2 开放")}
                  />
                </div>
              </div>

              <p className="mt-3 text-center text-[11px] leading-relaxed text-slate-500">
                {tab === "login" ? "登录" : "注册"}即表示您同意{" "}
                <button
                  type="button"
                  className="text-cyan-300/80 hover:text-cyan-200"
                  onClick={() => setInfo("用户协议文档将在正式发布版本提供")}
                >
                  《用户协议》
                </button>{" "}
                和{" "}
                <button
                  type="button"
                  className="text-cyan-300/80 hover:text-cyan-200"
                  onClick={() => setInfo("隐私政策将在正式发布版本提供")}
                >
                  《隐私政策》
                </button>
              </p>

              {tab === "login" ? (
                <p className="text-center text-[11px] text-slate-500">
                  还没有账户？{" "}
                  <RouterLink
                    to="/register"
                    className="text-cyan-300 hover:text-cyan-200"
                  >
                    立即注册
                  </RouterLink>
                </p>
              ) : (
                <p className="text-center text-[11px] text-slate-500">
                  已有账户？{" "}
                  <RouterLink
                    to="/login"
                    className="text-cyan-300 hover:text-cyan-200"
                  >
                    返回登录
                  </RouterLink>
                </p>
              )}
            </form>
          </div>
        </section>
      </div>

      {/* 底部页脚 */}
      <footer className="relative z-10 mx-auto mt-2 flex max-w-7xl items-center justify-between border-t border-cyan-300/10 px-6 py-4 text-[11px] text-slate-500">
        <span>© 2026 AICC Command. All rights reserved.</span>
        <div className="flex items-center gap-4">
          <button
            type="button"
            className="hover:text-slate-300"
            onClick={() => setInfo("服务条款将在正式发布版本提供")}
          >
            服务条款
          </button>
          <button
            type="button"
            className="hover:text-slate-300"
            onClick={() => setInfo("隐私政策将在正式发布版本提供")}
          >
            隐私政策
          </button>
          <span className="opacity-50">|</span>
          <span>版本 v0.2.0</span>
        </div>
      </footer>
    </div>
  );
}

// ---------- 子组件 ----------

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <div
        className="grid size-11 place-items-center rounded-2xl border border-cyan-300/30 bg-gradient-to-br from-cyan-400/30 to-sky-500/20 text-cyan-100 shadow-hud-cyan"
        aria-hidden
      >
        <Sparkles className="size-5" />
      </div>
      <div>
        <div className="text-base font-semibold tracking-[0.22em] text-slate-100">
          AICC COMMAND
        </div>
        <div className="text-[11px] text-slate-400">AI 指挥控制平台</div>
      </div>
    </div>
  );
}

function TabButton({
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
        "relative flex flex-col items-center justify-center gap-1 px-3 py-3 transition-colors",
        active
          ? "text-cyan-200"
          : "text-slate-400 hover:text-slate-200"
      )}
    >
      <span className="text-base font-medium">{title}</span>
      <span className="text-[11px] text-slate-500">{subtitle}</span>
      {active && (
        <span className="absolute inset-x-6 -bottom-px h-[2px] rounded-full bg-gradient-to-r from-cyan-400 to-sky-400 shadow-[0_0_12px_rgba(56,189,248,0.7)]" />
      )}
    </button>
  );
}

function Field({
  icon,
  label,
  children,
  trailing,
}: {
  icon: ReactNode;
  label: string;
  children: ReactNode;
  trailing?: ReactNode;
}) {
  return (
    <div>
      <div className="mb-1 text-xs text-slate-400">{label}</div>
      <div className="flex items-center gap-2 rounded-xl border border-cyan-300/10 bg-slate-950/40 px-3 py-2.5 transition-colors focus-within:border-cyan-300/40 focus-within:bg-slate-950/55">
        <span className="text-slate-500">{icon}</span>
        <div className="flex-1 min-w-0">{children}</div>
        {trailing}
      </div>
    </div>
  );
}

function SsoButton({
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
      className="flex items-center justify-center gap-1.5 rounded-xl border border-cyan-300/15 bg-white/[0.02] px-2 py-2 text-[11px] text-slate-300 transition-colors hover:border-cyan-300/30 hover:bg-white/[0.05]"
    >
      <span className="text-cyan-300">{icon}</span>
      {label}
    </button>
  );
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
    if (code === "LOGIN_BAD_CREDENTIALS") return "邮箱或密码错误";
    if (code === "LOGIN_USER_NOT_VERIFIED") return "账户尚未验证";
  } else {
    if (code === "REGISTER_USER_ALREADY_EXISTS") return "该邮箱已注册";
    if (code === "REGISTER_INVALID_PASSWORD") return "密码不符合要求";
  }
  return err.message || "操作失败";
}
