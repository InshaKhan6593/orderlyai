"use client";

import {
  ArrowLeft,
  ArrowRight,
  FolderOpen,
  ImageIcon,
  MoreHorizontal,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  Unlink,
  Upload,
  X,
} from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { OnboardingShell } from "@/components/onboarding/onboarding-shell";
import { ModifierTemplateDialog } from "@/components/onboarding/modifier-template-dialog";
import {
  OnboardingCard,
  OnboardingStepHeader,
} from "@/components/onboarding/onboarding-step-ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldTitle,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
  InputGroupText,
} from "@/components/ui/input-group";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { ApiError, clearTokens } from "@/lib/auth";
import {
  pickBusinessForOwner,
  saveSelectedBusinessId,
} from "@/lib/business-selection";
import { listBusinesses } from "@/lib/business-profile";
import {
  createCategory,
  createModifierGroup,
  createDishDraftFromProduct,
  createEmptyDishDraft,
  createOptionGroupDraft,
  createOptionGroupDraftFromLibrary,
  createOptionItemDraft,
  deleteCategory,
  deleteModifierGroup,
  deleteProduct,
  hasMenuDishErrors,
  listCategories,
  listModifierGroups,
  listProducts,
  saveMenuDish,
  seedSampleMenu,
  updateCategoryActive,
  updateCategoryName,
  updateModifierGroup,
  updateProductAvailability,
  uploadMenuItemImage,
  validateMenuDishDraft,
  type CategoryOut,
  type MenuDishDraft,
  type MenuDishErrors,
  type MenuOptionGroupDraft,
  type ModifierGroupOut,
  type ProductOut,
} from "@/lib/menu";
import { saveOnboardingResumePath } from "@/lib/onboarding-progress";
import { cn } from "@/lib/utils";

type MenuBuilderInitialState = {
  accessToken: string;
  businessId: string;
  categories: CategoryOut[];
  products: ProductOut[];
  modifierGroups?: ModifierGroupOut[];
  openProductId?: string;
  openNewDish?: boolean;
  categoryDialogOpen?: boolean;
  templateManagerOpen?: boolean;
};

type MenuBuilderProps = {
  initialState?: MenuBuilderInitialState;
};

const SELECT_LIMIT_OPTIONS = ["0", "1", "2", "3", "4", "5"].map((value) => ({
  value,
  label: value,
}));

function accessTokenFromStorage(): string | null {
  return (
    window.localStorage.getItem("orderly.access_token") ??
    window.sessionStorage.getItem("orderly.access_token")
  );
}

function MenuPreviewIllustration() {
  return (
    <Image
      src="/onboarding-menu-empty-state.png"
      alt=""
      width={258}
      height={216}
      className="mx-auto h-auto w-[190px] max-w-full"
      aria-hidden="true"
    />
  );
}

function categoryProductCount(products: ProductOut[], categoryId: string): number {
  return products.filter((product) => product.category_id === categoryId).length;
}

function formatMoney(value: string | number): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return String(value);
  return amount.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function EmptyMenuPanel({
  onAddCategory,
  onAddDish,
  onSeed,
  isSeeding,
}: {
  onAddCategory: () => void;
  onAddDish: () => void;
  onSeed: () => void;
  isSeeding: boolean;
}) {
  return (
    <OnboardingCard className="mt-2">
      <CardContent className="p-0">
        <div className="grid min-h-[390px] md:grid-cols-[224px_1fr] lg:min-h-[420px]">
          <aside className="flex min-h-[210px] flex-col border-b border-border p-4 md:min-h-0 md:border-r md:border-b-0">
            <div>
              <h2 className="text-base font-medium text-foreground">
                Categories
              </h2>
            </div>

            <div className="flex flex-1 flex-col items-center justify-center gap-4 py-6 text-center">
              <div className="grid size-14 place-items-center rounded-lg border border-muted-foreground/40 bg-background">
                <FolderOpen className="size-7 stroke-[1.5] text-muted-foreground" />
              </div>
              <p className="text-sm text-foreground">No categories yet</p>
              <Button
                type="button"
                variant="outline"
                size="lg"
                onClick={onAddCategory}
                className="h-10 min-w-[140px]"
              >
                <Plus data-icon="inline-start" />
                Add category
              </Button>
            </div>
          </aside>

          <section className="flex min-h-[330px] flex-col items-center justify-center px-5 py-6 text-center sm:px-8">
            <MenuPreviewIllustration />
            <h2 className="mt-4 font-heading text-2xl leading-tight font-semibold text-foreground sm:text-[28px]">
              No dishes yet
            </h2>
            <p className="mt-2 max-w-xl text-sm text-muted-foreground sm:text-base">
              Add your first dish or seed a sample menu to get started.
            </p>

            <div className="mt-5 flex w-full max-w-lg flex-col gap-3 sm:flex-row sm:justify-center">
              <Button
                type="button"
                size="lg"
                onClick={onAddDish}
                data-menu-dish-trigger="true"
                className="h-11 min-w-[190px]"
              >
                <Plus data-icon="inline-start" />
                Add your first dish
              </Button>
              <Button
                type="button"
                variant="outline"
                size="lg"
                onClick={onSeed}
                disabled={isSeeding}
                className="h-11 min-w-[190px]"
              >
                {isSeeding ? (
                  <Spinner data-icon="inline-start" />
                ) : (
                  <Sparkles
                    data-icon="inline-start"
                    className="fill-gold text-gold"
                  />
                )}
                Seed sample menu
              </Button>
            </div>

            <p className="mt-4 text-sm text-muted-foreground">
              You can edit or remove sample items anytime.
            </p>
          </section>
        </div>
      </CardContent>
    </OnboardingCard>
  );
}

function MenuEditorPanel({
  categories,
  products,
  selectedCategoryId,
  onSelectCategory,
  onAddCategory,
  onAddDish,
  onManageTemplates,
  onEditDish,
  onEditCategory,
  onDeleteCategory,
  onToggleCategoryActive,
  onToggleAvailability,
  onDeleteDish,
}: {
  categories: CategoryOut[];
  products: ProductOut[];
  selectedCategoryId: string;
  onSelectCategory: (categoryId: string) => void;
  onAddCategory: () => void;
  onAddDish: () => void;
  onManageTemplates: () => void;
  onEditDish: (product: ProductOut) => void;
  onEditCategory: (category: CategoryOut) => void;
  onDeleteCategory: (category: CategoryOut) => void;
  onToggleCategoryActive: (category: CategoryOut, isActive: boolean) => void;
  onToggleAvailability: (product: ProductOut, isAvailable: boolean) => void;
  onDeleteDish: (product: ProductOut) => void;
}) {
  const selectedCategory = categories.find(
    (category) => category.id === selectedCategoryId,
  );
  const visibleProducts = products.filter(
    (product) => product.category_id === selectedCategoryId,
  );

  return (
    <OnboardingCard className="mt-2">
      <CardContent className="p-0">
        <div className="grid min-h-[470px] md:grid-cols-[224px_1fr]">
          <aside className="border-b border-border p-4 md:border-r md:border-b-0">
            <h2 className="text-base font-medium text-foreground">Categories</h2>

            <div className="mt-5 flex flex-col gap-2">
              {categories.map((category) => {
                const active = category.id === selectedCategoryId;
                return (
                  <div
                    key={category.id}
                    className={cn(
                      "grid h-9 grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-1 rounded-lg border px-1.5 text-left text-sm transition-colors",
                      active
                        ? "border-primary bg-primary/5 text-primary"
                        : "border-border bg-background text-foreground hover:bg-muted",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => onSelectCategory(category.id)}
                      className="flex min-w-0 items-center rounded-md px-1.5 py-1 text-left"
                    >
                      <span className="min-w-0 flex-1 truncate">
                        {category.name}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {categoryProductCount(products, category.id)}
                      </span>
                    </button>
                    <Switch
                      size="sm"
                      checked={category.is_active}
                      data-category-toggle={category.id}
                      aria-label={`${category.name} active`}
                      onCheckedChange={(checked) =>
                        onToggleCategoryActive(category, checked)
                      }
                    />
                    <details className="relative">
                      <summary
                        className="flex size-7 cursor-pointer list-none items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground [&::-webkit-details-marker]:hidden"
                        aria-label={`Open ${category.name} category actions`}
                      >
                        <MoreHorizontal className="size-4" aria-hidden="true" />
                      </summary>
                      <div className="absolute top-8 right-0 z-20 grid w-36 gap-1 rounded-lg border border-border bg-popover p-1 text-sm text-popover-foreground shadow-lg">
                        <button
                          type="button"
                          className="flex h-8 items-center gap-2 rounded-md px-2 text-left hover:bg-muted"
                          onClick={() => onEditCategory(category)}
                          aria-label={`Edit ${category.name} category`}
                        >
                          <Pencil className="size-3.5" aria-hidden="true" />
                          Edit
                        </button>
                        <button
                          type="button"
                          className="flex h-8 items-center gap-2 rounded-md px-2 text-left text-destructive hover:bg-destructive/10"
                          onClick={() => onDeleteCategory(category)}
                          aria-label={`Delete ${category.name} category`}
                        >
                          <Trash2 className="size-3.5" aria-hidden="true" />
                          Delete
                        </button>
                      </div>
                    </details>
                  </div>
                );
              })}
            </div>

            <Button
              type="button"
              variant="outline"
              size="lg"
              onClick={onAddCategory}
              className="mt-4 h-10 w-full"
            >
              <Plus data-icon="inline-start" />
              Add category
            </Button>
          </aside>

          <section className="flex min-h-[430px] flex-col">
            <CardHeader className="px-5 py-4">
              <CardTitle className="font-sans text-lg">
                {selectedCategory?.name ?? "Menu"}
              </CardTitle>
              <CardDescription>
                {visibleProducts.length}{" "}
                {visibleProducts.length === 1 ? "dish" : "dishes"}
              </CardDescription>
              <CardAction>
                <div className="flex items-center gap-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={onManageTemplates}
                  >
                    <Pencil data-icon="inline-start" />
                    Modifiers
                  </Button>
                  {visibleProducts.length > 0 ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={onAddDish}
                    data-menu-dish-trigger="true"
                  >
                    <Plus data-icon="inline-start" />
                    Add dish
                  </Button>
                  ) : null}
                </div>
              </CardAction>
            </CardHeader>
            <Separator />

            <div className="flex flex-1 flex-col gap-4 p-5">
              {visibleProducts.length === 0 ? (
                <div className="grid flex-1 place-items-center rounded-lg border border-dashed border-border bg-muted/30 p-8 text-center">
                  <div>
                    <p className="font-medium text-foreground">
                      No dishes in this category yet
                    </p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Add a dish to start building this category.
                    </p>
                    <Button
                      type="button"
                      size="lg"
                      onClick={onAddDish}
                      className="mt-4 h-10 min-w-[116px]"
                    >
                      <Plus data-icon="inline-start" />
                      Add dish
                    </Button>
                  </div>
                </div>
              ) : (
                <div
                  data-product-grid="compact-card"
                  className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3"
                >
                  {visibleProducts.map((product) => (
                    <article
                      key={product.id}
                      data-product-card="compact"
                      className="flex min-h-[112px] max-w-[260px] flex-col rounded-lg border border-border bg-card p-3 shadow-sm transition-colors hover:border-primary/35 hover:bg-muted/30"
                    >
                      <div className="flex min-w-0 items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h3 className="truncate text-sm font-semibold text-foreground">
                            {product.name}
                          </h3>
                          <p className="mt-0.5 line-clamp-1 text-xs leading-4 text-muted-foreground">
                            {product.description ?? "No description"}
                          </p>
                        </div>
                        <p className="shrink-0 text-base font-semibold leading-none text-foreground">
                          R&nbsp;{formatMoney(product.price)}
                        </p>
                      </div>

                      {product.tags.length > 0 ? (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {product.tags.slice(0, 3).map((tag) => (
                            <Badge
                              key={tag}
                              variant="secondary"
                              className="h-5 px-2 text-[11px]"
                            >
                              {tag}
                            </Badge>
                          ))}
                        </div>
                      ) : null}

                      <div className="mt-auto flex min-h-8 items-center justify-between gap-2 pt-3">
                        <div className="flex items-center gap-2">
                          <span
                            className={cn(
                              "size-2 rounded-full",
                              product.is_available
                                ? "bg-primary"
                                : "bg-muted-foreground",
                            )}
                            aria-hidden="true"
                          />
                          <Switch
                            size="sm"
                            checked={product.is_available}
                            onCheckedChange={(checked) =>
                              onToggleAvailability(product, checked)
                            }
                            aria-label={`${product.name} available`}
                          />
                          <span className="text-xs text-muted-foreground">
                            Available
                          </span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-xs"
                            onClick={() => onEditDish(product)}
                            aria-label={`Edit ${product.name}`}
                          >
                            <Pencil />
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-xs"
                            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                            onClick={() => onDeleteDish(product)}
                            aria-label={`Delete ${product.name}`}
                          >
                            <Trash2 />
                          </Button>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>
      </CardContent>
    </OnboardingCard>
  );
}

function LimitSelect({
  value,
  onChange,
  ariaLabel,
  compact = false,
  allowZero = true,
}: {
  value: string;
  onChange: (value: string) => void;
  ariaLabel: string;
  compact?: boolean;
  allowZero?: boolean;
}) {
  const options = allowZero
    ? SELECT_LIMIT_OPTIONS
    : SELECT_LIMIT_OPTIONS.filter((option) => option.value !== "0");
  return (
    <Select
      items={options}
      value={value}
      onValueChange={(next) => {
        if (next !== null) onChange(next);
      }}
    >
      <SelectTrigger
        className={compact ? "h-8 w-[58px]" : "h-9 w-[64px]"}
        aria-label={ariaLabel}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent alignItemWithTrigger={false}>
        <SelectGroup>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}

export function MenuDishDrawer({
  draft,
  categories,
  modifierGroups,
  errors,
  showErrors,
  isSaving,
  onChange,
  onClose,
  onSave,
  onUploadImage,
  onManageTemplates,
}: {
  draft: MenuDishDraft;
  categories: CategoryOut[];
  modifierGroups: ModifierGroupOut[];
  errors: MenuDishErrors;
  showErrors: boolean;
  isSaving: boolean;
  onChange: (draft: MenuDishDraft) => void;
  onClose: () => void;
  onSave: () => void;
  onUploadImage: (image: File) => Promise<string>;
  onManageTemplates: () => void;
}) {
  const [tagInput, setTagInput] = useState("");
  const [isUploadingImage, setIsUploadingImage] = useState(false);
  const [expandedOptionDetails, setExpandedOptionDetails] = useState<Set<string>>(
    () => new Set(),
  );
  const categoryOptions = categories.map((category) => ({
    value: category.id,
    label: category.name,
  }));
  const attachedGroupIds = new Set(
    draft.optionGroups
      .map((group) => group.modifierGroupId)
      .filter((id): id is string => Boolean(id)),
  );
  const availableModifierGroups = modifierGroups.filter(
    (group) => !attachedGroupIds.has(group.id),
  );
  const hasAvailableModifierGroups = availableModifierGroups.length > 0;
  const hasAttachedTemplates = draft.optionGroups.some(
    (group) => group.isTemplate && Boolean(group.modifierGroupId),
  );
  const modifierGroupHelpText =
    modifierGroups.length === 0
      ? "No templates yet. Add a dish option or create a reusable template."
      : hasAvailableModifierGroups
        ? "Select a saved template to attach it to this dish."
        : "All saved templates are already attached to this dish.";

  function patch(patch: Partial<MenuDishDraft>) {
    onChange({ ...draft, ...patch });
  }

  function updateGroup(clientId: string, patch: Partial<MenuOptionGroupDraft>) {
    onChange({
      ...draft,
      optionGroups: draft.optionGroups.map((group) =>
        group.clientId === clientId ? { ...group, ...patch } : group,
      ),
    });
  }

  function updateItem(
    groupId: string,
    itemId: string,
    patch: Partial<MenuOptionGroupDraft["items"][number]>,
  ) {
    onChange({
      ...draft,
      optionGroups: draft.optionGroups.map((group) =>
        group.clientId === groupId
          ? {
              ...group,
              items: group.items.map((item) =>
                item.clientId === itemId
                  ? { ...item, ...patch }
                  : patch.isDefault && group.selectType === "single"
                    ? { ...item, isDefault: false }
                    : item,
              ),
            }
          : group,
      ),
    });
  }

  function removeGroup(clientId: string) {
    patch({
      optionGroups: draft.optionGroups.filter(
        (group) => group.clientId !== clientId,
      ),
    });
  }

  function removeItem(groupId: string, itemId: string) {
    setExpandedOptionDetails((current) => {
      if (!current.has(itemId)) return current;
      const next = new Set(current);
      next.delete(itemId);
      return next;
    });
    onChange({
      ...draft,
      optionGroups: draft.optionGroups.map((group) =>
        group.clientId === groupId
          ? {
              ...group,
              items: group.items.filter((item) => item.clientId !== itemId),
            }
          : group,
      ),
    });
  }

  function expandOptionDetails(itemId: string) {
    setExpandedOptionDetails((current) => {
      if (current.has(itemId)) return current;
      const next = new Set(current);
      next.add(itemId);
      return next;
    });
  }

  function attachExistingGroup(groupId: string | null) {
    if (!groupId) return;
    const group = availableModifierGroups.find(
      (candidate) => candidate.id === groupId,
    );
    if (!group) return;
    patch({
      optionGroups: [
        ...draft.optionGroups,
        createOptionGroupDraftFromLibrary(group),
      ],
    });
  }

  function addTag() {
    const tag = tagInput.trim();
    if (!tag || draft.tags.includes(tag)) return;
    patch({ tags: [...draft.tags, tag] });
    setTagInput("");
  }

  async function handleUploadImage(file: File) {
    setIsUploadingImage(true);
    try {
      const imageUrl = await onUploadImage(file);
      patch({ imageUrl });
      toast.success("Image uploaded.");
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't upload the image. Please try again.",
      );
    } finally {
      setIsUploadingImage(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-foreground/35 p-3 backdrop-blur-[1px] sm:p-4">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="menu-dish-drawer-title"
        className="ml-auto flex h-full w-full max-w-[720px] flex-col overflow-hidden rounded-xl border border-border bg-white shadow-[0_20px_70px_-30px_rgba(15,23,42,0.45)]"
      >
        <header className="flex items-start justify-between gap-4 px-6 pt-5 pb-2">
          <div>
            <h2
              id="menu-dish-drawer-title"
              className="font-heading text-xl leading-tight font-semibold text-foreground"
            >
              {draft.id ? "Edit dish" : "Add dish"}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {draft.name || "Create a dish customers can order."}
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label="Close dish drawer"
          >
            <X />
          </Button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-4">
          <div className="grid gap-4 sm:grid-cols-[116px_1fr]">
            <Field className="max-w-[116px]">
              <FieldLabel htmlFor="dish-image-file">Image</FieldLabel>
              <label
                htmlFor="dish-image-file"
                className="group relative grid size-[116px] cursor-pointer place-items-center overflow-hidden rounded-lg border border-dashed border-border bg-muted/40 transition-colors hover:border-primary hover:bg-primary/5"
              >
                {draft.imageUrl ? (
                  // Merchant-provided image URLs are stored by the backend.
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={draft.imageUrl}
                    alt=""
                    className="size-full object-cover"
                  />
                ) : (
                  <span className="flex flex-col items-center gap-1.5 text-center text-muted-foreground">
                    <Upload className="size-6 stroke-[1.5] text-foreground" />
                    <span className="text-xs">Upload image</span>
                  </span>
                )}
                {isUploadingImage ? (
                  <span className="absolute inset-0 grid place-items-center bg-white/70">
                    <Spinner />
                  </span>
                ) : null}
              </label>
              <Input
                id="dish-image-file"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="sr-only"
                disabled={isUploadingImage}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void handleUploadImage(file);
                  event.target.value = "";
                }}
              />
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <ImageIcon className="size-3.5" />
                <span>URL fallback</span>
              </div>
              <Input
                id="dish-image-url"
                aria-label="Image URL"
                value={draft.imageUrl}
                onChange={(event) => patch({ imageUrl: event.target.value })}
                placeholder="https://..."
                className="h-9"
              />
            </Field>

            <FieldGroup className="grid gap-3 sm:grid-cols-2">
              <Field data-invalid={showErrors && Boolean(errors.name)}>
                <FieldLabel htmlFor="dish-name">Name *</FieldLabel>
                <Input
                  id="dish-name"
                  value={draft.name}
                  onChange={(event) => patch({ name: event.target.value })}
                  aria-invalid={showErrors && Boolean(errors.name)}
                  className="h-9"
                />
                <FieldError>{showErrors ? errors.name : undefined}</FieldError>
              </Field>

              <Field data-invalid={showErrors && Boolean(errors.price)}>
                <FieldLabel htmlFor="dish-price">Price *</FieldLabel>
                <InputGroup className="h-9">
                  <InputGroupAddon>
                    <InputGroupText>R</InputGroupText>
                  </InputGroupAddon>
                  <InputGroupInput
                    id="dish-price"
                    type="number"
                    min="0"
                    step="0.01"
                    value={draft.price}
                    onChange={(event) => patch({ price: event.target.value })}
                    aria-invalid={showErrors && Boolean(errors.price)}
                  />
                </InputGroup>
                <FieldError>{showErrors ? errors.price : undefined}</FieldError>
              </Field>

              <Field data-invalid={showErrors && Boolean(errors.categoryId)}>
                <FieldLabel>Category *</FieldLabel>
                <Select
                  items={categoryOptions}
                  value={draft.categoryId}
                  onValueChange={(value) => {
                    if (value !== null) patch({ categoryId: value });
                  }}
                >
                  <SelectTrigger
                    className="h-9 w-full"
                    aria-invalid={showErrors && Boolean(errors.categoryId)}
                  >
                    <SelectValue>
                      {(value: string) =>
                        categories.find((category) => category.id === value)?.name ??
                        "Choose category"
                      }
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent alignItemWithTrigger={false}>
                    <SelectGroup>
                      {categories.map((category) => (
                        <SelectItem key={category.id} value={category.id}>
                          {category.name}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
                <FieldError>
                  {showErrors ? errors.categoryId : undefined}
                </FieldError>
              </Field>

              <Field orientation="horizontal" className="items-center pt-5">
                <FieldTitle>Available</FieldTitle>
                <Switch
                  size="default"
                  checked={draft.isAvailable}
                  onCheckedChange={(checked) => patch({ isAvailable: checked })}
                  aria-label="Dish available"
                />
              </Field>

              <Field className="sm:col-span-2">
                <FieldLabel htmlFor="dish-description">Description</FieldLabel>
                <Textarea
                  id="dish-description"
                  value={draft.description}
                  onChange={(event) => patch({ description: event.target.value })}
                  rows={4}
                  className="min-h-24 resize-y"
                />
              </Field>

              <Field data-invalid={showErrors && Boolean(errors.prepMinutes)}>
                <FieldLabel htmlFor="dish-prep-time">Prep time</FieldLabel>
                <Input
                  id="dish-prep-time"
                  type="number"
                  min="0"
                  step="1"
                  value={draft.prepMinutes}
                  onChange={(event) => patch({ prepMinutes: event.target.value })}
                  aria-invalid={showErrors && Boolean(errors.prepMinutes)}
                  className="h-9"
                />
                <FieldDescription>Minutes</FieldDescription>
                <FieldError>
                  {showErrors ? errors.prepMinutes : undefined}
                </FieldError>
              </Field>

              <Field>
                <FieldLabel htmlFor="dish-tag">Tags</FieldLabel>
                <div className="flex gap-2">
                  <Input
                    id="dish-tag"
                    value={tagInput}
                    onChange={(event) => setTagInput(event.target.value)}
                    placeholder="bestseller"
                    className="h-9"
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        addTag();
                      }
                    }}
                  />
                  <Button type="button" variant="outline" onClick={addTag}>
                    <Plus data-icon="inline-start" />
                    Add tag
                  </Button>
                </div>
              </Field>
            </FieldGroup>
          </div>

          {draft.tags.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {draft.tags.map((tag) => (
                <Badge key={tag} variant="secondary" className="gap-1">
                  {tag}
                  <button
                    type="button"
                    onClick={() =>
                      patch({ tags: draft.tags.filter((item) => item !== tag) })
                    }
                    aria-label={`Remove ${tag} tag`}
                  >
                    <X className="size-3" />
                  </button>
                </Badge>
              ))}
            </div>
          ) : null}

          <Separator className="my-4" />

          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                Options &amp; modifiers
              </h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Let customers choose sizes, add-ons, and customizations.
              </p>
            </div>
            <Button type="button" variant="ghost" size="sm" onClick={onManageTemplates}>
              <Pencil data-icon="inline-start" />
              Manage templates
            </Button>
          </div>

          {hasAvailableModifierGroups ? (
            <div className="mt-3">
              <Field>
                <FieldLabel>
                  {hasAttachedTemplates ? "Add another template" : "Add template"}
                </FieldLabel>
                <Select value={null} onValueChange={attachExistingGroup}>
                  <SelectTrigger className="h-9 w-full">
                    <SelectValue
                      placeholder={
                        hasAttachedTemplates
                          ? "Choose another template"
                          : "Choose from your template library"
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {availableModifierGroups.map((group) => (
                        <SelectItem key={group.id} value={group.id}>
                          {group.name} ({group.display_name})
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
                <FieldDescription>{modifierGroupHelpText}</FieldDescription>
              </Field>
            </div>
          ) : (
            <p className="mt-3 text-xs text-muted-foreground">
              {modifierGroupHelpText}
            </p>
          )}

          <div className="mt-3 flex flex-col gap-3">
            {draft.optionGroups.map((group) => {
              const groupError = errors.optionGroups?.[group.clientId];
              const definitionLocked = !group.isDefinitionEditable;
              return (
                <div
                  key={group.clientId}
                  data-compact-template={definitionLocked || undefined}
                  data-compact-dish-only={!definitionLocked || undefined}
                  className={cn(
                    "rounded-lg border border-border bg-background",
                    definitionLocked ? "p-2" : "p-2",
                  )}
                >
                  <div className={cn(
                    "flex flex-wrap justify-between gap-2",
                    definitionLocked ? "mb-1.5 items-start" : "mb-1.5 items-center",
                  )}>
                    <div className="flex min-w-0 items-center gap-2">
                      <Badge variant="secondary">
                        {group.isTemplate ? "Template" : "Dish only"}
                      </Badge>
                      {definitionLocked ? (
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-foreground">
                            {group.name}
                          </p>
                          <p className="truncate text-xs text-muted-foreground">
                            {group.displayName} - {group.selectType === "single" ? "Single choice" : "Multiple choice"}
                          </p>
                        </div>
                      ) : null}
                    </div>
                    <div className="ml-auto flex items-start gap-1">
                      {definitionLocked ? (
                        <div
                          data-compact-template-rules="true"
                          className="flex items-end gap-2"
                        >
                          <Field className="gap-1">
                            <FieldLabel className="text-xs">Required</FieldLabel>
                            <div className="flex h-8 items-center">
                              <Switch
                                checked={group.isRequired}
                                onCheckedChange={(checked) =>
                                  updateGroup(group.clientId, {
                                    isRequired: checked,
                                    minSelect: checked ? "1" : "0",
                                  })
                                }
                                aria-label={`${group.name || "Option group"} required`}
                              />
                            </div>
                          </Field>
                          {group.selectType === "multi" ? (
                            <Field className="gap-1">
                              <FieldLabel className="text-xs">Maximum choices</FieldLabel>
                              <LimitSelect
                                compact
                                allowZero={false}
                                value={group.maxSelect}
                                onChange={(value) =>
                                  updateGroup(group.clientId, { maxSelect: value })
                                }
                                ariaLabel={`${group.name || "Option group"} maximum choices`}
                              />
                            </Field>
                          ) : null}
                        </div>
                      ) : null}
                      {definitionLocked ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => removeGroup(group.clientId)}
                          aria-label={`Detach ${group.name || "option"} group`}
                        >
                          <Unlink />
                        </Button>
                      ) : (
                        <details className="relative">
                          <summary
                            className="flex size-8 cursor-pointer list-none items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground [&::-webkit-details-marker]:hidden"
                            aria-label={`Open ${group.name || "option"} group actions`}
                          >
                            <MoreHorizontal
                              className="size-4"
                              aria-hidden="true"
                            />
                          </summary>
                          <div className="absolute top-8 right-0 z-20 grid w-44 gap-1 rounded-lg border border-border bg-popover p-1 text-sm text-popover-foreground shadow-lg">
                            <button
                              type="button"
                              className="flex h-8 items-center gap-2 rounded-md px-2 text-left hover:bg-muted"
                              onClick={() =>
                                updateGroup(group.clientId, { isTemplate: true })
                              }
                            >
                              <FolderOpen
                                className="size-3.5"
                                aria-hidden="true"
                              />
                              Make reusable
                            </button>
                            <button
                              type="button"
                              className="flex h-8 items-center gap-2 rounded-md px-2 text-left text-destructive hover:bg-destructive/10"
                              onClick={() => removeGroup(group.clientId)}
                              aria-label={`Delete ${group.name || "option"} group`}
                            >
                              <Trash2
                                className="size-3.5"
                                aria-hidden="true"
                              />
                              Delete group
                            </button>
                          </div>
                        </details>
                      )}
                    </div>
                  </div>
                  {!definitionLocked ? (
                    <div className="grid gap-2 sm:grid-cols-2">
                      <Field data-invalid={showErrors && Boolean(groupError)}>
                        <FieldLabel>Internal name</FieldLabel>
                        <Input
                          value={group.name}
                          onChange={(event) =>
                            updateGroup(group.clientId, {
                              name: event.target.value,
                            })
                          }
                          aria-invalid={showErrors && Boolean(groupError)}
                          className="h-9"
                        />
                      </Field>

                      <Field data-invalid={showErrors && Boolean(groupError)}>
                        <FieldLabel>Customer label</FieldLabel>
                        <Input
                          value={group.displayName}
                          onChange={(event) =>
                            updateGroup(group.clientId, {
                              displayName: event.target.value,
                            })
                          }
                          aria-invalid={showErrors && Boolean(groupError)}
                          className="h-9"
                        />
                      </Field>
                    </div>
                  ) : null}

                  {!definitionLocked ? (
                  <div
                    className={cn(
                      "mt-2 grid gap-2 sm:items-end",
                      group.selectType === "multi"
                        ? "sm:grid-cols-[minmax(160px,1fr)_80px_128px]"
                        : "sm:grid-cols-[minmax(160px,1fr)_80px]",
                    )}
                  >

                      <Field>
                        <FieldLabel>Type</FieldLabel>
                        <ToggleGroup
                          value={[group.selectType]}
                          onValueChange={(value) => {
                            if (value[0]) {
                              const selectType = value[0] as "single" | "multi";
                              updateGroup(group.clientId, {
                                selectType,
                                minSelect: group.isRequired ? "1" : "0",
                                maxSelect:
                                  selectType === "single"
                                    ? "1"
                                    : String(group.items.filter((item) => item.isEnabled).length),
                              });
                            }
                          }}
                          variant="outline"
                          spacing={2}
                          aria-label={`${group.name || "Option group"} type`}
                        >
                          <ToggleGroupItem value="single" className="h-9 px-3">
                            Single
                          </ToggleGroupItem>
                          <ToggleGroupItem value="multi" className="h-9 px-3">
                            Multi
                          </ToggleGroupItem>
                        </ToggleGroup>
                      </Field>

                    <Field>
                      <FieldLabel>Required</FieldLabel>
                      <div className="flex h-9 items-center">
                        <Switch
                          size="lg"
                          checked={group.isRequired}
                          onCheckedChange={(checked) =>
                            updateGroup(group.clientId, {
                              isRequired: checked,
                              minSelect: checked ? "1" : "0",
                            })
                          }
                          aria-label={`${group.name || "Option group"} required`}
                        />
                      </div>
                    </Field>

                    {group.selectType === "multi" ? (
                      <Field>
                        <FieldLabel>Maximum choices</FieldLabel>
                        <LimitSelect
                          allowZero={false}
                          value={group.maxSelect}
                          onChange={(value) =>
                            updateGroup(group.clientId, { maxSelect: value })
                          }
                          ariaLabel={`${group.name || "Option group"} maximum choices`}
                        />
                      </Field>
                    ) : null}

                  </div>
                  ) : null}

                  {showErrors && groupError ? (
                    <FieldError className="mt-2">{groupError}</FieldError>
                  ) : null}

                  <div
                    data-compact-template-options={definitionLocked || undefined}
                    className={cn(
                      "overflow-x-auto pb-1",
                      definitionLocked ? "mt-1.5" : "mt-3",
                    )}
                  >
                    <div className={definitionLocked ? "min-w-[480px]" : "min-w-[560px]"}>
                    <div
                      className={cn(
                        "grid gap-2 px-1 text-xs text-muted-foreground",
                        definitionLocked
                          ? "grid-cols-[64px_minmax(0,1fr)_112px_58px]"
                          : "grid-cols-[64px_minmax(0,1fr)_112px_58px_32px]",
                      )}
                    >
                      <span>Enabled</span>
                      <span>Item name</span>
                      <span>Price delta</span>
                      <span>Default</span>
                      {!definitionLocked ? <span>Action</span> : null}
                    </div>
                    <div className={cn(
                      "flex flex-col",
                      definitionLocked ? "mt-1 gap-1" : "mt-2 gap-2",
                    )}>
                      {group.items.map((item) => (
                        <div
                          key={item.clientId}
                          className={cn(
                            "grid gap-2",
                            definitionLocked
                              ? "grid-cols-[64px_minmax(0,1fr)_112px_58px] items-center"
                              : "grid-cols-[64px_minmax(0,1fr)_112px_58px_32px] items-start",
                          )}
                        >
                          <div className="flex justify-center">
                            <Checkbox
                              checked={item.isEnabled}
                              disabled={!definitionLocked}
                              onCheckedChange={(checked) =>
                                updateItem(group.clientId, item.clientId, {
                                  isEnabled: checked,
                                  isDefault: checked ? item.isDefault : false,
                                })
                              }
                              aria-label={`Enable ${item.name || "option"}`}
                            />
                          </div>
                          {definitionLocked ? (
                            <div className="min-w-0 px-2.5 py-1">
                              <p className="truncate text-sm font-medium leading-tight text-foreground">
                                {item.name}
                              </p>
                              {item.description ? (
                                <p className="mt-0.5 text-xs leading-snug text-muted-foreground">
                                  {item.description}
                                </p>
                              ) : null}
                            </div>
                          ) : (
                            <div className="flex min-w-0 flex-col gap-1.5">
                              <Input
                                value={item.name}
                                onChange={(event) =>
                                  updateItem(group.clientId, item.clientId, {
                                    name: event.target.value,
                                  })
                                }
                                aria-label={`${group.name} item name`}
                                className="h-9"
                              />
                              {item.description.trim().length > 0 ||
                              expandedOptionDetails.has(item.clientId) ? (
                                <Textarea
                                  value={item.description}
                                  onChange={(event) =>
                                    updateItem(group.clientId, item.clientId, {
                                      description: event.target.value,
                                    })
                                  }
                                  aria-label={`${item.name || "Option"} customer details`}
                                  placeholder="Customer details, e.g. 500 ml or serves 2"
                                  rows={1}
                                  maxLength={500}
                                  className="min-h-9 resize-y py-1.5"
                                />
                              ) : (
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  className="h-7 w-fit px-2 text-xs text-muted-foreground"
                                  onClick={() =>
                                    expandOptionDetails(item.clientId)
                                  }
                                >
                                  <Plus data-icon="inline-start" />
                                  Add details
                                </Button>
                              )}
                            </div>
                          )}
                          <InputGroup className={definitionLocked ? "h-8" : "h-9"}>
                            <InputGroupAddon>
                              <InputGroupText>+ R</InputGroupText>
                            </InputGroupAddon>
                            <InputGroupInput
                              type="number"
                              min="0"
                              step="0.01"
                              value={item.priceDelta}
                              onChange={(event) =>
                                updateItem(group.clientId, item.clientId, {
                                  priceDelta: event.target.value,
                                  priceDeltaOverride: definitionLocked
                                    ? event.target.value
                                    : null,
                                })
                              }
                              aria-label={`${item.name || "Option"} price delta`}
                              disabled={!item.isEnabled}
                            />
                          </InputGroup>
                          <Switch
                            size={definitionLocked ? "default" : "lg"}
                            checked={item.isDefault}
                            onCheckedChange={(checked) =>
                              updateItem(group.clientId, item.clientId, {
                                isDefault: checked,
                              })
                            }
                            aria-label={`${item.name || "Option"} default`}
                            disabled={!item.isEnabled}
                          />
                          {!definitionLocked ? (
                            <Button
                              type="button"
                              variant="destructive"
                              size="icon-sm"
                              onClick={() => removeItem(group.clientId, item.clientId)}
                              aria-label={`Delete ${item.name || "option item"}`}
                              disabled={group.items.length === 1}
                            >
                              <Trash2 />
                            </Button>
                          ) : null}
                        </div>
                      ))}
                    </div>
                    {!definitionLocked ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="lg"
                        onClick={() =>
                          updateGroup(group.clientId, {
                            items: [...group.items, createOptionItemDraft()],
                          })
                        }
                        className="mt-3 h-8 w-full"
                      >
                        <Plus data-icon="inline-start" />
                        Add item
                      </Button>
                    ) : null}
                    </div>
                  </div>
                </div>
              );
            })}

            <Button
              type="button"
              variant="outline"
              size="lg"
              onClick={() =>
                patch({
                  optionGroups: [
                    ...draft.optionGroups,
                    createOptionGroupDraft(),
                  ],
                })
              }
              className="h-8 border-dashed"
            >
              <Plus data-icon="inline-start" />
              Add dish option
            </Button>
            <p className="text-xs text-muted-foreground">
              A required group with one enabled option is selected automatically.
            </p>
          </div>
        </div>

        <footer className="mt-auto border-t border-border bg-white px-6 py-4">
          <div className="flex items-center justify-between gap-4">
            <Button
              type="button"
              variant="outline"
              size="lg"
              onClick={onClose}
              className="h-9 min-w-[104px]"
            >
              Cancel
            </Button>
            <Button
              type="button"
              size="lg"
              onClick={onSave}
              disabled={isSaving}
              className="h-9 min-w-[124px]"
            >
              {isSaving ? <Spinner data-icon="inline-start" /> : null}
              Save dish
            </Button>
          </div>
        </footer>
      </section>
    </div>
  );
}

export function CategoryNameDialog({
  title,
  description,
  submitLabel,
  value,
  isSaving,
  onChange,
  onClose,
  onSubmit,
}: {
  title: string;
  description: string;
  submitLabel: string;
  value: string;
  isSaving: boolean;
  onChange: (value: string) => void;
  onClose: () => void;
  onSubmit: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-foreground/35 px-4 backdrop-blur-[1px]">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="category-dialog-title"
        className="w-full max-w-[420px] rounded-xl border border-border bg-white p-5 shadow-[0_20px_70px_-30px_rgba(15,23,42,0.45)]"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2
              id="category-dialog-title"
              className="font-heading text-xl leading-tight font-semibold text-foreground"
            >
              {title}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {description}
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label="Close category dialog"
          >
            <X />
          </Button>
        </div>

        <form
          className="mt-5"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit();
          }}
        >
          <Field>
            <FieldLabel htmlFor="category-name">Category name</FieldLabel>
            <Input
              id="category-name"
              value={value}
              onChange={(event) => onChange(event.target.value)}
              placeholder="e.g. Mains"
              className="h-10"
              autoFocus
            />
          </Field>
          <div className="mt-5 flex justify-end gap-3">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={isSaving}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSaving || !value.trim()}>
              {isSaving ? <Spinner data-icon="inline-start" /> : null}
              {submitLabel}
            </Button>
          </div>
        </form>
      </section>
    </div>
  );
}

export function MenuBuilder({ initialState }: MenuBuilderProps) {
  const router = useRouter();
  const [accessToken, setAccessToken] = useState(initialState?.accessToken ?? "");
  const [businessId, setBusinessId] = useState(initialState?.businessId ?? "");
  const [categories, setCategories] = useState<CategoryOut[]>(
    initialState?.categories ?? [],
  );
  const [products, setProducts] = useState<ProductOut[]>(
    initialState?.products ?? [],
  );
  const [modifierGroups, setModifierGroups] = useState<ModifierGroupOut[]>(
    initialState?.modifierGroups ?? [],
  );
  const [templateManagerOpen, setTemplateManagerOpen] = useState(
    initialState?.templateManagerOpen ?? false,
  );
  const [isSavingTemplate, setIsSavingTemplate] = useState(false);
  const [selectedCategoryId, setSelectedCategoryId] = useState(
    initialState?.categories[0]?.id ?? "",
  );
  const [draft, setDraft] = useState<MenuDishDraft | null>(() => {
    const openProduct = initialState?.products.find(
      (product) => product.id === initialState.openProductId,
    );
    if (openProduct) {
      return createDishDraftFromProduct(
        openProduct,
        initialState?.modifierGroups ?? [],
      );
    }
    if (initialState?.openNewDish) {
      return createEmptyDishDraft(initialState.categories[0]?.id ?? "");
    }
    return null;
  });
  const [showErrors, setShowErrors] = useState(false);
  const [isLoading, setIsLoading] = useState(!initialState);
  const [isSaving, setIsSaving] = useState(false);
  const [isSeeding, setIsSeeding] = useState(false);
  const [categoryDialogOpen, setCategoryDialogOpen] = useState(
    Boolean(initialState?.categoryDialogOpen),
  );
  const [categoryName, setCategoryName] = useState("");
  const [editingCategory, setEditingCategory] = useState<CategoryOut | null>(null);
  const [isCreatingCategory, setIsCreatingCategory] = useState(false);

  const dishErrors = draft ? validateMenuDishDraft(draft) : {};
  const hasMenuStructure = categories.length > 0 || products.length > 0;

  const selectedCategoryForNewDish = useMemo(
    () => selectedCategoryId || categories[0]?.id || "",
    [categories, selectedCategoryId],
  );

  useEffect(() => {
    if (initialState) return;
    const token = accessTokenFromStorage();
    if (!token) {
      toast.error("Please sign in to continue.");
      router.replace("/login");
      return;
    }

    let active = true;
    void listBusinesses(token)
      .then(async (businesses) => {
        const business = pickBusinessForOwner(businesses);
        if (!business) {
          throw new ApiError("Complete your business profile first.", 400);
        }
        saveSelectedBusinessId(business.id);
        const [loadedCategories, loadedProducts, loadedModifierGroups] =
          await Promise.all([
          listCategories({ accessToken: token, businessId: business.id }),
          listProducts({ accessToken: token, businessId: business.id }),
            listModifierGroups({ accessToken: token, businessId: business.id }),
          ]);
        if (!active) return;
        setAccessToken(token);
        setBusinessId(business.id);
        setCategories(loadedCategories);
        setProducts(loadedProducts);
        setModifierGroups(loadedModifierGroups);
        setSelectedCategoryId(
          loadedProducts[0]?.category_id ?? loadedCategories[0]?.id ?? "",
        );
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          toast.error("Your session has expired. Please sign in again.");
          router.replace("/login");
          return;
        }
        toast.error(
          error instanceof ApiError
            ? error.message
            : "We couldn't load your menu.",
        );
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [initialState, router]);

  function handleSaveExit() {
    saveOnboardingResumePath("/onboarding/menu");
    clearTokens();
    router.replace("/login");
  }

  function openNewDish() {
    if (categories.length === 0) {
      toast.info("Add a category before creating dishes.");
      return;
    }
    setShowErrors(false);
    setDraft(createEmptyDishDraft(selectedCategoryForNewDish));
  }

  function openExistingDish(product: ProductOut) {
    setShowErrors(false);
    setDraft(createDishDraftFromProduct(product, modifierGroups));
  }

  function handleAddCategory() {
    if (!accessToken || !businessId) {
      toast.error("Menu is still loading. Try again in a moment.");
      return;
    }
    setEditingCategory(null);
    setCategoryName("");
    setCategoryDialogOpen(true);
  }

  function handleEditCategory(category: CategoryOut) {
    if (!accessToken || !businessId) {
      toast.error("Menu is still loading. Try again in a moment.");
      return;
    }
    setEditingCategory(category);
    setCategoryName(category.name);
    setCategoryDialogOpen(true);
  }

  async function handleSaveCategory() {
    const name = categoryName.trim();
    if (!name) return;
    if (!accessToken || !businessId) {
      toast.error("Menu is still loading. Try again in a moment.");
      return;
    }
    setIsCreatingCategory(true);
    try {
      if (editingCategory) {
        const saved = await updateCategoryName({
          accessToken,
          businessId,
          categoryId: editingCategory.id,
          name,
        });
        setCategories((current) =>
          current.map((category) => (category.id === saved.id ? saved : category)),
        );
        toast.success("Category updated.");
      } else {
        const created = await createCategory({
          accessToken,
          businessId,
          name,
          sortOrder: categories.length,
        });
        setCategories((current) => [...current, created]);
        setSelectedCategoryId(created.id);
        toast.success("Category added.");
      }
      setCategoryName("");
      setEditingCategory(null);
      setCategoryDialogOpen(false);
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't save category. Please try again.",
      );
    } finally {
      setIsCreatingCategory(false);
    }
  }

  async function handleDeleteCategory(category: CategoryOut) {
    if (!accessToken || !businessId) return;
    if (!window.confirm(`Delete ${category.name}? Dishes will stay in your menu without this category.`)) {
      return;
    }

    const previousCategories = categories;
    const previousProducts = products;
    const previousSelectedCategoryId = selectedCategoryId;
    const remainingCategories = categories.filter((item) => item.id !== category.id);

    setCategories(remainingCategories);
    setProducts((current) =>
      current.map((product) =>
        product.category_id === category.id
          ? { ...product, category_id: null }
          : product,
      ),
    );
    if (selectedCategoryId === category.id) {
      setSelectedCategoryId(remainingCategories[0]?.id ?? "");
    }

    try {
      await deleteCategory({
        accessToken,
        businessId,
        categoryId: category.id,
      });
      toast.success("Category deleted.");
    } catch (error) {
      setCategories(previousCategories);
      setProducts(previousProducts);
      setSelectedCategoryId(previousSelectedCategoryId);
      toast.error(
        error instanceof ApiError ? error.message : "Couldn't delete the category.",
      );
    }
  }

  async function handleToggleCategoryActive(
    category: CategoryOut,
    isActive: boolean,
  ) {
    if (!accessToken || !businessId) return;
    setCategories((current) =>
      current.map((item) =>
        item.id === category.id ? { ...item, is_active: isActive } : item,
      ),
    );
    try {
      const saved = await updateCategoryActive({
        accessToken,
        businessId,
        categoryId: category.id,
        isActive,
      });
      setCategories((current) =>
        current.map((item) => (item.id === saved.id ? saved : item)),
      );
    } catch (error) {
      setCategories((current) =>
        current.map((item) =>
          item.id === category.id
            ? { ...item, is_active: category.is_active }
            : item,
        ),
      );
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't update the category.",
      );
    }
  }

  async function handleUploadMenuItemImage(image: File) {
    if (!accessToken || !businessId) {
      throw new ApiError("Menu is still loading. Try again in a moment.", 0);
    }
    return uploadMenuItemImage({
      accessToken,
      businessId,
      image,
    });
  }

  async function refreshModifierLibrary() {
    try {
      setModifierGroups(
        await listModifierGroups({ accessToken, businessId }),
      );
    } catch {
      toast.warning("Saved successfully, but the modifier library could not refresh.");
    }
  }

  async function handleSaveTemplate(group: MenuOptionGroupDraft) {
    if (!accessToken || !businessId) return;
    setIsSavingTemplate(true);
    try {
      const saved = group.modifierGroupId
        ? await updateModifierGroup({
            accessToken,
            businessId,
            groupId: group.modifierGroupId,
            group,
          })
        : await createModifierGroup({ accessToken, businessId, group });
      setModifierGroups((current) => {
        const exists = current.some((item) => item.id === saved.id);
        return exists
          ? current.map((item) => (item.id === saved.id ? saved : item))
          : [...current, saved].sort((a, b) => a.name.localeCompare(b.name));
      });
      setDraft((current) =>
        current
          ? {
              ...current,
              optionGroups: current.optionGroups.map((assignment) => {
                if (assignment.modifierGroupId !== saved.id) return assignment;
                const currentItems = new Map(
                  assignment.items.map((item) => [item.optionId, item]),
                );
                return {
                  ...assignment,
                  name: saved.name,
                  displayName: saved.display_name,
                  selectType: saved.select_type,
                  isTemplate: true,
                  isDefinitionEditable: false,
                  items: saved.items.map((item) => {
                    const currentItem = currentItems.get(item.id);
                    return createOptionItemDraft({
                      clientId: item.id,
                      optionId: item.id,
                      name: item.name,
                      description: item.description ?? "",
                      priceDelta:
                        currentItem?.priceDeltaOverride ?? String(item.price_delta),
                      priceDeltaOverride:
                        currentItem?.priceDeltaOverride ?? null,
                      isDefault: currentItem?.isDefault ?? false,
                      isEnabled: currentItem?.isEnabled ?? false,
                    });
                  }),
                };
              }),
            }
          : current,
      );
      setTemplateManagerOpen(false);
      toast.success(group.modifierGroupId ? "Template updated." : "Template created.");
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : "Couldn't save the template.",
      );
    } finally {
      setIsSavingTemplate(false);
    }
  }

  async function handleDeleteTemplate(group: ModifierGroupOut) {
    if (!accessToken || !businessId) return;
    if (!window.confirm(`Delete ${group.name}?`)) return;
    setIsSavingTemplate(true);
    try {
      await deleteModifierGroup({
        accessToken,
        businessId,
        groupId: group.id,
      });
      setModifierGroups((current) => current.filter((item) => item.id !== group.id));
      setTemplateManagerOpen(false);
      toast.success("Template deleted.");
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : "Couldn't delete the template.",
      );
    } finally {
      setIsSavingTemplate(false);
    }
  }

  async function handleSeedSampleMenu() {
    if (!accessToken || !businessId) {
      toast.error("Menu is still loading. Try again in a moment.");
      return;
    }
    setIsSeeding(true);
    try {
      const seeded = await seedSampleMenu({
        accessToken,
        businessId,
        categories,
        products,
      });
      setCategories(seeded.categories);
      setProducts(seeded.products);
      await refreshModifierLibrary();
      const mains = seeded.categories.find((category) => category.name === "Mains");
      setSelectedCategoryId(mains?.id ?? seeded.categories[0]?.id ?? "");
      const burger = seeded.products.find(
        (product) => product.name === "Classic Beef Burger",
      );
      if (burger) setDraft(createDishDraftFromProduct(burger, modifierGroups));
      toast.success("Sample menu added.");
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't seed the sample menu. Please try again.",
      );
    } finally {
      setIsSeeding(false);
    }
  }

  async function handleSaveDish() {
    if (!draft) return;
    setShowErrors(true);
    if (hasMenuDishErrors(dishErrors)) {
      toast.error("Check your dish details before saving.");
      return;
    }
    if (!accessToken || !businessId) {
      toast.error("Menu is still loading. Try again in a moment.");
      return;
    }

    setIsSaving(true);
    try {
      const saved = await saveMenuDish({
        accessToken,
        businessId,
        draft,
        categories,
      });
      setProducts((current) => {
        const exists = current.some((product) => product.id === saved.id);
        return exists
          ? current.map((product) => (product.id === saved.id ? saved : product))
          : [...current, saved];
      });
      await refreshModifierLibrary();
      setSelectedCategoryId(saved.category_id ?? selectedCategoryId);
      setDraft(null);
      toast.success("Dish saved.");
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't save the dish. Please try again.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  async function handleToggleAvailability(
    product: ProductOut,
    isAvailable: boolean,
  ) {
    if (!accessToken || !businessId) return;
    setProducts((current) =>
      current.map((item) =>
        item.id === product.id ? { ...item, is_available: isAvailable } : item,
      ),
    );
    try {
      const saved = await updateProductAvailability({
        accessToken,
        businessId,
        productId: product.id,
        isAvailable,
      });
      setProducts((current) =>
        current.map((item) => (item.id === saved.id ? saved : item)),
      );
    } catch (error) {
      setProducts((current) =>
        current.map((item) =>
          item.id === product.id
            ? { ...item, is_available: product.is_available }
            : item,
        ),
      );
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't update availability.",
      );
    }
  }

  async function handleDeleteDish(product: ProductOut) {
    if (!accessToken || !businessId) return;
    if (!window.confirm(`Delete ${product.name}?`)) return;
    try {
      await deleteProduct({
        accessToken,
        businessId,
        productId: product.id,
      });
      setProducts((current) => current.filter((item) => item.id !== product.id));
      toast.success("Dish deleted.");
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't delete the dish.",
      );
    }
  }

  function handleContinue() {
    if (products.length === 0) {
      toast.error("Add at least one dish before continuing.");
      return;
    }
    saveOnboardingResumePath("/onboarding/assistant");
    router.push("/onboarding/assistant");
  }

  return (
    <>
      <OnboardingShell
        currentStep={5}
        contentClassName="max-w-[1120px]"
        mainClassName="items-start py-4 sm:px-8"
        footerClassName="w-full justify-between gap-3"
        onSaveExit={handleSaveExit}
        footer={
          <>
            <Button
              type="button"
              variant="outline"
              size="lg"
              onClick={() => router.push("/onboarding/fulfillment")}
              className="h-10 min-w-[104px]"
            >
              <ArrowLeft data-icon="inline-start" />
              Back
            </Button>
            <Button
              type="button"
              variant="link"
              size="default"
              onClick={handleSaveExit}
            >
              Skip for now
            </Button>
            <Button
              type="button"
              size="lg"
              disabled={isLoading || products.length === 0}
              onClick={handleContinue}
              className="h-10 min-w-[136px]"
            >
              Continue
              <ArrowRight data-icon="inline-end" />
            </Button>
          </>
        }
      >
        <OnboardingStepHeader
          stepLabel="Step 5 of 8"
          title="Build your menu"
          subtitle="Add categories and dishes customers can order."
        />

        {isLoading ? (
          <OnboardingCard className="mt-2">
            <CardContent
              data-menu-loading={true}
              className="grid min-h-[390px] place-items-center"
            >
              <Spinner />
            </CardContent>
          </OnboardingCard>
        ) : hasMenuStructure ? (
          <MenuEditorPanel
            categories={categories}
            products={products}
            selectedCategoryId={selectedCategoryId}
            onSelectCategory={setSelectedCategoryId}
            onAddCategory={handleAddCategory}
            onAddDish={openNewDish}
            onManageTemplates={() => setTemplateManagerOpen(true)}
            onEditDish={openExistingDish}
            onEditCategory={handleEditCategory}
            onDeleteCategory={(category) => void handleDeleteCategory(category)}
            onToggleCategoryActive={(category, checked) =>
              void handleToggleCategoryActive(category, checked)
            }
            onToggleAvailability={(product, checked) =>
              void handleToggleAvailability(product, checked)
            }
            onDeleteDish={(product) => void handleDeleteDish(product)}
          />
        ) : (
          <EmptyMenuPanel
            onAddCategory={handleAddCategory}
            onAddDish={openNewDish}
            onSeed={handleSeedSampleMenu}
            isSeeding={isSeeding}
          />
        )}
      </OnboardingShell>

      {draft ? (
        <MenuDishDrawer
          draft={draft}
          categories={categories}
          modifierGroups={modifierGroups}
          errors={dishErrors}
          showErrors={showErrors}
          isSaving={isSaving}
          onChange={setDraft}
          onClose={() => setDraft(null)}
          onSave={() => void handleSaveDish()}
          onUploadImage={handleUploadMenuItemImage}
          onManageTemplates={() => setTemplateManagerOpen(true)}
        />
      ) : null}
      <ModifierTemplateDialog
        open={templateManagerOpen}
        groups={modifierGroups}
        isSaving={isSavingTemplate}
        onOpenChange={setTemplateManagerOpen}
        onSave={(group) => void handleSaveTemplate(group)}
        onDelete={(group) => void handleDeleteTemplate(group)}
      />
      {categoryDialogOpen ? (
        <CategoryNameDialog
          title={editingCategory ? "Edit category" : "Add category"}
          description={
            editingCategory
              ? "Rename this menu section."
              : "Create a menu section like Mains, Drinks, or Desserts."
          }
          submitLabel={editingCategory ? "Save category" : "Create category"}
          value={categoryName}
          isSaving={isCreatingCategory}
          onChange={setCategoryName}
          onClose={() => {
            if (isCreatingCategory) return;
            setCategoryName("");
            setEditingCategory(null);
            setCategoryDialogOpen(false);
          }}
          onSubmit={() => void handleSaveCategory()}
        />
      ) : null}
    </>
  );
}

export function MenuEmptyState() {
  return <MenuBuilder />;
}
