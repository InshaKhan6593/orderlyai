import { describe, expect, it, vi } from "vitest";

import {
  buildBusinessPayloads,
  hasRequiredBusinessProfileFields,
  saveBusinessProfile,
  shouldShowFieldError,
  type BusinessProfileValues,
} from "@/lib/business-profile";

const validProfile: BusinessProfileValues = {
  name: "  The Green Bistro  ",
  type: "restaurant",
  description: "  Seasonal food, made locally.  ",
  logoPath: "local-file://logo.png",
  coverPath: "local-file://cover.jpg",
  timezone: "Asia/Karachi",
  currency: "PKR",
  languages: ["en", "ur"],
  phoneCountry: "+92",
  phoneNumber: " 300 1234567 ",
  email: " hello@example.com ",
  address: " 12 Market Road ",
  mapsUrl: " https://maps.google.com/example ",
};

describe("buildBusinessPayloads", () => {
  it("maps form values to the backend create and update contracts", () => {
    expect(buildBusinessPayloads(validProfile)).toEqual({
      create: {
        name: "The Green Bistro",
        type: "restaurant",
        timezone: "Asia/Karachi",
        currency: "PKR",
      },
      update: {
        name: "The Green Bistro",
        type: "restaurant",
        description: "Seasonal food, made locally.",
        logo_url: "local-file://logo.png",
        cover_url: "local-file://cover.jpg",
        timezone: "Asia/Karachi",
        currency: "PKR",
        languages: ["en", "ur"],
        helpline_phone: "+92 300 1234567",
        email: "hello@example.com",
        address: "12 Market Road",
        maps_url: "https://maps.google.com/example",
      },
    });
  });

  it("sends nulls for cleared optional fields", () => {
    const values = {
      ...validProfile,
      description: "",
      logoPath: "",
      coverPath: "",
      phoneNumber: "",
      email: "",
      address: "",
      mapsUrl: "",
    };

    expect(buildBusinessPayloads(values).update).toMatchObject({
      description: null,
      logo_url: null,
      cover_url: null,
      helpline_phone: null,
      email: null,
      address: null,
      maps_url: null,
    });
  });
});

describe("business-profile validation state", () => {
  it("does not show an error for an untouched field before submission", () => {
    expect(shouldShowFieldError(true, false, 0)).toBe(false);
    expect(shouldShowFieldError(true, true, 0)).toBe(true);
    expect(shouldShowFieldError(true, false, 1)).toBe(true);
  });

  it("keeps Continue disabled until every required field has a value", () => {
    expect(
      hasRequiredBusinessProfileFields({
        name: "",
        type: "restaurant",
        timezone: "Asia/Karachi",
        currency: "PKR",
      }),
    ).toBe(false);
    expect(
      hasRequiredBusinessProfileFields({
        name: "The Green Bistro",
        type: "restaurant",
        timezone: "Asia/Karachi",
        currency: "PKR",
      }),
    ).toBe(true);
  });
});

describe("saveBusinessProfile", () => {
  it("creates the tenant, then PATCHes optional fields through its tenant-scoped endpoint", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ id: "business-123", ...buildBusinessPayloads(validProfile).create }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "business-123", name: "The Green Bistro" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

    await saveBusinessProfile({
      accessToken: "access-token",
      values: validProfile,
      fetcher,
    });

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/api/v1/businesses",
      expect.objectContaining({
        method: "POST",
        headers: {
          Authorization: "Bearer access-token",
          "Content-Type": "application/json",
        },
      }),
    );
    expect(fetcher).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/businesses/business-123",
      expect.objectContaining({ method: "PATCH" }),
    );
  });

  it("updates an existing tenant without creating a duplicate", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ id: "business-123", name: "The Green Bistro" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await saveBusinessProfile({
      accessToken: "access-token",
      existingBusinessId: "business-123",
      values: validProfile,
      fetcher,
    });

    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/businesses/business-123",
      expect.objectContaining({ method: "PATCH" }),
    );
  });
});
