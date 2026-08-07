import { describe, expect, it } from "vitest";

import {
  buildChatRequestHeaders,
  encodeChatHeaderValue,
  extractChatErrorMessage,
  formatChatError,
} from "./chatTransport";

describe("chatTransport", () => {
  it("includes per-request model credentials in chat headers", () => {
    const headers = buildChatRequestHeaders({
      approvalMode: "auto",
      modelConfig: {
        provider: "openai",
        model: "gpt-5",
        apiKey: "sk-test",
        baseUrl: "https://api.openai.com/v1",
      },
      modelProviderId: "openai-responses",
      modelConfigId: "openai",
      docFolder: "folder-1",
      scenarioId: "scenario-1",
      token: "jwt-token",
    });

    expect(headers).toEqual({
      Authorization: "Bearer jwt-token",
      "X-TianShu-Approval-Mode": "auto",
      "X-TianShu-Model-Config-Id": "openai",
      "X-TianShu-Model-Provider-Id": "openai-responses",
      "X-TianShu-Model-Provider": "openai",
      "X-TianShu-Model-Name": "gpt-5",
      "X-TianShu-Model-Base-Url": "https://api.openai.com/v1",
      "X-TianShu-Doc-Folder": "folder-1",
      "X-TianShu-Scenario-Id": "scenario-1",
    });
    // API Key must NEVER appear in chat request headers
    expect(headers).not.toHaveProperty("X-TianShu-Model-Api-Key");
  });

  it("omits empty optional header values", () => {
    const headers = buildChatRequestHeaders({
      approvalMode: "strict",
      modelConfig: {
        provider: "",
        model: "",
        apiKey: "",
        baseUrl: "",
      },
    });

    expect(headers).toEqual({
      "X-TianShu-Approval-Mode": "strict",
    });
  });

  it("encodes non-Latin custom header values for browser fetch", () => {
    const headers = buildChatRequestHeaders({
      approvalMode: "off",
      modelConfig: {
        provider: "custom",
        model: "通义千问",
        apiKey: "",
        baseUrl: "",
      },
      docFolder: "战报资料",
    });

    expect(headers["X-TianShu-Model-Provider"]).toBe("custom");
    expect(headers["X-TianShu-Model-Name"]).toBe(
      encodeChatHeaderValue("通义千问")
    );
    expect(headers["X-TianShu-Doc-Folder"]).toBe(
      encodeChatHeaderValue("战报资料")
    );
    expect(headers["X-TianShu-Model-Name"]).toMatch(/^utf8-url:/);
    expect(() => new Headers(headers)).not.toThrow();
  });

  it("extracts nested backend error details from wrapped errors", () => {
    const error = new Error("503 Service Unavailable") as Error & {
      cause?: unknown;
    };
    error.cause = {
      response: {
        body: {
          error:
            "No LLM configured. Either set TIANSHU_LLM_MODEL + TIANSHU_LLM_API_KEY on the server, or fill the model section in the AI sidebar (Settings).",
        },
      },
    };

    expect(extractChatErrorMessage(error)).toContain("No LLM configured");
    expect(formatChatError(error)).toBe(
      "No LLM is configured. Fill the API key in AI model settings, or set TIANSHU_LLM_MODEL and TIANSHU_LLM_API_KEY in the server environment."
    );
  });

  it("uses structured detail messages before falling back to unknown", () => {
    expect(
      formatChatError({
        detail: [{ message: "Model provider rejected the API key" }],
      })
    ).toBe("Model provider rejected the API key");
  });
});
