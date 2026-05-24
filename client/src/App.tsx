import { Component, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import LoginPage from "@/features/auth/LoginPage";
import RequireAuth from "@/features/auth/RequireAuth";
import AIModelConfigPage from "@/features/ai/AIModelConfigPage";
import PlayScenarioPage from "@/features/scenarios/PlayScenarioPage";
import ScenarioListPage from "@/features/scenarios/ScenarioListPage";

interface ErrorBoundaryState {
  error: Error | null;
}

class AppErrorBoundary extends Component<
  { children: ReactNode },
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div
          style={{
            height: "100vh",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            background: "#050914",
            color: "#e2e8f0",
            fontFamily: "monospace",
            gap: 16,
            padding: 32,
          }}
        >
          <div style={{ fontSize: 18, color: "#f87171" }}>页面发生错误</div>
          <div
            style={{
              fontSize: 12,
              color: "#64748b",
              maxWidth: 480,
              textAlign: "center",
            }}
          >
            {this.state.error.message}
          </div>
          <button
            onClick={() => window.location.assign("/scenarios")}
            style={{
              marginTop: 8,
              padding: "8px 20px",
              borderRadius: 8,
              border: "1px solid rgba(125,211,252,0.3)",
              background: "rgba(125,211,252,0.1)",
              color: "#7dd3fc",
              cursor: "pointer",
            }}
          >
            返回项目列表
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// 路由总览：
//   /                 -> /scenarios（默认入口）
//   /login            -> 登录
//   /register         -> 注册
//   /scenarios        -> 我的想定 + 系统模板（需登录）
//   /play/:scenarioId -> 推演界面（需登录）
//   *                 -> /scenarios（兜底）
export default function App() {
  return (
    <AppErrorBoundary>
      <Routes>
        <Route path="/" element={<Navigate to="/scenarios" replace />} />
        {/* /login 与 /register 走同一组件，组件内部按 pathname 切到对应 tab。 */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<LoginPage />} />
        <Route
          path="/scenarios"
          element={
            <RequireAuth>
              <ScenarioListPage />
            </RequireAuth>
          }
        />
        <Route
          path="/ai-models"
          element={
            <RequireAuth>
              <AIModelConfigPage />
            </RequireAuth>
          }
        />
        <Route
          path="/play/:scenarioId"
          element={
            <RequireAuth>
              <PlayScenarioPage />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/scenarios" replace />} />
      </Routes>
    </AppErrorBoundary>
  );
}
