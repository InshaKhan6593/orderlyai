import { describe, expect, it, vi } from "vitest";

import {
  buildAgentConfigPayload,
  createAgentConfigValues,
  getAgentConfig,
  saveAgentConfig,
  type AgentConfigValues,
} from "@/lib/ai-assistant";

const values: AgentConfigValues = {
  greetingMessage: "  Hi! Welcome to Test Bistro. What would you like today?  ",
  upsellEnabled: true,
  humanHandoffPhone: "  +92 300 1234567  ",
  extraInstructions: "  Cash and card accepted.  ",
};

describe("AI assistant payloads", () => {
  it("maps backend config to English-only form values", () => {
    expect(
      createAgentConfigValues(
        { name: "Test Bistro", helpline_phone: "+92 300 7654321" },
        {
          id: "config-1",
          business_id: "business-1",
          greeting_message: "Saved greeting",
          language: "en",
          upsell_enabled: false,
          human_handoff_phone: null,
          extra_instructions: "Parking behind the building.",
        },
      ),
    ).toEqual({
      greetingMessage: "Saved greeting",
      upsellEnabled: false,
      humanHandoffPhone: "+92 300 7654321",
      extraInstructions: "Parking behind the building.",
    });
  });

  it("builds a minimal payload without tone, language, or automatic approval", () => {
    expect(buildAgentConfigPayload(values)).toEqual({
      greeting_message: "Hi! Welcome to Test Bistro. What would you like today?",
      upsell_enabled: true,
      human_handoff_phone: "+92 300 1234567",
      extra_instructions: "Cash and card accepted.",
    });
  });
});

describe("AI assistant API", () => {
  it("GETs and PUTs the tenant-scoped agent config endpoint", async () => {
    const fetcher = vi.fn<typeof fetch>(async (_input, init) => {
      return new Response(
        JSON.stringify({
          id: "config-1",
          business_id: "business-1",
          greeting_message: "Saved greeting",
          language: "en",
          upsell_enabled: init?.method !== "PUT",
          human_handoff_phone: null,
          extra_instructions: null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });

    await getAgentConfig({
      accessToken: "token",
      businessId: "business-1",
      fetcher,
    });
    await saveAgentConfig({
      accessToken: "token",
      businessId: "business-1",
      values,
      fetcher,
    });

    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/businesses/business-1/agent-config",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/businesses/business-1/agent-config",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify(buildAgentConfigPayload(values)),
      }),
    );
  });
});
