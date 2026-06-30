import { describe, expect, it } from "vitest";

import type { Business } from "@/lib/business-profile";
import {
  pickBusinessForOwner,
  readSelectedBusinessId,
  saveSelectedBusinessId,
  SELECTED_BUSINESS_STORAGE_KEY,
} from "@/lib/business-selection";

function business(
  patch: Pick<Business, "id" | "name" | "status">,
): Business {
  return {
    id: patch.id,
    name: patch.name,
    slug: patch.name.toLowerCase().replaceAll(" ", "-"),
    type: "restaurant",
    description: null,
    logo_url: null,
    cover_url: null,
    timezone: "America/New_York",
    currency: "USD",
    languages: ["en"],
    helpline_phone: null,
    email: null,
    address: null,
    maps_url: null,
    status: patch.status,
    offers_delivery: true,
    offers_pickup: true,
    min_order_amount: "0.00",
    default_prep_minutes: 20,
    packaging_fee: "0.00",
    accepting_orders: true,
  };
}

function storage(seed: Record<string, string> = {}): Storage {
  const values = new Map(Object.entries(seed));
  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key: string) => values.get(key) ?? null,
    key: (index: number) => Array.from(values.keys())[index] ?? null,
    removeItem: (key: string) => {
      values.delete(key);
    },
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
  };
}

describe("business selection", () => {
  const businesses = [
    business({ id: "new-onboarding", name: "New Store", status: "onboarding" }),
    business({ id: "8oz", name: "8oz", status: "active" }),
  ];

  it("uses the saved business id when the owner has multiple businesses", () => {
    const selected = pickBusinessForOwner(
      businesses,
      storage({ [SELECTED_BUSINESS_STORAGE_KEY]: "8oz" }),
    );

    expect(selected?.id).toBe("8oz");
  });

  it("falls back to an active business before an onboarding business", () => {
    const selected = pickBusinessForOwner(businesses, storage());

    expect(selected?.id).toBe("8oz");
  });

  it("persists the selected business id for the next owner page", () => {
    const store = storage();

    saveSelectedBusinessId("8oz", store);

    expect(readSelectedBusinessId(store)).toBe("8oz");
  });
});
