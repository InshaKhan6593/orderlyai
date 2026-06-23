import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { BusinessProfileForm } from "@/components/onboarding/business-profile-form";
import { BusinessHoursForm } from "@/components/onboarding/business-hours-form";
import { FulfillmentForm } from "@/components/onboarding/fulfillment-form";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

describe("BusinessHoursForm layout", () => {
  it("uses the compact content and heading scale from Business Profile", () => {
    const html = renderToStaticMarkup(<BusinessHoursForm />);

    expect(html).toContain("max-w-[1040px]");
    expect(html).toContain("text-3xl");
    expect(html).toContain("sm:text-[34px]");
    expect(html).not.toContain("sm:text-5xl");
  });

  it("shares the same onboarding header and card contract as Business Profile", () => {
    const profileHtml = renderToStaticMarkup(<BusinessProfileForm />);
    const hoursHtml = renderToStaticMarkup(<BusinessHoursForm />);

    for (const html of [profileHtml, hoursHtml]) {
      expect(html).toContain('data-onboarding-step-header="true"');
      expect(html).toContain("font-heading text-3xl leading-tight font-semibold");
      expect(html).toContain('data-onboarding-card="true"');
      expect(html).toContain("rounded-lg border-border bg-card py-0");
    }

    expect(profileHtml.match(/data-onboarding-card="true"/g)).toHaveLength(1);
    expect(hoursHtml.match(/data-onboarding-card="true"/g)).toHaveLength(2);
  });

  it("uses the app Select control instead of native time inputs", () => {
    const html = renderToStaticMarkup(<BusinessHoursForm />);

    expect(html).not.toContain('type="time"');
    expect(html).toContain('data-slot="select-trigger"');
    expect(html).toContain("09:00 AM");
  });

  it("renders one Closed label for each closed day", () => {
    const html = renderToStaticMarkup(<BusinessHoursForm />);
    const closedLabels = html.match(/>Closed<\/span>/g) ?? [];

    expect(closedLabels).toHaveLength(2);
  });

  it("keeps the accepting-orders card compact", () => {
    const html = renderToStaticMarkup(<BusinessHoursForm />);

    expect(html).toContain(
      "grid gap-3 px-5 py-3 has-data-[slot=card-action]:grid-cols-1",
    );
  });

  it("uses the compact menu footer sizing across onboarding forms", () => {
    const formHtml = [
      renderToStaticMarkup(<BusinessProfileForm />),
      renderToStaticMarkup(<BusinessHoursForm />),
      renderToStaticMarkup(<FulfillmentForm />),
    ];

    for (const html of formHtml) {
      expect(html).toContain("py-3");
      expect(html).toContain("w-full justify-between gap-3");
      expect(html).toContain("h-10 min-w-[104px]");
      expect(html).toContain("h-10 min-w-[136px]");
      expect(html).not.toContain("h-12");
    }
  });
});
