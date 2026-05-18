import { createRoot } from "react-dom/client";
import "@/styles/index.css";
import "@/i18n";
import App from "./App.tsx";
import { AppProvider } from "@/gui/contextProviders/providers/AppProvider";

createRoot(document.getElementById("root")!).render(
  <AppProvider>
    <App />
  </AppProvider>
);
