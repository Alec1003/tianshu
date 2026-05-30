import { beforeEach, describe, expect, it } from "vitest";

import { DEFAULT_MODEL, createDefaultProviderConfigs } from "./modelProfiles";
import { useModelConfigStore } from "./modelStore";

describe("modelStore", () => {
  beforeEach(() => {
    window.localStorage.clear();
    useModelConfigStore.setState({
      providerConfigs: createDefaultProviderConfigs(),
      modelProfiles: [],
      activeModelProfileId: "",
      defaultModelProfileId: "",
      activeModelConfig: DEFAULT_MODEL,
      showUnverifiedModels: true,
    });
  });

  it("shows only models explicitly added in the config center", () => {
    useModelConfigStore.getState().updateProviderConfig("openai-responses", {
      enabled: true,
      verified: true,
      customModels: [
        {
          id: "gpt-5.5",
          group: "Responses",
          checkStatus: "ok",
        },
      ],
    });

    const options = useModelConfigStore.getState().getModelOptions();

    expect(options.map((option) => option.id)).toEqual(["gpt-5.5"]);
  });
});
