import { z } from "zod";

import { apiUrl } from "@/lib/api";
import { ApiError } from "@/lib/auth";

export const businessTypes = [
  "restaurant",
  "cafe",
  "bakery",
  "home_kitchen",
  "other",
] as const;

export const businessProfileSchema = z.object({
  name: z.string().trim().min(1, "Business name is required.").max(255),
  type: z.enum(businessTypes, { message: "Choose a business type." }),
  description: z.string().max(160, "Description must be 160 characters or less."),
  logoPath: z.string(),
  coverPath: z.string(),
  timezone: z.string().trim().min(1, "Timezone is required."),
  currency: z.string().trim().min(1, "Currency is required."),
  languages: z.array(z.string()).min(1, "Choose at least one language."),
  phoneCountry: z.string(),
  phoneNumber: z.string(),
  email: z.union([z.literal(""), z.email("Enter a valid email address.")]),
  address: z.string(),
  mapsUrl: z.union([z.literal(""), z.url("Enter a valid Google Maps URL.")]),
});

export type BusinessProfileValues = z.infer<typeof businessProfileSchema>;

export function shouldShowFieldError(
  hasError: boolean,
  isTouched: boolean,
  submitCount: number,
): boolean {
  return hasError && (isTouched || submitCount > 0);
}

export function hasRequiredBusinessProfileFields(
  values: Pick<BusinessProfileValues, "name" | "type" | "timezone" | "currency">,
): boolean {
  return Boolean(
    values.name.trim() &&
      values.type &&
      values.timezone.trim() &&
      values.currency.trim(),
  );
}

export type Business = {
  id: string;
  name: string;
  slug: string;
  type: (typeof businessTypes)[number];
  description: string | null;
  logo_url: string | null;
  cover_url: string | null;
  timezone: string;
  currency: string;
  languages: string[];
  helpline_phone: string | null;
  email: string | null;
  address: string | null;
  maps_url: string | null;
  status: "onboarding" | "active" | "paused" | "suspended";
  offers_delivery: boolean;
  offers_pickup: boolean;
  min_order_amount: string | number;
  default_prep_minutes: number;
  packaging_fee: string | number;
  accepting_orders: boolean;
};

type BusinessCreatePayload = Pick<
  BusinessProfileValues,
  "name" | "type" | "timezone" | "currency"
>;

type BusinessUpdatePayload = {
  name: string;
  type: BusinessProfileValues["type"];
  description: string | null;
  logo_url: string | null;
  cover_url: string | null;
  timezone: string;
  currency: string;
  languages: string[];
  helpline_phone: string | null;
  email: string | null;
  address: string | null;
  maps_url: string | null;
};

function trimmedOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function buildBusinessPayloads(values: BusinessProfileValues): {
  create: BusinessCreatePayload;
  update: BusinessUpdatePayload;
} {
  const name = values.name.trim();
  const phoneNumber = values.phoneNumber.trim();

  return {
    create: {
      name,
      type: values.type,
      timezone: values.timezone,
      currency: values.currency,
    },
    update: {
      name,
      type: values.type,
      description: trimmedOrNull(values.description),
      logo_url: trimmedOrNull(values.logoPath),
      cover_url: trimmedOrNull(values.coverPath),
      timezone: values.timezone,
      currency: values.currency,
      languages: values.languages,
      helpline_phone: phoneNumber
        ? `${values.phoneCountry.trim()} ${phoneNumber}`.trim()
        : null,
      email: trimmedOrNull(values.email),
      address: trimmedOrNull(values.address),
      maps_url: trimmedOrNull(values.mapsUrl),
    },
  };
}

type Fetcher = typeof fetch;

async function businessRequest<T>({
  path,
  method = "GET",
  accessToken,
  body,
  fetcher = fetch,
}: {
  path: string;
  method?: "GET" | "POST" | "PATCH";
  accessToken: string;
  body?: unknown;
  fetcher?: Fetcher;
}): Promise<T> {
  let response: Response;
  try {
    response = await fetcher(apiUrl(path), {
      method,
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
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
    let message = "Couldn't save your business profile. Please try again.";
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

  return (await response.json()) as T;
}

export function listBusinesses(
  accessToken: string,
  fetcher: Fetcher = fetch,
): Promise<Business[]> {
  return businessRequest<Business[]>({
    path: "/businesses",
    accessToken,
    fetcher,
  });
}

/** Take a business live: flip status to active and open the order kill-switch. */
export function goLiveBusiness({
  accessToken,
  businessId,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  fetcher?: Fetcher;
}): Promise<Business> {
  return businessRequest<Business>({
    path: `/businesses/${businessId}`,
    method: "PATCH",
    accessToken,
    body: { status: "active", accepting_orders: true },
    fetcher,
  });
}

export async function saveBusinessProfile({
  accessToken,
  values,
  existingBusinessId,
  fetcher = fetch,
}: {
  accessToken: string;
  values: BusinessProfileValues;
  existingBusinessId?: string;
  fetcher?: Fetcher;
}): Promise<Business> {
  const payloads = buildBusinessPayloads(values);
  let businessId = existingBusinessId;

  if (!businessId) {
    const created = await businessRequest<Business>({
      path: "/businesses",
      method: "POST",
      accessToken,
      body: payloads.create,
      fetcher,
    });
    businessId = created.id;
  }

  return businessRequest<Business>({
    path: `/businesses/${businessId}`,
    method: "PATCH",
    accessToken,
    body: payloads.update,
    fetcher,
  });
}
