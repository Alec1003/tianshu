import { Navigate, Route, Routes } from "react-router-dom";

import LoginPage from "@/features/auth/LoginPage";
import RegisterPage from "@/features/auth/RegisterPage";
import RequireAuth from "@/features/auth/RequireAuth";
import PlayScenarioPage from "@/features/scenarios/PlayScenarioPage";
import ScenarioListPage from "@/features/scenarios/ScenarioListPage";

// 路由总览：
//   /                 -> /scenarios（默认入口）
//   /login            -> 登录
//   /register         -> 注册
//   /scenarios        -> 我的想定 + 系统模板（需登录）
//   /play/:scenarioId -> 推演界面（需登录）
//   *                 -> /scenarios（兜底）
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/scenarios" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        path="/scenarios"
        element={
          <RequireAuth>
            <ScenarioListPage />
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
  );
}
