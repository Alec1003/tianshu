import { useMemo } from "react";
import {
  ArrowLeft,
  Bot,
  CheckCircle2,
  FolderKanban,
  Server,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { AppShell, type AppShellNavItem } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { StatCard } from "@/components/ui/stat-card";
import ModelConfigCenter from "./ModelConfigCenter";
import { listModelProviderDefinitions } from "./modelProfiles";
import { useModelConfigStore } from "./modelStore";

export default function AIModelConfigPage() {
  const navigate = useNavigate();
  const definitions = useMemo(listModelProviderDefinitions, []);
  const providerConfigs = useModelConfigStore((state) => state.providerConfigs);
  const enabledProviders = definitions.filter(
    (definition) => providerConfigs[definition.id]?.enabled
  );
  const modelCount = enabledProviders.reduce(
    (total, definition) =>
      total +
      definition.models.length +
      (providerConfigs[definition.id]?.customModels.length ?? 0),
    0
  );
  const verifiedCount = enabledProviders.filter(
    (definition) =>
      providerConfigs[definition.id]?.verified || !definition.requiresApiKey
  ).length;
  const navItems: AppShellNavItem[] = [
    {
      id: "scenarios",
      label: "项目管理",
      caption: "Scenarios",
      icon: FolderKanban,
    },
    {
      id: "models",
      label: "模型配置",
      caption: "AI Models",
      icon: Bot,
      badge: enabledProviders.length,
    },
  ];

  return (
    <AppShell
      activeNavItem="models"
      actions={
        <Button onClick={() => navigate(-1)} type="button" variant="outline">
          <ArrowLeft className="size-4" />
          返回
        </Button>
      }
      description="集中维护大模型 Provider、API Key、Base URL 和可用模型列表。"
      eyebrow="AI Runtime"
      navItems={navItems}
      onNavItemSelect={(id) => {
        if (id === "scenarios") navigate("/scenarios");
        if (id === "models") navigate("/ai-models");
      }}
      title="模型配置中心"
    >
      <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <StatCard
            caption="当前启用"
            icon={Server}
            label="Provider"
            value={enabledProviders.length}
          />
          <StatCard
            caption="可选择模型"
            icon={Bot}
            label="模型数量"
            tone="green"
            value={modelCount}
          />
          <StatCard
            caption="已通过或免密"
            icon={CheckCircle2}
            label="验证状态"
            tone="amber"
            value={verifiedCount}
          />
        </div>
        <ModelConfigCenter onSaved={() => navigate(-1)} />
      </div>
    </AppShell>
  );
}
