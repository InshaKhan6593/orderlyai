import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { AIAssistantForm } from "@/components/onboarding/ai-assistant-form";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

describe("AIAssistantForm", () => {
  it("renders the English-only assistant setup without tone or automatic approval", () => {
    const html = renderToStaticMarkup(
      <AIAssistantForm
        initialState={{
          accessToken: "token",
          business: {
            id: "business-1",
            name: "The Green Bistro",
            helpline_phone: "+92 300 1234567",
          },
          config: {
            id: null,
            business_id: "business-1",
            greeting_message:
              "Hi! Welcome to The Green Bistro. I can show you our menu and take your order. What would you like today?",
            language: "en",
            upsell_enabled: true,
            human_handoff_phone: "+92 300 1234567",
            extra_instructions: "",
          },
        }}
      />,
    );

    expect(html).toContain("Step 6 of 8");
    expect(html).toContain("Set up your WhatsApp assistant");
    expect(html).toContain("You can finish this later");
    expect(html).toContain("Greeting message");
    expect(html).toContain("Language");
    expect(html).toContain("English");
    expect(html).toContain("Upsell suggestions");
    expect(html).toContain("Human handoff number");
    expect(html).toContain("FAQ / extra info");
    expect(html).toContain("Live preview");
    expect(html).toContain("Preview only");
    expect(html).not.toContain("Tone");
    expect(html).not.toContain("Friendly");
    expect(html).not.toContain("Auto-confirm");
    expect(html).not.toContain("automatic");
    expect(html).not.toContain("approve each order");
  });
});
