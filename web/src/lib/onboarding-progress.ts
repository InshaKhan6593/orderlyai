import { pickBusinessForOwner } from "@/lib/business-selection";

export const ONBOARDING_RESUME_STORAGE_KEY = "orderly.onboarding_resume_path";

export const IMPLEMENTED_ONBOARDING_RESUME_PATHS = [
  "/onboarding",
  "/onboarding/business-profile",
  "/onboarding/hours",
  "/onboarding/fulfillment",
  "/onboarding/menu",
  "/onboarding/assistant",
  "/onboarding/whatsapp",
  "/onboarding/review",
] as const;

export type OnboardingResumePath = (typeof IMPLEMENTED_ONBOARDING_RESUME_PATHS)[number];

type ProgressStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

type ResumeBusinessSnapshot = {
  id: string;
  status?: string;
  offers_delivery: boolean;
  offers_pickup: boolean;
  min_order_amount: string | number;
  default_prep_minutes: number;
  packaging_fee: string | number;
};

type ResumeDeliveryZoneSnapshot = {
  id: string;
  name?: string;
  fee?: string | number;
};

type ListBusinesses = (accessToken: string) => Promise<ResumeBusinessSnapshot[]>;
type ListDeliveryZones = (args: {
  accessToken: string;
  businessId: string;
}) => Promise<ResumeDeliveryZoneSnapshot[]>;

function browserStorage(): ProgressStorage | null {
  if (typeof window === "undefined") return null;
  return window.localStorage;
}

export function normalizeOnboardingResumePath(
  path: string | null | undefined,
): OnboardingResumePath | null {
  return IMPLEMENTED_ONBOARDING_RESUME_PATHS.includes(path as OnboardingResumePath)
    ? (path as OnboardingResumePath)
    : null;
}

export function readOnboardingResumePath(
  storage: ProgressStorage | null = browserStorage(),
): OnboardingResumePath | null {
  if (!storage) return null;
  return normalizeOnboardingResumePath(storage.getItem(ONBOARDING_RESUME_STORAGE_KEY));
}

export function saveOnboardingResumePath(
  path: string,
  storage: ProgressStorage | null = browserStorage(),
): void {
  if (!storage) return;
  const normalized = normalizeOnboardingResumePath(path);
  if (!normalized) return;
  storage.setItem(ONBOARDING_RESUME_STORAGE_KEY, normalized);
}

function moneyChanged(value: string | number): boolean {
  const amount = Number(value);
  return Number.isFinite(amount) && amount > 0;
}

export function inferOnboardingResumePath(
  business: ResumeBusinessSnapshot | undefined,
  deliveryZones: ResumeDeliveryZoneSnapshot[],
): OnboardingResumePath {
  if (!business) return "/onboarding";

  const hasFulfillmentProgress =
    deliveryZones.length > 0 ||
    !business.offers_delivery ||
    !business.offers_pickup ||
    moneyChanged(business.min_order_amount) ||
    business.default_prep_minutes !== 30 ||
    moneyChanged(business.packaging_fee);

  return hasFulfillmentProgress ? "/onboarding/fulfillment" : "/onboarding/hours";
}

export async function resolveOnboardingResumePath({
  accessToken,
  storage = browserStorage(),
  listBusinesses,
  listDeliveryZones,
}: {
  accessToken: string;
  storage?: ProgressStorage | null;
  listBusinesses: ListBusinesses;
  listDeliveryZones: ListDeliveryZones;
}): Promise<OnboardingResumePath> {
  const stored = readOnboardingResumePath(storage);
  if (stored) return stored;

  try {
    const businesses = await listBusinesses(accessToken);
    const business = pickBusinessForOwner(businesses, storage ?? undefined);
    if (!business) return "/onboarding";

    const zones = await listDeliveryZones({
      accessToken,
      businessId: business.id,
    }).catch(() => []);

    return inferOnboardingResumePath(business, zones);
  } catch {
    return "/onboarding";
  }
}
