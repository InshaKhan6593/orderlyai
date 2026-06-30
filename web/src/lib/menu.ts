import { apiUrl } from "@/lib/api";
import { ApiError } from "@/lib/auth";

type Fetcher = typeof fetch;

export type CategoryOut = {
  id: string;
  business_id: string;
  name: string;
  sort_order: number;
  is_active: boolean;
  created_at: string;
};

export type ModifierOptionOut = {
  id: string;
  name: string;
  description: string | null;
  price_delta: string | number;
  is_default: boolean;
  sort_order: number;
};

export type ModifierGroupOut = {
  id: string;
  business_id: string;
  name: string;
  display_name: string;
  select_type: "single" | "multi";
  is_template: boolean;
  items: ModifierOptionOut[];
};

export type ProductModifierGroupOut = {
  assignment_id: string;
  modifier_group_id: string;
  name: string;
  display_name: string;
  select_type: "single" | "multi";
  is_template: boolean;
  is_required: boolean;
  min_select: number;
  max_select: number | null;
  sort_order: number;
  items: (ModifierOptionOut & { price_delta_override: string | number | null })[];
};

export type ProductOut = {
  id: string;
  business_id: string;
  category_id: string | null;
  name: string;
  description: string | null;
  price: string | number;
  image_url: string | null;
  is_available: boolean;
  is_archived: boolean;
  tags: string[];
  prep_minutes: number | null;
  sort_order: number;
  modifier_groups: ProductModifierGroupOut[];
};

export type MenuOptionItemDraft = {
  clientId: string;
  optionId: string | null;
  name: string;
  description: string;
  priceDelta: string;
  priceDeltaOverride: string | null;
  isDefault: boolean;
  isEnabled: boolean;
};

export type MenuOptionGroupDraft = {
  clientId: string;
  modifierGroupId: string | null;
  name: string;
  displayName: string;
  selectType: "single" | "multi";
  isTemplate: boolean;
  isDefinitionEditable: boolean;
  isRequired: boolean;
  minSelect: string;
  maxSelect: string;
  items: MenuOptionItemDraft[];
};

export type MenuDishDraft = {
  id: string | null;
  name: string;
  categoryId: string;
  description: string;
  price: string;
  imageUrl: string;
  isAvailable: boolean;
  tags: string[];
  prepMinutes: string;
  optionGroups: MenuOptionGroupDraft[];
};

export type MenuDishErrors = {
  name?: string;
  categoryId?: string;
  price?: string;
  prepMinutes?: string;
  optionGroups?: Record<string, string>;
};

export type ProductPayload = {
  name: string;
  category_id: string | null;
  description: string | null;
  price: string;
  image_url: string | null;
  is_available: boolean;
  tags: string[];
  prep_minutes: number | null;
  modifier_groups: {
    modifier_group_id?: string;
    definition?: ModifierGroupPayload;
    is_required: boolean;
    min_select: number;
    max_select: number | null;
    sort_order: number;
    items?: {
      option_id: string;
      price_delta: string | null;
      is_default: boolean;
    }[];
  }[];
};

export type ModifierGroupPayload = {
  name: string;
  display_name: string;
  select_type: "single" | "multi";
  is_template: boolean;
  items: {
    id?: string;
    name: string;
    description: string | null;
    price_delta: string;
    is_default: boolean;
    sort_order: number;
  }[];
};

type ProductImageUploadOut = {
  image_url: string;
};

function clientId(prefix: string): string {
  return `${prefix}-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
}

function trimmedOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function isNonNegativeNumber(value: string, integerOnly = false): boolean {
  if (value.trim() === "") return false;
  const parsed = Number(value);
  return (
    Number.isFinite(parsed) &&
    parsed >= 0 &&
    (!integerOnly || Number.isInteger(parsed))
  );
}

function optionalNumber(value: string): number | null {
  return value.trim() ? Number(value) : null;
}

function moneyOrZero(value: string): string {
  return value.trim() || "0";
}

function stringValue(value: string | number | null): string {
  return value === null ? "" : String(value);
}

export function createOptionItemDraft(
  patch: Partial<MenuOptionItemDraft> = {},
): MenuOptionItemDraft {
  return {
    clientId: clientId("item"),
    optionId: null,
    name: "",
    description: "",
    priceDelta: "0",
    priceDeltaOverride: null,
    isDefault: false,
    isEnabled: true,
    ...patch,
  };
}

export function createOptionGroupDraft(
  patch: Partial<MenuOptionGroupDraft> = {},
): MenuOptionGroupDraft {
  return {
    clientId: clientId("group"),
    modifierGroupId: null,
    name: "",
    displayName: "",
    selectType: "single",
    isTemplate: false,
    isDefinitionEditable: true,
    isRequired: false,
    minSelect: "0",
    maxSelect: "1",
    items: [createOptionItemDraft()],
    ...patch,
  };
}

export function createOptionGroupDraftFromLibrary(
  group: ModifierGroupOut,
): MenuOptionGroupDraft {
  const hasDefaultOption = group.items.some((item) => item.is_default);
  return createOptionGroupDraft({
    modifierGroupId: group.id,
    name: group.name,
    displayName: group.display_name,
    selectType: group.select_type,
    isTemplate: true,
    isDefinitionEditable: false,
    isRequired: hasDefaultOption,
    minSelect: hasDefaultOption ? "1" : "0",
    maxSelect:
      group.select_type === "single" ? "1" : String(group.items.length),
    items: group.items.map((item) =>
      createOptionItemDraft({
        clientId: item.id,
        optionId: item.id,
        name: item.name,
        description: item.description ?? "",
        priceDelta: stringValue(item.price_delta),
        priceDeltaOverride: null,
        isDefault: item.is_default,
        isEnabled: true,
      }),
    ),
  });
}

export function createEmptyDishDraft(categoryId = ""): MenuDishDraft {
  return {
    id: null,
    name: "",
    categoryId,
    description: "",
    price: "",
    imageUrl: "",
    isAvailable: true,
    tags: [],
    prepMinutes: "",
    optionGroups: [],
  };
}

export function createDishDraftFromProduct(
  product: ProductOut,
  modifierGroups: ModifierGroupOut[] = [],
): MenuDishDraft {
  return {
    id: product.id,
    name: product.name,
    categoryId: product.category_id ?? "",
    description: product.description ?? "",
    price: stringValue(product.price),
    imageUrl: product.image_url ?? "",
    isAvailable: product.is_available,
    tags: product.tags,
    prepMinutes: product.prep_minutes === null ? "" : String(product.prep_minutes),
    optionGroups: product.modifier_groups.map((group) => {
      const libraryGroup = modifierGroups.find(
        (candidate) => candidate.id === group.modifier_group_id,
      );
      const enabledById = new Map(group.items.map((item) => [item.id, item]));
      const definitions = libraryGroup?.items ?? group.items;
      const minimum = group.is_required
        ? Math.max(group.min_select, 1)
        : group.min_select;
      const maximum =
        group.select_type === "single"
          ? 1
          : group.max_select && group.max_select > 0
            ? group.max_select
            : enabledById.size;
      return {
        clientId: group.assignment_id,
        modifierGroupId: group.modifier_group_id,
        name: group.name,
        displayName: group.display_name,
        selectType: group.select_type,
        isTemplate: group.is_template,
        isDefinitionEditable: !group.is_template,
        isRequired: group.is_required,
        minSelect: String(minimum),
        maxSelect: String(maximum),
        items: definitions.map((definition) => {
          const enabled = enabledById.get(definition.id);
          return {
            clientId: definition.id,
            optionId: definition.id,
            name: definition.name,
            description: definition.description ?? "",
            priceDelta: stringValue(enabled?.price_delta ?? definition.price_delta),
            priceDeltaOverride: enabled
              ? stringValue(enabled.price_delta_override) || null
              : null,
            isDefault: enabled?.is_default ?? false,
            isEnabled: Boolean(enabled),
          };
        }),
      };
    }),
  };
}

export function validateMenuDishDraft(draft: MenuDishDraft): MenuDishErrors {
  const errors: MenuDishErrors = {};
  const groupErrors: Record<string, string> = {};

  if (!draft.name.trim()) errors.name = "Dish name is required.";
  if (!draft.categoryId) errors.categoryId = "Choose a category.";
  if (!isNonNegativeNumber(draft.price)) {
    errors.price = "Enter a valid non-negative price.";
  }
  if (draft.prepMinutes.trim() && !isNonNegativeNumber(draft.prepMinutes, true)) {
    errors.prepMinutes = "Enter prep time in whole minutes.";
  }

  for (const group of draft.optionGroups) {
    if (!group.name.trim()) {
      groupErrors[group.clientId] = "Group name is required.";
      continue;
    }
    if (!group.displayName.trim()) {
      groupErrors[group.clientId] = "Customer label is required.";
      continue;
    }
    const enabledItems = group.items.filter((item) => item.isEnabled);
    if (enabledItems.length === 0) {
      groupErrors[group.clientId] = "Enable at least one option.";
      continue;
    }
    if (
      group.selectType === "multi" &&
      (!group.maxSelect.trim() ||
        !isNonNegativeNumber(group.maxSelect, true) ||
        Number(group.maxSelect) < 1)
    ) {
      groupErrors[group.clientId] = "Maximum choices must be a positive whole number.";
      continue;
    }
    const invalidItem = group.items.find(
      (item) =>
        !item.name.trim() || !isNonNegativeNumber(item.priceDelta || "0"),
    );
    if (invalidItem) {
      groupErrors[group.clientId] =
        "Each option item needs a name and non-negative price delta.";
    }
  }

  if (Object.keys(groupErrors).length > 0) errors.optionGroups = groupErrors;
  return errors;
}

export function hasMenuDishErrors(errors: MenuDishErrors): boolean {
  return Boolean(
    errors.name ||
      errors.categoryId ||
      errors.price ||
      errors.prepMinutes ||
      (errors.optionGroups && Object.keys(errors.optionGroups).length > 0),
  );
}

export function buildModifierGroupPayload(
  group: MenuOptionGroupDraft,
): ModifierGroupPayload {
  return {
    name: group.name.trim(),
    display_name: group.displayName.trim(),
    select_type: group.selectType,
    is_template: group.isTemplate,
    items: group.items.map((item, itemIndex) => ({
      ...(item.optionId ? { id: item.optionId } : {}),
      name: item.name.trim(),
      description: (item.description ?? "").trim() || null,
      price_delta: moneyOrZero(item.priceDelta),
      is_default: item.isDefault,
      sort_order: itemIndex,
    })),
  };
}

export function buildProductPayload(
  draft: MenuDishDraft,
): ProductPayload {
  return {
    name: draft.name.trim(),
    category_id: draft.categoryId || null,
    description: trimmedOrNull(draft.description),
    price: moneyOrZero(draft.price),
    image_url: trimmedOrNull(draft.imageUrl),
    is_available: draft.isAvailable,
    tags: draft.tags.map((tag) => tag.trim()).filter(Boolean),
    prep_minutes: optionalNumber(draft.prepMinutes),
    modifier_groups: draft.optionGroups.map((group, groupIndex) => {
      const enabledCount = group.items.filter((item) => item.isEnabled).length;
      const maximumChoices =
        group.selectType === "single"
          ? 1
          : Number(group.maxSelect) > 0
            ? Number(group.maxSelect)
            : enabledCount;
      return {
        ...(group.modifierGroupId
          ? { modifier_group_id: group.modifierGroupId }
          : {}),
        ...(group.isDefinitionEditable
          ? { definition: buildModifierGroupPayload(group) }
          : {}),
        is_required: group.isRequired,
        min_select: group.isRequired ? 1 : 0,
        max_select: maximumChoices,
        sort_order: groupIndex,
        items: group.isTemplate && !group.isDefinitionEditable
          ? group.items
              .filter((item) => item.isEnabled && item.optionId)
              .map((item) => ({
                option_id: item.optionId as string,
                price_delta: item.priceDeltaOverride,
                is_default: item.isDefault,
              }))
          : undefined,
      };
    }),
  };
}

async function menuRequest<T>({
  path,
  accessToken,
  method = "GET",
  body,
  fetcher = fetch,
}: {
  path: string;
  accessToken: string;
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  fetcher?: Fetcher;
}): Promise<T> {
  let response: Response;
  try {
    response = await fetcher(apiUrl(path), {
      method,
      headers: {
        Authorization: `Bearer ${accessToken}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch {
    throw new ApiError(
      "Couldn't reach the server. Is the API running on http://localhost:8000?",
      0,
    );
  }

  if (!response.ok) {
    let message = "Couldn't save your menu. Please try again.";
    let code: string | undefined;
    try {
      const payload = (await response.json()) as {
        error?: { message?: string; code?: string };
      };
      message = payload.error?.message ?? message;
      code = payload.error?.code;
    } catch {
      // Keep the stable fallback for non-JSON responses.
    }
    throw new ApiError(message, response.status, code);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function listCategories({
  accessToken,
  businessId,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  fetcher?: Fetcher;
}): Promise<CategoryOut[]> {
  return menuRequest<CategoryOut[]>({
    path: `/businesses/${businessId}/categories`,
    accessToken,
    fetcher,
  });
}

export function createCategory({
  accessToken,
  businessId,
  name,
  sortOrder = 0,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  name: string;
  sortOrder?: number;
  fetcher?: Fetcher;
}): Promise<CategoryOut> {
  return menuRequest<CategoryOut>({
    path: `/businesses/${businessId}/categories`,
    accessToken,
    method: "POST",
    body: { name: name.trim(), sort_order: sortOrder, is_active: true },
    fetcher,
  });
}

export function updateCategoryActive({
  accessToken,
  businessId,
  categoryId,
  isActive,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  categoryId: string;
  isActive: boolean;
  fetcher?: Fetcher;
}): Promise<CategoryOut> {
  return menuRequest<CategoryOut>({
    path: `/businesses/${businessId}/categories/${categoryId}`,
    accessToken,
    method: "PATCH",
    body: { is_active: isActive },
    fetcher,
  });
}

export function updateCategoryName({
  accessToken,
  businessId,
  categoryId,
  name,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  categoryId: string;
  name: string;
  fetcher?: Fetcher;
}): Promise<CategoryOut> {
  return menuRequest<CategoryOut>({
    path: `/businesses/${businessId}/categories/${categoryId}`,
    accessToken,
    method: "PATCH",
    body: { name: name.trim() },
    fetcher,
  });
}

export function deleteCategory({
  accessToken,
  businessId,
  categoryId,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  categoryId: string;
  fetcher?: Fetcher;
}): Promise<void> {
  return menuRequest<void>({
    path: `/businesses/${businessId}/categories/${categoryId}`,
    accessToken,
    method: "DELETE",
    fetcher,
  });
}

export function listModifierGroups({
  accessToken,
  businessId,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  fetcher?: Fetcher;
}): Promise<ModifierGroupOut[]> {
  return menuRequest<ModifierGroupOut[]>({
    path: `/businesses/${businessId}/modifier-groups`,
    accessToken,
    fetcher,
  });
}

export function createModifierGroup({
  accessToken,
  businessId,
  group,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  group: MenuOptionGroupDraft;
  fetcher?: Fetcher;
}): Promise<ModifierGroupOut> {
  return menuRequest<ModifierGroupOut>({
    path: `/businesses/${businessId}/modifier-groups`,
    accessToken,
    method: "POST",
    body: buildModifierGroupPayload(group),
    fetcher,
  });
}

export function updateModifierGroup({
  accessToken,
  businessId,
  groupId,
  group,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  groupId: string;
  group: MenuOptionGroupDraft;
  fetcher?: Fetcher;
}): Promise<ModifierGroupOut> {
  return menuRequest<ModifierGroupOut>({
    path: `/businesses/${businessId}/modifier-groups/${groupId}`,
    accessToken,
    method: "PATCH",
    body: buildModifierGroupPayload(group),
    fetcher,
  });
}

export function deleteModifierGroup({
  accessToken,
  businessId,
  groupId,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  groupId: string;
  fetcher?: Fetcher;
}): Promise<void> {
  return menuRequest<void>({
    path: `/businesses/${businessId}/modifier-groups/${groupId}`,
    accessToken,
    method: "DELETE",
    fetcher,
  });
}

export function listProducts({
  accessToken,
  businessId,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  fetcher?: Fetcher;
}): Promise<ProductOut[]> {
  return menuRequest<ProductOut[]>({
    path: `/businesses/${businessId}/products`,
    accessToken,
    fetcher,
  });
}

export async function uploadMenuItemImage({
  accessToken,
  businessId,
  image,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  image: Blob;
  fetcher?: Fetcher;
}): Promise<string> {
  let response: Response;
  try {
    response = await fetcher(
      apiUrl(`/businesses/${businessId}/products/images`),
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": image.type || "application/octet-stream",
        },
        body: image,
      },
    );
  } catch {
    throw new ApiError(
      "Couldn't reach the server. Is the API running on http://localhost:8000?",
      0,
    );
  }

  if (!response.ok) {
    let message = "Couldn't upload the image. Please try again.";
    let code: string | undefined;
    try {
      const payload = (await response.json()) as {
        error?: { message?: string; code?: string };
      };
      message = payload.error?.message ?? message;
      code = payload.error?.code;
    } catch {
      // Keep the stable fallback for non-JSON responses.
    }
    throw new ApiError(message, response.status, code);
  }

  const payload = (await response.json()) as ProductImageUploadOut;
  return payload.image_url;
}

export async function saveMenuDish({
  accessToken,
  businessId,
  draft,
  categories,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  draft: MenuDishDraft;
  categories: CategoryOut[];
  fetcher?: Fetcher;
}): Promise<ProductOut> {
  const errors = validateMenuDishDraft(draft);
  if (hasMenuDishErrors(errors)) {
    throw new ApiError("Check your dish details before saving.", 422);
  }
  if (!categories.some((category) => category.id === draft.categoryId)) {
    throw new ApiError("Choose a category that belongs to this business.", 422);
  }

  return menuRequest<ProductOut>({
    path: draft.id
      ? `/businesses/${businessId}/products/${draft.id}`
      : `/businesses/${businessId}/products`,
    accessToken,
    method: draft.id ? "PATCH" : "POST",
    body: buildProductPayload(draft),
    fetcher,
  });
}

export function updateProductAvailability({
  accessToken,
  businessId,
  productId,
  isAvailable,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  productId: string;
  isAvailable: boolean;
  fetcher?: Fetcher;
}): Promise<ProductOut> {
  return menuRequest<ProductOut>({
    path: `/businesses/${businessId}/products/${productId}`,
    accessToken,
    method: "PATCH",
    body: { is_available: isAvailable },
    fetcher,
  });
}

export function deleteProduct({
  accessToken,
  businessId,
  productId,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  productId: string;
  fetcher?: Fetcher;
}): Promise<void> {
  return menuRequest<void>({
    path: `/businesses/${businessId}/products/${productId}`,
    accessToken,
    method: "DELETE",
    fetcher,
  });
}

export async function seedSampleMenu({
  accessToken,
  businessId,
  categories,
  products,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  categories: CategoryOut[];
  products: ProductOut[];
  fetcher?: Fetcher;
}): Promise<{ categories: CategoryOut[]; products: ProductOut[] }> {
  const desiredCategories = ["Starters", "Mains", "Drinks", "Desserts"];
  const allCategories = [...categories];

  for (const [index, name] of desiredCategories.entries()) {
    if (!allCategories.some((category) => category.name === name)) {
      allCategories.push(
        await createCategory({
          accessToken,
          businessId,
          name,
          sortOrder: index,
          fetcher,
        }),
      );
    }
  }

  const mains = allCategories.find((category) => category.name === "Mains");
  if (!mains) return { categories: allCategories, products };

  const seededProducts = [...products];
  const sampleProducts = [
    {
      name: "Classic Beef Burger",
      description: "Smash patty, cheddar, house sauce",
      price: "850",
      tags: ["bestseller", "halal"],
      prepMinutes: "20",
      optionGroups: [
        createOptionGroupDraft({
          clientId: "seed-size",
          name: "Burger sizes",
          displayName: "Size",
          selectType: "single",
          isRequired: true,
          minSelect: "1",
          maxSelect: "1",
          items: [
            createOptionItemDraft({
              clientId: "seed-regular",
              name: "Regular",
              priceDelta: "0",
              isDefault: true,
            }),
            createOptionItemDraft({
              clientId: "seed-large",
              name: "Large",
              priceDelta: "250",
            }),
          ],
        }),
        createOptionGroupDraft({
          clientId: "seed-addons",
          name: "Burger add-ons",
          displayName: "Add-ons",
          selectType: "multi",
          minSelect: "0",
          maxSelect: "3",
          items: [
            createOptionItemDraft({
              clientId: "seed-cheese",
              name: "Extra cheese",
              priceDelta: "150",
            }),
            createOptionItemDraft({
              clientId: "seed-jalapenos",
              name: "Jalapenos",
              priceDelta: "80",
            }),
            createOptionItemDraft({
              clientId: "seed-no-onions",
              name: "No onions",
              priceDelta: "0",
            }),
          ],
        }),
      ],
    },
    {
      name: "Creamy Alfredo Pasta",
      description: "Fettuccine, parmesan, herbs",
      price: "900",
      tags: ["veg"],
      prepMinutes: "25",
      optionGroups: [],
    },
  ];

  for (const sample of sampleProducts) {
    if (seededProducts.some((product) => product.name === sample.name)) continue;
    seededProducts.push(
      await saveMenuDish({
        accessToken,
        businessId,
        categories: allCategories,
        draft: {
          ...createEmptyDishDraft(mains.id),
          name: sample.name,
          description: sample.description,
          price: sample.price,
          tags: sample.tags,
          prepMinutes: sample.prepMinutes,
          optionGroups: sample.optionGroups,
        },
        fetcher,
      }),
    );
  }

  return { categories: allCategories, products: seededProducts };
}
