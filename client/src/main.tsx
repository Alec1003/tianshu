import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "@/styles/index.css";
import "@/i18n";
import App from "./App.tsx";
import { AppProvider } from "@/gui/contextProviders/providers/AppProvider";
import { AuthProvider } from "@/features/auth/AuthContext";

// 路由 + 认证 + 应用上下文嵌套顺序：
//  - BrowserRouter 必须在 AuthProvider 外，因为 AuthProvider 需要 useNavigate
//    访问（路由守卫和退出登录会用到）。
//  - AppProvider 仍然包住 <App>，提供 ScenarioTime 等领域上下文。
createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <AuthProvider>
      <AppProvider>
        <App />
      </AppProvider>
    </AuthProvider>
  </BrowserRouter>
);
