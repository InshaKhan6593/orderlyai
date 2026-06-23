import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { WhatsAppConnectionForm } from "@/components/onboarding/whatsapp-connection-form";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

describe("WhatsAppConnectionForm", () => {
  it("renders the Meta test-number fields and client handoff guidance", () => {
    const html = renderToStaticMarkup(
      <WhatsAppConnectionForm
        initialState={{
          accessToken: "token",
          business: {
            id: "business-1",
            name: "The Green Bistro",
          },
          connection: {
            id: null,
            business_id: "business-1",
            mode: "test",
            waba_id: "",
            phone_number_id: "",
            display_phone_number: null,
            display_name: null,
            status: "not_configured",
            has_access_token: false,
          },
        }}
      />,
    );

    expect(html).toContain("Step 7 of 8");
    expect(html).toContain("Connect your WhatsApp number");
    expect(html).toContain("Connection status");
    expect(html).toContain("Use your Meta test number");
    expect(html).toContain("WABA ID");
    expect(html).toContain("Phone number ID");
    expect(html).toContain("Access token");
    expect(html).toContain("Display phone number");
    expect(html).toContain("Clients provide the same WABA ID, phone number ID, and token for manual onboarding.");
    expect(html).not.toContain("App secret");
  });
});
