import { describe, expect, it, vi } from "vitest";

import {
  inferOnboardingResumePath,
  readOnboardingResumePath,
  resolveOnboardingResumePath,
  saveOnboardingResumePath,
} from "@/lib/onboarding-progress";

function createStorage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      values.set(key, value);
    }),
    removeItem: vi.fn((key: string) => {
      values.delete(key);
    }),
  };
}

describe("onboarding progress", () => {
  it("stores and reads only implemented onboarding resume paths", () => {
    const storage = createStorage();

    saveOnboardingResumePath("/onboarding/hours", storage);
    expect(readOnboardingResumePath(storage)).toBe("/onboarding/hours");

    saveOnboardingResumePath("/onboarding/menu", storage);
    expect(readOnboardingResumePath(storage)).toBe("/onboarding/menu");

    saveOnboardingResumePath("/onboarding/assistant", storage);
    expect(readOnboardingResumePath(storage)).toBe("/onboarding/assistant");

    saveOnboardingResumePath("/onboarding/whatsapp", storage);
    expect(readOnboardingResumePath(storage)).toBe("/onboarding/whatsapp");
  });

  it("prefers the stored resume path after login", async () => {
    const storage = createStorage({
      "orderly.onboarding_resume_path": "/onboarding/fulfillment",
    });
    const listBusinesses = vi.fn();
    const listDeliveryZones = vi.fn();

    await expect(
      resolveOnboardingResumePath({
        accessToken: "token",
        storage,
        listBusinesses,
        listDeliveryZones,
      }),
    ).resolves.toBe("/onboarding/fulfillment");

    expect(listBusinesses).not.toHaveBeenCalled();
    expect(listDeliveryZones).not.toHaveBeenCalled();
  });

  it("falls back to the first unfinished backend-backed step", async () => {
    const business = {
      id: "business-1",
      offers_delivery: true,
      offers_pickup: true,
      min_order_amount: "0",
      default_prep_minutes: 30,
      packaging_fee: "0",
    };

    expect(inferOnboardingResumePath(undefined, [])).toBe("/onboarding");
    expect(inferOnboardingResumePath(business, [])).toBe("/onboarding/hours");
    expect(
      inferOnboardingResumePath(business, [
        { id: "zone-1", name: "Gulshan", fee: "100" },
      ]),
    ).toBe("/onboarding/fulfillment");
  });

  it("ignores invalid stored paths and uses backend fallback", async () => {
    const storage = createStorage({
      "orderly.onboarding_resume_path": "/dashboard",
    });

    await expect(
      resolveOnboardingResumePath({
        accessToken: "token",
        storage,
        listBusinesses: vi.fn(async () => [
          {
            id: "business-1",
            status: "onboarding",
            offers_delivery: true,
            offers_pickup: true,
            min_order_amount: "0",
            default_prep_minutes: 30,
            packaging_fee: "0",
          },
        ]),
        listDeliveryZones: vi.fn(async () => []),
      }),
    ).resolves.toBe("/onboarding/hours");
  });
});
