import { describe, expect, it, vi } from "vitest";

import {
  buildWhatsAppConnectionPayload,
  createWhatsAppConnectionValues,
  getWhatsAppConnection,
  saveWhatsAppConnection,
  type WhatsAppConnectionValues,
} from "@/lib/whatsapp-connection";

const values: WhatsAppConnectionValues = {
  mode: "test",
  wabaId: "  123456789012345  ",
  phoneNumberId: "  987654321098765  ",
  displayPhoneNumber: "  +1 555 010 1234  ",
  displayName: "  OrderlyAI Test Bot  ",
  accessToken: "  EAAG-test-token  ",
};

describe("WhatsApp connection payloads", () => {
  it("maps backend connection state into form values without exposing the token", () => {
    expect(
      createWhatsAppConnectionValues({
        id: "connection-1",
        business_id: "business-1",
        mode: "test",
        waba_id: "123456789012345",
        phone_number_id: "987654321098765",
        display_phone_number: "+1 555 010 1234",
        display_name: "OrderlyAI Test Bot",
        status: "configured",
        has_access_token: true,
      }),
    ).toEqual({
      mode: "test",
      wabaId: "123456789012345",
      phoneNumberId: "987654321098765",
      displayPhoneNumber: "+1 555 010 1234",
      displayName: "OrderlyAI Test Bot",
      accessToken: "",
    });
  });

  it("builds the real Meta setup payload from form values", () => {
    expect(buildWhatsAppConnectionPayload(values)).toEqual({
      mode: "test",
      waba_id: "123456789012345",
      phone_number_id: "987654321098765",
      display_phone_number: "+1 555 010 1234",
      display_name: "OrderlyAI Test Bot",
      access_token: "EAAG-test-token",
    });
  });

  it("omits a blank access token so an existing token can be preserved", () => {
    expect(
      buildWhatsAppConnectionPayload({ ...values, accessToken: "   " }),
    ).not.toHaveProperty("access_token");
  });
});

describe("WhatsApp connection API", () => {
  it("GETs and PUTs the tenant-scoped WhatsApp connection endpoint", async () => {
    const fetcher = vi.fn<typeof fetch>(async () => {
      return new Response(
        JSON.stringify({
          id: "connection-1",
          business_id: "business-1",
          mode: "test",
          waba_id: "123456789012345",
          phone_number_id: "987654321098765",
          display_phone_number: "+1 555 010 1234",
          display_name: "OrderlyAI Test Bot",
          status: "configured",
          has_access_token: true,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });

    await getWhatsAppConnection({
      accessToken: "token",
      businessId: "business-1",
      fetcher,
    });
    await saveWhatsAppConnection({
      accessToken: "token",
      businessId: "business-1",
      values,
      fetcher,
    });

    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/businesses/business-1/whatsapp-connection",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/businesses/business-1/whatsapp-connection",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify(buildWhatsAppConnectionPayload(values)),
      }),
    );
  });
});
