import { describe, expect, it, vi } from "vitest";

import {
  buildBusinessSettingsPayload,
  buildZonePayload,
  createDeliveryZoneDraft,
  createFulfillmentValues,
  saveFulfillment,
  validateFulfillment,
  type FulfillmentValues,
} from "@/lib/fulfillment";

const validValues: FulfillmentValues = {
  offersDelivery: true,
  offersPickup: true,
  offersDineIn: false,
  minOrderAmount: "500",
  defaultPrepMinutes: "30",
  packagingFee: "25",
  zones: [
    {
      clientId: "zone-local-1",
      id: null,
      name: "  Gulshan  ",
      fee: "150",
      minOrder: "500",
      etaMinutes: "35",
      isActive: true,
    },
  ],
};

describe("fulfillment validation", () => {
  it("requires delivery or pickup even when dine-in is selected", () => {
    const errors = validateFulfillment({
      ...validValues,
      offersDelivery: false,
      offersPickup: false,
      offersDineIn: true,
      zones: [],
    });

    expect(errors.fulfillment).toBeDefined();
  });

  it("requires one complete active zone when delivery is enabled", () => {
    const errors = validateFulfillment({
      ...validValues,
      zones: [
        {
          ...validValues.zones[0],
          name: "",
          fee: "",
          isActive: false,
        },
      ],
    });

    expect(errors.zones).toBeDefined();
    expect(errors.zoneFields["zone-local-1"]).toEqual({
      name: "Zone name is required.",
      fee: "Delivery fee is required.",
    });
  });

  it("allows pickup-only businesses without delivery zones", () => {
    const errors = validateFulfillment({
      ...validValues,
      offersDelivery: false,
      offersPickup: true,
      zones: [],
    });

    expect(errors).toEqual({ zoneFields: {} });
  });

  it("ignores unfinished zone drafts while delivery is disabled", () => {
    const errors = validateFulfillment({
      ...validValues,
      offersDelivery: false,
      offersPickup: true,
      zones: [{ ...validValues.zones[0], name: "", fee: "" }],
    });

    expect(errors).toEqual({ zoneFields: {} });
  });
});

describe("fulfillment payloads", () => {
  it("creates an empty active zone row for the form", () => {
    expect(createDeliveryZoneDraft("zone-new-1")).toEqual({
      clientId: "zone-new-1",
      id: null,
      name: "",
      fee: "",
      minOrder: "",
      etaMinutes: "",
      isActive: true,
    });
  });

  it("maps saved backend values into resumable form state", () => {
    expect(
      createFulfillmentValues(
        {
          offers_delivery: true,
          offers_pickup: false,
          min_order_amount: "750.00",
          default_prep_minutes: 40,
          packaging_fee: "20.00",
        },
        [
          {
            id: "zone-123",
            business_id: "business-123",
            name: "Gulshan",
            fee: "150.00",
            min_order: "500.00",
            eta_minutes: 35,
            is_active: true,
          },
        ],
      ),
    ).toEqual({
      offersDelivery: true,
      offersPickup: false,
      offersDineIn: false,
      minOrderAmount: "750.00",
      defaultPrepMinutes: "40",
      packagingFee: "20.00",
      zones: [
        {
          clientId: "zone-123",
          id: "zone-123",
          name: "Gulshan",
          fee: "150.00",
          minOrder: "500.00",
          etaMinutes: "35",
          isActive: true,
        },
      ],
    });
  });

  it("maps settings and zone drafts to backend field names", () => {
    expect(buildBusinessSettingsPayload(validValues)).toEqual({
      offers_delivery: true,
      offers_pickup: true,
      min_order_amount: "500",
      default_prep_minutes: 30,
      packaging_fee: "25",
    });
    expect(buildZonePayload(validValues.zones[0])).toEqual({
      name: "Gulshan",
      fee: "150",
      min_order: "500",
      eta_minutes: 35,
      is_active: true,
    });
  });
});

describe("saveFulfillment", () => {
  it("does not write hidden zone drafts while delivery is disabled", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ id: "business-123" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await saveFulfillment({
      accessToken: "access-token",
      businessId: "business-123",
      values: {
        ...validValues,
        offersDelivery: false,
        zones: [{ ...validValues.zones[0], name: "", fee: "" }],
      },
      deletedZoneIds: [],
      fetcher,
    });

    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/businesses/business-123",
      expect.objectContaining({ method: "PATCH" }),
    );
  });

  it("PATCHes tenant settings and reconciles new, existing, and removed zones", async () => {
    const existingZone = {
      ...validValues.zones[0],
      clientId: "zone-existing",
      id: "zone-123",
      name: "DHA Phase 5",
    };
    const values = { ...validValues, zones: [existingZone, validValues.zones[0]] };
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (init?.method === "DELETE") return new Response(null, { status: 204 });
      if (url.endsWith("/businesses/business-123")) {
        return new Response(JSON.stringify({ id: "business-123" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ id: "zone-saved" }), {
        status: init?.method === "POST" ? 201 : 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    await saveFulfillment({
      accessToken: "access-token",
      businessId: "business-123",
      values,
      deletedZoneIds: ["zone-removed"],
      fetcher,
    });

    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/businesses/business-123",
      expect.objectContaining({ method: "PATCH" }),
    );
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/businesses/business-123/delivery-zones/zone-123",
      expect.objectContaining({ method: "PATCH" }),
    );
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/businesses/business-123/delivery-zones",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/businesses/business-123/delivery-zones/zone-removed",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
