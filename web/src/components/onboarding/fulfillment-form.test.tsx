import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { FulfillmentForm } from "@/components/onboarding/fulfillment-form";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

describe("FulfillmentForm", () => {
  it("renders the Step 4 fulfillment, order settings, and zones sections", () => {
    const html = renderToStaticMarkup(<FulfillmentForm />);

    expect(html).toContain("Step 4 of 8");
    expect(html).toContain("How do customers get their food?");
    expect(html).toContain("Fulfillment options");
    expect(html).toContain("Order settings");
    expect(html).toContain("Delivery zones");
    expect(html).toContain("Delivery");
    expect(html).toContain("Pickup");
    expect(html).toContain("Dine-in");
  });

  it("keeps the three fulfillment option cards compact", () => {
    const html = renderToStaticMarkup(<FulfillmentForm />);

    expect(html.match(/min-h-\[72px\]/g) ?? []).toHaveLength(3);
    expect(html).toContain("size-6 shrink-0 stroke-[1.5] text-foreground");
    expect(html).toContain("ml-auto flex shrink-0 items-center gap-2");
    expect(html).not.toContain("min-h-[84px]");
    expect(html).not.toContain("min-h-[108px]");
    expect(html).not.toContain("mt-2 flex items-center gap-2");
    expect(html).not.toContain("size-8 shrink-0 stroke-[1.5] text-foreground");
  });
});
