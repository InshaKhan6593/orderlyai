import { describe, expect, it, vi } from "vitest";

import {
  buildModifierGroupPayload,
  buildProductPayload,
  createOptionGroupDraft,
  createOptionGroupDraftFromLibrary,
  createOptionItemDraft,
  createDishDraftFromProduct,
  deleteCategory,
  deleteModifierGroup,
  saveMenuDish,
  updateModifierGroup,
  updateCategoryActive,
  updateCategoryName,
  uploadMenuItemImage,
  validateMenuDishDraft,
  type CategoryOut,
  type MenuDishDraft,
  type ProductOut,
} from "@/lib/menu";

const categories: CategoryOut[] = [
  {
    id: "cat-mains",
    business_id: "biz-1",
    name: "Mains",
    sort_order: 0,
    is_active: true,
    created_at: "2026-06-22T00:00:00Z",
  },
];

function draft(overrides: Partial<MenuDishDraft> = {}): MenuDishDraft {
  return {
    id: null,
    name: "Classic Beef Burger",
    categoryId: "cat-mains",
    description: "Smash patty, cheddar, house sauce",
    price: "850",
    imageUrl: "",
    isAvailable: true,
    tags: ["bestseller", "halal"],
    prepMinutes: "20",
    optionGroups: [
      {
        clientId: "group-size",
        modifierGroupId: "modifier-size",
        name: "Burger sizes",
        displayName: "Size",
        selectType: "single",
        isTemplate: true,
        isDefinitionEditable: false,
        isRequired: true,
        minSelect: "1",
        maxSelect: "1",
        items: [
          {
            clientId: "item-regular",
            optionId: "item-regular",
            name: "Regular",
            priceDelta: "0",
            priceDeltaOverride: null,
            isDefault: true,
            isEnabled: true,
          },
          {
            clientId: "item-large",
            optionId: "item-large",
            name: "Large",
            priceDelta: "250",
            priceDeltaOverride: "250",
            isDefault: false,
            isEnabled: true,
          },
        ],
      },
    ],
    ...overrides,
  };
}

describe("menu helpers", () => {
  it("derives modifier limits from selection type and required state", () => {
    const single = draft({
      optionGroups: [
        {
          ...draft().optionGroups[0],
          isRequired: false,
          minSelect: "9",
          maxSelect: "9",
        },
      ],
    });
    const multi = draft({
      optionGroups: [
        {
          ...draft().optionGroups[0],
          selectType: "multi",
          isRequired: true,
          minSelect: "0",
          maxSelect: "2",
        },
      ],
    });

    expect(buildProductPayload(single).modifier_groups[0]).toMatchObject({
      is_required: false,
      min_select: 0,
      max_select: 1,
    });
    expect(buildProductPayload(multi).modifier_groups[0]).toMatchObject({
      is_required: true,
      min_select: 1,
      max_select: 2,
    });
  });

  it("assigns meaningful limits when attaching reusable templates", () => {
    const pattyCount = createOptionGroupDraftFromLibrary({
      id: "group-patties",
      business_id: "biz-1",
      name: "Burger patty count",
      display_name: "Choose patties",
      select_type: "single",
      is_template: true,
      items: [
        {
          id: "single",
          name: "Single",
          description: null,
          price_delta: "0",
          is_default: true,
          sort_order: 0,
        },
        {
          id: "double",
          name: "Double",
          description: null,
          price_delta: "250",
          is_default: false,
          sort_order: 1,
        },
      ],
    });
    const addOns = createOptionGroupDraftFromLibrary({
      id: "group-addons",
      business_id: "biz-1",
      name: "Burger add-ons",
      display_name: "Add-ons",
      select_type: "multi",
      is_template: true,
      items: [
        {
          id: "cheese",
          name: "Extra cheese",
          description: null,
          price_delta: "100",
          is_default: false,
          sort_order: 0,
        },
        {
          id: "jalapenos",
          name: "Jalapenos",
          description: null,
          price_delta: "50",
          is_default: false,
          sort_order: 1,
        },
      ],
    });

    expect(pattyCount).toMatchObject({
      isRequired: true,
      minSelect: "1",
      maxSelect: "1",
    });
    expect(addOns).toMatchObject({
      isRequired: false,
      minSelect: "0",
      maxSelect: "2",
    });
  });

  it("preserves customer-facing modifier option descriptions", () => {
    const group = createOptionGroupDraft({
      name: "Pizza sizes",
      displayName: "Size",
      isTemplate: true,
      items: [
        createOptionItemDraft({
          name: "Small",
          description: "13-inch diameter, serves 1-2",
        }),
      ],
    });

    expect(buildModifierGroupPayload(group).items[0]).toMatchObject({
      name: "Small",
      description: "13-inch diameter, serves 1-2",
    });
  });

  it("builds the product payload with reusable modifier-group assignments", () => {
    expect(buildProductPayload(draft())).toEqual({
      name: "Classic Beef Burger",
      category_id: "cat-mains",
      description: "Smash patty, cheddar, house sauce",
      price: "850",
      image_url: null,
      is_available: true,
      tags: ["bestseller", "halal"],
      prep_minutes: 20,
      modifier_groups: [
        {
          modifier_group_id: "modifier-size",
          is_required: true,
          min_select: 1,
          max_select: 1,
          sort_order: 0,
          items: [
            {
              option_id: "item-regular",
              price_delta: null,
              is_default: true,
            },
            {
              option_id: "item-large",
              price_delta: "250",
              is_default: false,
            },
          ],
        },
      ],
    });
  });

  it("allows a sole required option while validating dish fields", () => {
    expect(
      validateMenuDishDraft(
        draft({
          name: "",
          categoryId: "",
          price: "-1",
          optionGroups: [
            {
              clientId: "group-size",
              modifierGroupId: null,
              name: "Burger sizes",
              displayName: "Size",
              selectType: "single",
              isTemplate: false,
              isDefinitionEditable: true,
              isRequired: true,
              minSelect: "1",
              maxSelect: "1",
              items: [
                {
                  clientId: "item-regular",
                  optionId: null,
                  name: "Regular",
                  priceDelta: "0",
                  priceDeltaOverride: null,
                  isDefault: true,
                  isEnabled: true,
                },
              ],
            },
          ],
        }),
      ),
    ).toEqual({
      name: "Dish name is required.",
      categoryId: "Choose a category.",
      price: "Enter a valid non-negative price.",
    });
  });

  it("maps an existing product into an editable dish draft", () => {
    const product: ProductOut = {
      id: "prod-1",
      business_id: "biz-1",
      category_id: "cat-mains",
      name: "Classic Beef Burger",
      description: "Smash patty",
      price: "850.00",
      image_url: null,
      is_available: true,
      is_archived: false,
      tags: ["bestseller"],
      prep_minutes: 20,
      sort_order: 0,
      modifier_groups: [
        {
          assignment_id: "assignment-1",
          modifier_group_id: "group-1",
          name: "Size",
          display_name: "Size",
          select_type: "single",
          is_template: true,
          is_required: true,
          min_select: 0,
          max_select: null,
          sort_order: 0,
          items: [
            {
              id: "item-1",
              name: "Regular",
              price_delta: "0.00",
              price_delta_override: null,
              is_default: true,
              sort_order: 0,
            },
          ],
        },
      ],
    };

    expect(createDishDraftFromProduct(product).optionGroups[0]).toMatchObject({
      clientId: "assignment-1",
      modifierGroupId: "group-1",
      name: "Size",
      displayName: "Size",
      selectType: "single",
      isTemplate: true,
      isDefinitionEditable: false,
      isRequired: true,
      minSelect: "1",
      maxSelect: "1",
    });
  });

  it("merges disabled template options into an existing dish draft", () => {
    const product = {
      id: "prod-1",
      business_id: "biz-1",
      category_id: "cat-mains",
      name: "Double Burger",
      description: null,
      price: "900.00",
      image_url: null,
      is_available: true,
      is_archived: false,
      tags: [],
      prep_minutes: null,
      sort_order: 0,
      modifier_groups: [
        {
          assignment_id: "assignment-1",
          modifier_group_id: "group-patties",
          name: "Burger patties",
          display_name: "Patties",
          select_type: "single" as const,
          is_template: true,
          is_required: true,
          min_select: 1,
          max_select: 1,
          sort_order: 0,
          items: [
            {
              id: "double",
              name: "Double",
              price_delta: "175.00",
              price_delta_override: "175.00",
              is_default: true,
              sort_order: 1,
            },
          ],
        },
      ],
    } satisfies ProductOut;
    const templates = [
      {
        id: "group-patties",
        business_id: "biz-1",
        name: "Burger patties",
        display_name: "Patties",
        select_type: "single" as const,
        is_template: true,
        items: [
          {
            id: "single",
            name: "Single",
            price_delta: "0.00",
            is_default: true,
            sort_order: 0,
          },
          {
            id: "double",
            name: "Double",
            price_delta: "200.00",
            is_default: false,
            sort_order: 1,
          },
        ],
      },
    ];

    const group = createDishDraftFromProduct(product, templates).optionGroups[0];
    expect(group.items).toEqual([
      expect.objectContaining({ optionId: "single", isEnabled: false }),
      expect.objectContaining({
        optionId: "double",
        isEnabled: true,
        priceDelta: "175.00",
        priceDeltaOverride: "175.00",
      }),
    ]);
  });

  it("saves new and existing dishes through the product endpoints", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "new-prod" }), { status: 201 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "existing-prod" }), { status: 200 }),
      );

    await saveMenuDish({
      accessToken: "token",
      businessId: "biz-1",
      draft: draft(),
      categories,
      fetcher,
    });
    await saveMenuDish({
      accessToken: "token",
      businessId: "biz-1",
      draft: draft({ id: "existing-prod" }),
      categories,
      fetcher,
    });

    expect(fetcher).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/api/v1/businesses/biz-1/products",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetcher).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/businesses/biz-1/products/existing-prod",
      expect.objectContaining({ method: "PATCH" }),
    );
  });

  it("creates a dish-specific group atomically through the product request", async () => {
    const newGroupDraft = {
      ...draft().optionGroups[0],
      clientId: "new-size",
      modifierGroupId: null,
      isTemplate: false,
      isDefinitionEditable: true,
      items: draft().optionGroups[0].items.map((item) => ({
        ...item,
        optionId: null,
      })),
    };
    const fetcher = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ id: "new-prod" }), { status: 201 }),
    );

    await saveMenuDish({
      accessToken: "token",
      businessId: "biz-1",
      draft: draft({ optionGroups: [newGroupDraft] }),
      categories,
      fetcher,
    });

    expect(fetcher).toHaveBeenCalledTimes(1);
    const productRequest = fetcher.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(productRequest.body))).toMatchObject({
      modifier_groups: [
        {
          definition: {
            name: "Burger sizes",
            display_name: "Size",
            is_template: false,
          },
        },
      ],
    });
  });

  it("updates and deletes reusable modifier templates", async () => {
    const template = draft().optionGroups[0];
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "modifier-size" }), { status: 200 }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    await updateModifierGroup({
      accessToken: "token",
      businessId: "biz-1",
      groupId: "modifier-size",
      group: template,
      fetcher,
    });
    await deleteModifierGroup({
      accessToken: "token",
      businessId: "biz-1",
      groupId: "modifier-size",
      fetcher,
    });

    expect(fetcher).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/api/v1/businesses/biz-1/modifier-groups/modifier-size",
      expect.objectContaining({ method: "PATCH" }),
    );
    expect(fetcher).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/businesses/biz-1/modifier-groups/modifier-size",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("PATCHes category active state through the tenant category endpoint", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ...categories[0], is_active: false }), {
        status: 200,
      }),
    );

    const updated = await updateCategoryActive({
      accessToken: "token",
      businessId: "biz-1",
      categoryId: "cat-mains",
      isActive: false,
      fetcher,
    });

    expect(updated.is_active).toBe(false);
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/businesses/biz-1/categories/cat-mains",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ is_active: false }),
      }),
    );
  });

  it("PATCHes category name and DELETEs categories through tenant endpoints", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...categories[0], name: "Burgers" }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    const updated = await updateCategoryName({
      accessToken: "token",
      businessId: "biz-1",
      categoryId: "cat-mains",
      name: "Burgers",
      fetcher,
    });
    await deleteCategory({
      accessToken: "token",
      businessId: "biz-1",
      categoryId: "cat-mains",
      fetcher,
    });

    expect(updated.name).toBe("Burgers");
    expect(fetcher).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/api/v1/businesses/biz-1/categories/cat-mains",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ name: "Burgers" }),
      }),
    );
    expect(fetcher).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/businesses/biz-1/categories/cat-mains",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("uploads a menu item image as raw image bytes", async () => {
    const image = new Blob(["image-bytes"], { type: "image/png" });
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          image_url: "http://localhost:8000/uploads/menu/biz-1/image.png",
        }),
        { status: 201 },
      ),
    );

    const imageUrl = await uploadMenuItemImage({
      accessToken: "token",
      businessId: "biz-1",
      image,
      fetcher,
    });

    expect(imageUrl).toBe("http://localhost:8000/uploads/menu/biz-1/image.png");
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/businesses/biz-1/products/images",
      expect.objectContaining({
        method: "POST",
        body: image,
        headers: expect.objectContaining({
          Authorization: "Bearer token",
          "Content-Type": "image/png",
        }),
      }),
    );
  });
});
