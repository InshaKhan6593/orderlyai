"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ImageIcon,
  Layers,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { DashboardShell } from "@/components/dashboard/dashboard-shell";
import {
  CategoryNameDialog,
  MenuDishDrawer,
} from "@/components/onboarding/menu-empty-state";
import { ModifierTemplateDialog } from "@/components/onboarding/modifier-template-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { ApiError } from "@/lib/auth";
import {
  pickBusinessForOwner,
  saveSelectedBusinessId,
} from "@/lib/business-selection";
import { listBusinesses, type Business } from "@/lib/business-profile";
import {
  formatMoney,
  listDashboardOrders,
  toggleAcceptingOrders,
  type DashboardOrder,
} from "@/lib/dashboard";
import {
  createCategory,
  createDishDraftFromProduct,
  createEmptyDishDraft,
  createModifierGroup,
  deleteCategory,
  deleteModifierGroup,
  deleteProduct,
  hasMenuDishErrors,
  listCategories,
  listModifierGroups,
  listProducts,
  saveMenuDish,
  updateCategoryActive,
  updateCategoryName,
  updateModifierGroup,
  updateProductAvailability,
  uploadMenuItemImage,
  validateMenuDishDraft,
  type CategoryOut,
  type MenuDishDraft,
  type MenuOptionGroupDraft,
  type ModifierGroupOut,
  type ProductOut,
} from "@/lib/menu";
import { cn } from "@/lib/utils";

function accessTokenFromStorage(): string | null {
  return (
    window.localStorage.getItem("orderly.access_token") ??
    window.sessionStorage.getItem("orderly.access_token")
  );
}

function productCount(products: ProductOut[], categoryId: string): number {
  return products.filter((product) => product.category_id === categoryId).length;
}

function ProductImage({ product }: { product: ProductOut }) {
  if (product.image_url?.startsWith("http")) {
    return (
      // Product image domains are tenant-provided and not configured for next/image yet.
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={product.image_url}
        alt=""
        className="h-36 w-full object-cover"
      />
    );
  }
  return (
    <span className="flex h-36 w-full items-center justify-center bg-muted/60 text-muted-foreground">
      <ImageIcon className="size-7" aria-hidden="true" />
    </span>
  );
}

function ProductCard({
  product,
  selected,
  onEdit,
  onToggleAvailability,
  onDelete,
}: {
  product: ProductOut;
  selected: boolean;
  onEdit: () => void;
  onToggleAvailability: (checked: boolean) => void;
  onDelete: () => void;
}) {
  return (
    <article
      className={cn(
        "group flex flex-col overflow-hidden rounded-xl border bg-card shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md",
        selected ? "border-primary ring-1 ring-primary/20" : "border-border",
      )}
    >
      <button
        type="button"
        onClick={onEdit}
        className="relative block text-left"
        aria-label={`Edit ${product.name}`}
      >
        <ProductImage product={product} />
        {!product.is_available ? (
          <span className="absolute top-3 left-3 rounded-full bg-foreground/80 px-2.5 py-1 text-xs font-medium text-background backdrop-blur-sm">
            Sold out
          </span>
        ) : null}
      </button>

      <div className="flex flex-1 flex-col p-4">
        <div className="flex items-start justify-between gap-3">
          <button
            type="button"
            onClick={onEdit}
            className="min-w-0 text-left"
          >
            <h3 className="truncate font-medium text-foreground">{product.name}</h3>
          </button>
          <span className="shrink-0 text-sm font-semibold text-foreground">
            R {formatMoney(product.price)}
          </span>
        </div>

        <p className="mt-1 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
          {product.description ?? "No description"}
        </p>

        {product.tags.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {product.tags.slice(0, 3).map((tag) => (
              <Badge key={tag} variant="secondary" className="rounded-full font-normal">
                {tag}
              </Badge>
            ))}
          </div>
        ) : null}

        <div className="mt-auto flex items-center justify-between gap-3 border-t border-border/60 pt-3.5">
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <Switch
              size="sm"
              checked={product.is_available}
              onCheckedChange={onToggleAvailability}
              aria-label={`${product.name} available`}
            />
            {product.is_available ? "Available" : "Sold out"}
          </label>
          <div className="flex items-center gap-0.5 opacity-60 transition-opacity group-hover:opacity-100">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="text-muted-foreground hover:text-foreground"
              aria-label={`Edit ${product.name}`}
              onClick={onEdit}
            >
              <Pencil />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
              aria-label={`Delete ${product.name}`}
              onClick={onDelete}
            >
              <Trash2 />
            </Button>
          </div>
        </div>
      </div>
    </article>
  );
}

export function DashboardMenuPage() {
  const router = useRouter();
  const [accessToken, setAccessToken] = useState("");
  const [business, setBusiness] = useState<Business | null>(null);
  const [orders, setOrders] = useState<DashboardOrder[]>([]);
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [products, setProducts] = useState<ProductOut[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState("");
  const [search, setSearch] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [modifierGroups, setModifierGroups] = useState<ModifierGroupOut[]>([]);
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [savingTemplate, setSavingTemplate] = useState(false);

  const [draft, setDraft] = useState<MenuDishDraft | null>(null);
  const [showErrors, setShowErrors] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const [categoryDialogOpen, setCategoryDialogOpen] = useState(false);
  const [categoryName, setCategoryName] = useState("");
  const [editingCategory, setEditingCategory] = useState<CategoryOut | null>(null);
  const [isSavingCategory, setIsSavingCategory] = useState(false);

  const dishErrors = useMemo(
    () => (draft ? validateMenuDishDraft(draft) : {}),
    [draft],
  );

  useEffect(() => {
    const token = accessTokenFromStorage();
    if (!token) {
      toast.error("Please sign in to continue.");
      router.replace("/login");
      return;
    }

    let active = true;
    void (async () => {
      try {
        const businesses = await listBusinesses(token);
        const selected = pickBusinessForOwner(businesses);
        if (!selected) throw new ApiError("Complete your business profile first.", 400);
        saveSelectedBusinessId(selected.id);
        const [loadedCategories, loadedProducts, loadedOrders, loadedGroups] =
          await Promise.all([
            listCategories({ accessToken: token, businessId: selected.id }),
            listProducts({ accessToken: token, businessId: selected.id }),
            listDashboardOrders({ accessToken: token, businessId: selected.id }).catch(
              () => [] as DashboardOrder[],
            ),
            listModifierGroups({ accessToken: token, businessId: selected.id }).catch(
              () => [] as ModifierGroupOut[],
            ),
          ]);
        if (!active) return;
        setAccessToken(token);
        setBusiness(selected);
        setCategories(loadedCategories);
        setProducts(loadedProducts);
        setOrders(loadedOrders);
        setModifierGroups(loadedGroups);
        setSelectedCategoryId(
          loadedProducts[0]?.category_id ?? loadedCategories[0]?.id ?? "",
        );
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          toast.error("Your session has expired. Please sign in again.");
          router.replace("/login");
          return;
        }
        toast.error(error instanceof ApiError ? error.message : "Couldn't load menu.");
      } finally {
        if (active) setIsLoading(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [router]);

  const pendingCount = orders.filter((order) => order.status === "pending").length;
  const visibleProducts = useMemo(() => {
    const query = search.trim().toLowerCase();
    return products.filter((product) => {
      const matchesCategory = !selectedCategoryId || product.category_id === selectedCategoryId;
      const matchesSearch =
        !query ||
        product.name.toLowerCase().includes(query) ||
        (product.description ?? "").toLowerCase().includes(query);
      return matchesCategory && matchesSearch && !product.is_archived;
    });
  }, [products, search, selectedCategoryId]);
  const selectedCategory = categories.find((category) => category.id === selectedCategoryId);
  const activeProductCount = useMemo(
    () => products.filter((product) => !product.is_archived).length,
    [products],
  );
  const selectedCategoryForNewDish =
    selectedCategoryId || categories[0]?.id || "";

  async function handleAcceptingOrders(checked: boolean) {
    if (!accessToken || !business) return;
    const previous = business;
    setBusiness({ ...business, accepting_orders: checked });
    try {
      const updated = await toggleAcceptingOrders({
        accessToken,
        businessId: business.id,
        acceptingOrders: checked,
      });
      saveSelectedBusinessId(updated.id);
      setBusiness(updated);
    } catch (error) {
      setBusiness(previous);
      toast.error(
        error instanceof ApiError ? error.message : "Couldn't update accepting orders.",
      );
    }
  }

  async function handleCategoryActive(category: CategoryOut, checked: boolean) {
    if (!accessToken || !business) return;
    const previous = categories;
    setCategories((current) =>
      current.map((item) => (item.id === category.id ? { ...item, is_active: checked } : item)),
    );
    try {
      const updated = await updateCategoryActive({
        accessToken,
        businessId: business.id,
        categoryId: category.id,
        isActive: checked,
      });
      setCategories((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
    } catch (error) {
      setCategories(previous);
      toast.error(
        error instanceof ApiError ? error.message : "Couldn't update the category.",
      );
    }
  }

  function handleAddCategory() {
    if (!accessToken || !business) {
      toast.error("Menu is still loading. Try again in a moment.");
      return;
    }
    setEditingCategory(null);
    setCategoryName("");
    setCategoryDialogOpen(true);
  }

  function handleEditCategory(category: CategoryOut) {
    if (!accessToken || !business) {
      toast.error("Menu is still loading. Try again in a moment.");
      return;
    }
    setEditingCategory(category);
    setCategoryName(category.name);
    setCategoryDialogOpen(true);
  }

  async function handleSaveCategory() {
    const name = categoryName.trim();
    if (!name || !accessToken || !business) return;
    setIsSavingCategory(true);
    try {
      if (editingCategory) {
        const saved = await updateCategoryName({
          accessToken,
          businessId: business.id,
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
          businessId: business.id,
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
        error instanceof ApiError ? error.message : "Couldn't save category.",
      );
    } finally {
      setIsSavingCategory(false);
    }
  }

  async function handleDeleteCategory(category: CategoryOut) {
    if (!accessToken || !business) return;
    if (
      !window.confirm(
        `Delete ${category.name}? Dishes will stay in your menu without this category.`,
      )
    ) {
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
        businessId: business.id,
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

  function openNewDish() {
    if (!business) {
      toast.error("Menu is still loading. Try again in a moment.");
      return;
    }
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

  async function handleUploadMenuItemImage(image: File) {
    if (!accessToken || !business) {
      throw new ApiError("Menu is still loading. Try again in a moment.", 0);
    }
    return uploadMenuItemImage({
      accessToken,
      businessId: business.id,
      image,
    });
  }

  async function refreshModifierLibrary() {
    if (!accessToken || !business) return;
    try {
      setModifierGroups(
        await listModifierGroups({ accessToken, businessId: business.id }),
      );
    } catch {
      toast.warning("Saved successfully, but the modifier library could not refresh.");
    }
  }

  async function handleSaveDish() {
    if (!draft) return;
    setShowErrors(true);
    if (hasMenuDishErrors(dishErrors)) {
      toast.error("Check your dish details before saving.");
      return;
    }
    if (!accessToken || !business) {
      toast.error("Menu is still loading. Try again in a moment.");
      return;
    }

    setIsSaving(true);
    try {
      const saved = await saveMenuDish({
        accessToken,
        businessId: business.id,
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
        error instanceof ApiError ? error.message : "Couldn't save the dish.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDeleteDish(product: ProductOut) {
    if (!accessToken || !business) return;
    if (!window.confirm(`Delete ${product.name}?`)) return;
    const previous = products;
    setProducts((current) => current.filter((item) => item.id !== product.id));
    if (draft?.id === product.id) setDraft(null);
    try {
      await deleteProduct({
        accessToken,
        businessId: business.id,
        productId: product.id,
      });
      toast.success("Dish deleted.");
    } catch (error) {
      setProducts(previous);
      toast.error(
        error instanceof ApiError ? error.message : "Couldn't delete the dish.",
      );
    }
  }

  async function handleSaveTemplate(group: MenuOptionGroupDraft) {
    if (!accessToken || !business) return;
    setSavingTemplate(true);
    try {
      const saved = group.modifierGroupId
        ? await updateModifierGroup({
            accessToken,
            businessId: business.id,
            groupId: group.modifierGroupId,
            group,
          })
        : await createModifierGroup({
            accessToken,
            businessId: business.id,
            group,
          });
      setModifierGroups((current) => {
        const exists = current.some((item) => item.id === saved.id);
        return exists
          ? current.map((item) => (item.id === saved.id ? saved : item))
          : [...current, saved];
      });
      toast.success(group.modifierGroupId ? "Template updated." : "Template created.");
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : "Couldn't save the template.",
      );
    } finally {
      setSavingTemplate(false);
    }
  }

  async function handleDeleteTemplate(group: ModifierGroupOut) {
    if (!accessToken || !business) return;
    setSavingTemplate(true);
    try {
      await deleteModifierGroup({
        accessToken,
        businessId: business.id,
        groupId: group.id,
      });
      setModifierGroups((current) => current.filter((item) => item.id !== group.id));
      toast.success("Template deleted.");
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : "Couldn't delete the template.",
      );
    } finally {
      setSavingTemplate(false);
    }
  }

  async function handleProductAvailability(product: ProductOut, checked: boolean) {
    if (!accessToken || !business) return;
    const previous = products;
    setProducts((current) =>
      current.map((item) =>
        item.id === product.id ? { ...item, is_available: checked } : item,
      ),
    );
    try {
      const updated = await updateProductAvailability({
        accessToken,
        businessId: business.id,
        productId: product.id,
        isAvailable: checked,
      });
      setProducts((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
    } catch (error) {
      setProducts(previous);
      toast.error(
        error instanceof ApiError ? error.message : "Couldn't update availability.",
      );
    }
  }

  return (
    <DashboardShell
      active="menu"
      title="Menu"
      business={business}
      pendingCount={pendingCount}
      acceptingOrders={business?.accepting_orders ?? true}
      onAcceptingOrdersChange={(checked) => void handleAcceptingOrders(checked)}
    >
      {isLoading ? (
        <div className="grid min-h-[520px] place-items-center">
          <Spinner />
        </div>
      ) : (
        <div className="min-w-0">
          <section className="mb-6 flex flex-wrap items-end gap-4">
            <div className="min-w-0 flex-1">
              <p className="text-sm text-muted-foreground">
                Manage categories, dishes, availability, and options.
              </p>
            </div>
            <Button variant="outline" className="h-10" onClick={() => setTemplatesOpen(true)}>
              <Layers data-icon="inline-start" />
              Modifier templates
            </Button>
            <Button variant="outline" className="h-10" onClick={handleAddCategory}>
              <Plus data-icon="inline-start" />
              Add category
            </Button>
            <Button className="h-10" onClick={openNewDish}>
              <Plus data-icon="inline-start" />
              Add dish
            </Button>
          </section>

          <div className="grid min-h-[560px] gap-4 lg:grid-cols-[200px_minmax(0,1fr)]">
            <Card className="flex max-h-[calc(100vh-11rem)] flex-col self-start overflow-hidden rounded-lg py-0 shadow-sm lg:sticky lg:top-20">
              <CardContent className="flex min-h-0 flex-1 flex-col p-3">
                <h3 className="mb-2 px-2.5 text-base font-semibold text-foreground">
                  Categories
                </h3>

                {categories.length === 0 ? (
                  <p className="px-2.5 text-sm text-muted-foreground">
                    No categories yet
                  </p>
                ) : (
                  <div className="-mr-1.5 flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto pr-2.5 [scrollbar-color:var(--muted-foreground)_transparent] [scrollbar-width:thin] [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-muted-foreground/40 [&::-webkit-scrollbar-track]:bg-transparent">
                    <button
                      type="button"
                      onClick={() => setSelectedCategoryId("")}
                      className={cn(
                        "flex items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm transition-colors",
                        selectedCategoryId === ""
                          ? "bg-primary/8 font-medium text-primary"
                          : "text-foreground hover:bg-muted",
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate">All items</span>
                      <span
                        className={cn(
                          "shrink-0 text-xs",
                          selectedCategoryId === ""
                            ? "text-primary"
                            : "text-muted-foreground",
                        )}
                      >
                        {activeProductCount}
                      </span>
                    </button>

                    {categories.map((category) => {
                      const active = category.id === selectedCategoryId;
                      return (
                        <div
                          key={category.id}
                          className={cn(
                            "group flex items-center gap-2 rounded-md px-2.5 py-2 text-sm transition-colors",
                            active
                              ? "bg-primary/8 text-primary"
                              : "text-foreground hover:bg-muted",
                          )}
                        >
                          <button
                            type="button"
                            onClick={() => setSelectedCategoryId(category.id)}
                            title={category.name}
                            className={cn(
                              "min-w-0 flex-1 truncate text-left",
                              active && "font-medium",
                              !category.is_active && !active && "text-muted-foreground",
                            )}
                          >
                            {category.name}
                          </button>

                          <span
                            className={cn(
                              "shrink-0",
                              active
                                ? "hidden"
                                : "group-hover:hidden group-focus-within:hidden",
                            )}
                          >
                            {category.is_active ? (
                              <span className="text-xs text-muted-foreground">
                                {productCount(products, category.id)}
                              </span>
                            ) : (
                              <span className="rounded-full border border-border px-2 py-px text-[11px] text-muted-foreground">
                                Hidden
                              </span>
                            )}
                          </span>

                          <div
                            className={cn(
                              "shrink-0 items-center gap-0.5",
                              active
                                ? "flex"
                                : "hidden group-hover:flex group-focus-within:flex",
                            )}
                          >
                            <Switch
                              size="sm"
                              checked={category.is_active}
                              onCheckedChange={(checked) =>
                                void handleCategoryActive(category, checked)
                              }
                              aria-label={`${category.name} visible`}
                            />
                            <details className="relative">
                              <summary
                                className={cn(
                                  "flex size-7 cursor-pointer list-none items-center justify-center rounded-md transition-colors hover:bg-muted [&::-webkit-details-marker]:hidden",
                                  active
                                    ? "text-primary"
                                    : "text-muted-foreground hover:text-foreground",
                                )}
                                aria-label={`Open ${category.name} category actions`}
                              >
                                <MoreHorizontal className="size-4" aria-hidden="true" />
                              </summary>
                              <div className="absolute top-8 right-0 z-20 grid w-36 gap-1 rounded-lg border border-border bg-popover p-1 text-sm text-popover-foreground shadow-lg">
                                <button
                                  type="button"
                                  className="flex h-8 items-center gap-2 rounded-md px-2 text-left hover:bg-muted"
                                  onClick={() => handleEditCategory(category)}
                                  aria-label={`Edit ${category.name} category`}
                                >
                                  <Pencil className="size-3.5" aria-hidden="true" />
                                  Edit
                                </button>
                                <button
                                  type="button"
                                  className="flex h-8 items-center gap-2 rounded-md px-2 text-left text-destructive hover:bg-destructive/10"
                                  onClick={() => void handleDeleteCategory(category)}
                                  aria-label={`Delete ${category.name} category`}
                                >
                                  <Trash2 className="size-3.5" aria-hidden="true" />
                                  Delete
                                </button>
                              </div>
                            </details>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                <Button
                  type="button"
                  variant="outline"
                  size="lg"
                  onClick={handleAddCategory}
                  className="mt-3 h-10 w-full shrink-0"
                >
                  <Plus data-icon="inline-start" />
                  Add category
                </Button>
              </CardContent>
            </Card>

            <Card className="rounded-lg py-0 shadow-sm">
              <CardContent className="p-5">
                <div className="flex flex-wrap items-center gap-4">
                  <h3 className="font-heading text-xl font-medium text-foreground">
                    {selectedCategory?.name ?? "All items"}{" "}
                    <span className="font-sans text-sm text-muted-foreground">
                      - {visibleProducts.length} dishes
                    </span>
                  </h3>
                  <div className="relative ml-auto min-w-[250px]">
                    <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                      placeholder="Search dishes..."
                      className="h-10 pl-9"
                    />
                  </div>
                </div>
                <div className="mt-5 grid gap-4 sm:grid-cols-2 2xl:grid-cols-3">
                  {visibleProducts.map((product) => (
                    <ProductCard
                      key={product.id}
                      product={product}
                      selected={draft?.id === product.id}
                      onEdit={() => openExistingDish(product)}
                      onToggleAvailability={(checked) =>
                        void handleProductAvailability(product, checked)
                      }
                      onDelete={() => void handleDeleteDish(product)}
                    />
                  ))}
                  {visibleProducts.length === 0 ? (
                    <div className="col-span-full grid min-h-[240px] place-items-center rounded-lg border border-dashed border-border bg-muted/25 p-8 text-center">
                      <div>
                        <p className="font-medium text-foreground">No dishes here yet</p>
                        <p className="mt-1 text-sm text-muted-foreground">
                          Add a dish to start building this category.
                        </p>
                        <Button className="mt-4" onClick={openNewDish}>
                          <Plus data-icon="inline-start" />
                          Add dish
                        </Button>
                      </div>
                    </div>
                  ) : null}
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

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
          onManageTemplates={() => setTemplatesOpen(true)}
        />
      ) : null}

      <ModifierTemplateDialog
        open={templatesOpen}
        groups={modifierGroups.filter((group) => group.is_template)}
        isSaving={savingTemplate}
        onOpenChange={setTemplatesOpen}
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
          isSaving={isSavingCategory}
          onChange={setCategoryName}
          onClose={() => {
            if (isSavingCategory) return;
            setCategoryName("");
            setEditingCategory(null);
            setCategoryDialogOpen(false);
          }}
          onSubmit={() => void handleSaveCategory()}
        />
      ) : null}
    </DashboardShell>
  );
}
