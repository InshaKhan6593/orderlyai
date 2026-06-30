export const SELECTED_BUSINESS_STORAGE_KEY = "orderly.selected_business_id";

type BusinessStorage = Pick<Storage, "getItem" | "removeItem" | "setItem">;
type SelectableBusiness = {
  id: string;
  status?: string | null;
};

function browserStorage(): BusinessStorage | undefined {
  if (typeof window === "undefined") return undefined;
  return window.localStorage;
}

export function readSelectedBusinessId(
  storage: BusinessStorage | undefined = browserStorage(),
): string | null {
  if (!storage) return null;
  try {
    return storage.getItem(SELECTED_BUSINESS_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function saveSelectedBusinessId(
  businessId: string,
  storage: BusinessStorage | undefined = browserStorage(),
): void {
  if (!storage) return;
  try {
    storage.setItem(SELECTED_BUSINESS_STORAGE_KEY, businessId);
  } catch {
    // Storage can fail in private browsing or locked-down embedded contexts.
  }
}

export function clearSelectedBusinessId(
  storage: BusinessStorage | undefined = browserStorage(),
): void {
  if (!storage) return;
  try {
    storage.removeItem(SELECTED_BUSINESS_STORAGE_KEY);
  } catch {
    // Ignore storage failures; selection will fall back to server data.
  }
}

export function pickBusinessForOwner<TBusiness extends SelectableBusiness>(
  businesses: TBusiness[],
  storage: BusinessStorage | undefined = browserStorage(),
): TBusiness | null {
  const savedBusinessId = readSelectedBusinessId(storage);
  const savedBusiness = savedBusinessId
    ? businesses.find((business) => business.id === savedBusinessId)
    : undefined;

  if (savedBusiness) return savedBusiness;
  if (savedBusinessId) clearSelectedBusinessId(storage);

  return (
    businesses.find((business) => business.status === "active") ??
    businesses.find((business) => business.status === "onboarding") ??
    businesses[0] ??
    null
  );
}
