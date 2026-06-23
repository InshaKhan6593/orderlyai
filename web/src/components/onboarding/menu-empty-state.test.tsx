import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import {
  MenuBuilder,
  MenuEmptyState,
} from "@/components/onboarding/menu-empty-state";
import { ModifierTemplateManagerContent } from "@/components/onboarding/modifier-template-dialog";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

describe("MenuEmptyState", () => {
  function renderEmptyBuilder() {
    return renderToStaticMarkup(
      <MenuBuilder
        initialState={{
          accessToken: "token",
          businessId: "biz-1",
          categories: [],
          products: [],
        }}
      />,
    );
  }

  it("renders the step 5 empty menu screen", () => {
    const html = renderEmptyBuilder();

    expect(html).toContain("Step 5 of 8");
    expect(html).toContain("Build your menu");
    expect(html).toContain("Categories");
    expect(html).toContain("No categories yet");
    expect(html).toContain("No dishes yet");
    expect(html).toContain("Add your first dish");
    expect(html).toContain("Seed sample menu");
  });

  it("uses the widened menu sizing contract", () => {
    const html = renderEmptyBuilder();

    expect(html).toContain("max-w-[1120px]");
    expect(html).toContain('data-onboarding-step-header="true"');
    expect(html).toContain("font-heading text-3xl leading-tight font-semibold");
    expect(html).toContain('data-onboarding-card="true"');
    expect(html).toContain("rounded-lg border-border bg-card py-0");
    expect(html).not.toContain("sm:text-5xl");
  });

  it("keeps the dish drawer trigger in the empty menu panel only", () => {
    const html = renderEmptyBuilder();

    expect(html.match(/data-menu-dish-trigger="true"/g)).toHaveLength(1);
    expect(html).toContain("min-h-[390px] md:grid-cols-[224px_1fr]");
    expect(html).toContain("disabled=\"\"");
  });

  it("uses compact footer controls and a filled gold seed-menu icon", () => {
    const html = renderEmptyBuilder();

    expect(html).toContain("py-3");
    expect(html).toContain("h-10 min-w-[104px]");
    expect(html).toContain("h-10 min-w-[136px]");
    expect(html).toContain("fill-gold text-gold");
  });

  it("does not inject test credentials into the live menu route component", () => {
    const html = renderToStaticMarkup(<MenuEmptyState />);

    expect(html).toContain('data-menu-loading="true"');
    expect(html).not.toContain("No categories yet");
  });

  it("renders an in-app category name popup instead of relying on window.prompt", () => {
    const html = renderToStaticMarkup(
      <MenuBuilder
        initialState={{
          accessToken: "token",
          businessId: "biz-1",
          categories: [],
          products: [],
          categoryDialogOpen: true,
        }}
      />,
    );

    expect(html).toContain('role="dialog"');
    expect(html).toContain("Add category");
    expect(html).toContain("Category name");
    expect(html).toContain("Create category");
  });

  it("renders the category dialog overlay after the onboarding footer", () => {
    const html = renderToStaticMarkup(
      <MenuBuilder
        initialState={{
          accessToken: "token",
          businessId: "biz-1",
          categories: [],
          products: [],
          categoryDialogOpen: true,
        }}
      />,
    );

    expect(html.indexOf('role="dialog"')).toBeGreaterThan(
      html.indexOf("Skip for now"),
    );
  });

  it("keeps the category list visible behind the new dish drawer before products exist", () => {
    const html = renderToStaticMarkup(
      <MenuBuilder
        initialState={{
          accessToken: "token",
          businessId: "biz-1",
          categories: [
            {
              id: "cat-mains",
              business_id: "biz-1",
              name: "Mains",
              sort_order: 0,
              is_active: true,
              created_at: "2026-06-22T00:00:00Z",
            },
          ],
          products: [],
          openNewDish: true,
        }}
      />,
    );

    expect(html).toContain("Mains");
    expect(html).toContain("0 dishes");
    expect(html).toContain("No dishes in this category yet");
    expect(html).toContain("Add dish");
    expect(html).not.toContain("No categories yet");
  });

  it("uses compact theme sizing with enough drawer width for modifiers", () => {
    const html = renderToStaticMarkup(
      <MenuBuilder
        initialState={{
          accessToken: "token",
          businessId: "biz-1",
          categories: [
            {
              id: "cat-burgers",
              business_id: "biz-1",
              name: "burgers",
              sort_order: 0,
              is_active: true,
              created_at: "2026-06-22T00:00:00Z",
            },
          ],
          products: [],
          openNewDish: true,
        }}
      />,
    );

    expect(html).toContain(
      "fixed inset-0 z-50 bg-foreground/35 p-3 backdrop-blur-[1px] sm:p-4",
    );
    expect(html).toContain("max-w-[720px]");
    expect(html).toContain(
      "overflow-hidden rounded-xl border border-border bg-white",
    );
    expect(html).toContain("px-6 pt-5 pb-2");
    expect(html).toContain("font-heading text-xl leading-tight font-semibold");
    expect(html).toContain("sm:grid-cols-[116px_1fr]");
    expect(html).toContain("size-[116px]");
    expect(html).toContain("px-6 py-4");
    expect(html).not.toContain("fixed inset-0 bg-foreground/20");
    expect(html).not.toContain("rounded-l-xl border-l border-border");
    expect(html).not.toContain("max-w-[600px]");
    expect(html).not.toContain("max-w-[650px]");
    expect(html).not.toContain("px-8 pt-7 pb-3");
  });

  it("renders a file upload control for menu item images", () => {
    const html = renderToStaticMarkup(
      <MenuBuilder
        initialState={{
          accessToken: "token",
          businessId: "biz-1",
          categories: [
            {
              id: "cat-burgers",
              business_id: "biz-1",
              name: "burgers",
              sort_order: 0,
              is_active: true,
              created_at: "2026-06-22T00:00:00Z",
            },
          ],
          products: [],
          openNewDish: true,
        }}
      />,
    );

    expect(html).toContain("Upload image");
    expect(html).toContain('type="file"');
    expect(html).toContain('accept="image/png,image/jpeg,image/webp"');
  });

  it("renders compact category rows with edit and delete actions", () => {
    const html = renderToStaticMarkup(
      <MenuBuilder
        initialState={{
          accessToken: "token",
          businessId: "biz-1",
          categories: [
            {
              id: "cat-mains",
              business_id: "biz-1",
              name: "Mains",
              sort_order: 0,
              is_active: true,
              created_at: "2026-06-22T00:00:00Z",
            },
          ],
          products: [],
        }}
      />,
    );

    expect(html).toContain("grid h-9");
    expect(html).toContain('aria-label="Edit Mains category"');
    expect(html).toContain('aria-label="Delete Mains category"');
    expect(html).not.toContain("flex h-12 items-center");
    expect(html).not.toContain("Drag to reorder");
  });

  it("renders the backend-wired menu editor drawer from the modifier mockup", () => {
    const html = renderToStaticMarkup(
      <MenuBuilder
        initialState={{
          accessToken: "token",
          businessId: "biz-1",
          categories: [
            {
              id: "cat-mains",
              business_id: "biz-1",
              name: "Mains",
              sort_order: 0,
              is_active: true,
              created_at: "2026-06-22T00:00:00Z",
            },
          ],
          products: [
            {
              id: "prod-burger",
              business_id: "biz-1",
              category_id: "cat-mains",
              name: "Classic Beef Burger",
              description: "Smash patty, cheddar, house sauce",
              price: "850",
              image_url: null,
              is_available: true,
              is_archived: false,
              tags: ["bestseller", "halal"],
              prep_minutes: 20,
              sort_order: 0,
              modifier_groups: [
                {
                  assignment_id: "assignment-size",
                  modifier_group_id: "group-size",
                  name: "Burger sizes",
                  display_name: "Size",
                  select_type: "single",
                  is_template: true,
                  is_required: true,
                  min_select: 1,
                  max_select: 1,
                  sort_order: 0,
                  items: [
                    {
                      id: "item-regular",
                      name: "Regular",
                      description: null,
                      price_delta: "0",
                      price_delta_override: null,
                      is_default: true,
                      sort_order: 0,
                    },
                    {
                      id: "item-large",
                      name: "Large",
                      description: "13-inch diameter, serves 1-2",
                      price_delta: "250",
                      price_delta_override: "250",
                      is_default: false,
                      sort_order: 1,
                    },
                  ],
                },
              ],
            },
          ],
          modifierGroups: [
            {
              id: "group-size",
              business_id: "biz-1",
              name: "Size",
              display_name: "Size",
              select_type: "single",
              is_template: true,
              items: [
                {
                  id: "item-regular",
                  name: "Regular",
                  description: null,
                  price_delta: "0",
                  is_default: true,
                  sort_order: 0,
                },
                {
                  id: "item-large",
                  name: "Large",
                  description: "13-inch diameter, serves 1-2",
                  price_delta: "250",
                  is_default: false,
                  sort_order: 1,
                },
              ],
            },
          ],
          openProductId: "prod-burger",
        }}
      />,
    );

    expect(html).toContain("Edit dish");
    expect(html).toContain("Classic Beef Burger");
    expect(html).toContain("<textarea");
    expect(html).toContain('id="dish-description"');
    expect(html).toContain("min-h-24");
    expect(html).toContain('data-product-grid="compact-card"');
    expect(html).toContain('data-product-card="compact"');
    expect(html).toContain("grid gap-3 sm:grid-cols-2 xl:grid-cols-3");
    expect(html).toContain("min-h-[112px]");
    expect(html).toContain("max-w-[260px]");
    expect(html).not.toContain("group/product-card");
    expect(html).not.toContain("min-w-[236px] max-w-[236px]");
    expect(html).not.toContain("h-28");
    expect(html).not.toContain("View details");
    expect(html).toContain("text-base font-semibold leading-none");
    expect(html).toContain("Options &amp; modifiers");
    expect(html).toContain("All saved templates are already attached to this dish.");
    expect(html).not.toContain("Use template");
    expect(html).not.toContain("Add template");
    expect(html).not.toContain("Choose from your template library");
    expect(html).toContain("Add dish option");
    expect(html).toContain("Manage templates");
    expect(html).toContain("Template");
    expect(html).toContain('data-compact-template="true"');
    expect(html).toContain('data-compact-template-rules="true"');
    expect(html).toContain('data-compact-template-options="true"');
    expect(html).toContain("Burger sizes");
    expect(html).toContain("Single choice");
    expect(html).toContain("13-inch diameter, serves 1-2");
    expect(html).not.toContain("Template names are shared; availability and prices apply to this dish.");
    expect(html).not.toContain("Customer details, e.g. 500 ml or serves 2");
    expect(html).not.toContain("Add item");
    expect(html).not.toContain("Action");
    expect(html).not.toContain('aria-label="Duplicate Size group"');
    expect(html).not.toContain('aria-label="Collapse option group"');
    expect(html).not.toContain("Drag dishes to reorder");
    expect(html).not.toContain("Customer label");
    expect(html).toContain("Required");
    expect(html).not.toContain(">Min<");
    expect(html).not.toContain(">Max<");
    expect(html).not.toContain("Maximum choices");
    expect(html).toContain("Regular");
    expect(html).toContain("Large");
    expect(html).toContain("Enabled");
    expect(html).toContain("Save dish");
  });

  it("keeps dish-only modifier group actions compact in an overflow menu", () => {
    const html = renderToStaticMarkup(
      <MenuBuilder
        initialState={{
          accessToken: "token",
          businessId: "biz-1",
          categories: [
            {
              id: "cat-burgers",
              business_id: "biz-1",
              name: "Burgers",
              sort_order: 0,
              is_active: true,
              created_at: "2026-06-22T00:00:00Z",
            },
          ],
          products: [
            {
              id: "prod-burger",
              business_id: "biz-1",
              category_id: "cat-burgers",
              name: "Classic Burger",
              description: "Beef patty, cheese, sauce",
              price: "850",
              image_url: null,
              is_available: true,
              is_archived: false,
              tags: [],
              prep_minutes: 15,
              sort_order: 0,
              modifier_groups: [
                {
                  assignment_id: "assignment-cheese",
                  modifier_group_id: "dish-group-cheese",
                  name: "Extra cheese",
                  display_name: "Add cheese",
                  select_type: "multi",
                  is_template: false,
                  is_required: false,
                  min_select: 0,
                  max_select: 1,
                  sort_order: 0,
                  items: [
                    {
                      id: "item-cheddar",
                      name: "Cheddar",
                      description: null,
                      price_delta: "120",
                      price_delta_override: "120",
                      is_default: false,
                      sort_order: 0,
                    },
                  ],
                },
              ],
            },
          ],
          modifierGroups: [],
          openProductId: "prod-burger",
        }}
      />,
    );

    expect(html).toContain("Dish only");
    expect(html).toContain('data-compact-dish-only="true"');
    expect(html).toContain('aria-label="Open Extra cheese group actions"');
    expect(html).toContain("Make reusable");
    expect(html).toContain("Delete group");
    expect(html).toContain("Add details");
    expect(html).not.toContain("Save as template");
    expect(html).not.toContain("Customer details, e.g. 500 ml or serves 2");
  });

  it("shows saved modifier groups that are not already attached to the dish", () => {
    const html = renderToStaticMarkup(
      <MenuBuilder
        initialState={{
          accessToken: "token",
          businessId: "biz-1",
          categories: [
            {
              id: "cat-mains",
              business_id: "biz-1",
              name: "Mains",
              sort_order: 0,
              is_active: true,
              created_at: "2026-06-22T00:00:00Z",
            },
          ],
          products: [
            {
              id: "prod-burger",
              business_id: "biz-1",
              category_id: "cat-mains",
              name: "Classic Beef Burger",
              description: "Smash patty, cheddar, house sauce",
              price: "850",
              image_url: null,
              is_available: true,
              is_archived: false,
              tags: [],
              prep_minutes: 20,
              sort_order: 0,
              modifier_groups: [
                {
                  assignment_id: "assignment-size",
                  modifier_group_id: "group-size",
                  name: "Burger sizes",
                  display_name: "Size",
                  select_type: "single",
                  is_template: true,
                  is_required: true,
                  min_select: 1,
                  max_select: 1,
                  sort_order: 0,
                  items: [
                    {
                      id: "item-regular",
                      name: "Regular",
                      price_delta: "0",
                      price_delta_override: null,
                      is_default: true,
                      sort_order: 0,
                    },
                  ],
                },
              ],
            },
          ],
          modifierGroups: [
            {
              id: "group-size",
              business_id: "biz-1",
              name: "Size",
              display_name: "Size",
              select_type: "single",
              is_template: true,
              items: [
                {
                  id: "item-regular",
                  name: "Regular",
                  price_delta: "0",
                  is_default: true,
                  sort_order: 0,
                },
              ],
            },
            {
              id: "group-addons",
              business_id: "biz-1",
              name: "Add-ons",
              display_name: "Add-ons",
              select_type: "multi",
              is_template: true,
              items: [
                {
                  id: "item-fries",
                  name: "Fries",
                  price_delta: "150",
                  is_default: false,
                  sort_order: 0,
                },
              ],
            },
          ],
          openProductId: "prod-burger",
        }}
      />,
    );

    expect(html).toContain("Choose another template");
    expect(html).toContain("Add another template");
    expect(html).toContain("Select a saved template to attach it to this dish.");
    expect(html).not.toContain("Use template");
    expect(html).not.toContain("No available groups");
    expect(html).not.toContain("All saved templates are already attached to this dish.");
  });

  it("renders a visible modifier template manager", () => {
    const html = renderToStaticMarkup(
      <ModifierTemplateManagerContent
        groups={[]}
        isSaving={false}
        onSave={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(html).toContain("Modifier templates");
    expect(html).toContain("Create template");
    expect(html).toContain("Internal name");
    expect(html).toContain("Customer label");
    expect(html).toContain("No templates yet");
  });
});
