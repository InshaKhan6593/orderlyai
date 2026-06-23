import { apiUrl } from "@/lib/api";
import { ApiError } from "@/lib/auth";

export type DeliveryZoneDraft = {
  clientId: string;
  id: string | null;
  name: string;
  fee: string;
  minOrder: string;
  etaMinutes: string;
  isActive: boolean;
};

export type FulfillmentValues = {
  offersDelivery: boolean;
  offersPickup: boolean;
  offersDineIn: boolean;
  minOrderAmount: string;
  defaultPrepMinutes: string;
  packagingFee: string;
  zones: DeliveryZoneDraft[];
};

export type FulfillmentBusinessSnapshot = {
  offers_delivery: boolean;
  offers_pickup: boolean;
  min_order_amount: string | number;
  default_prep_minutes: number;
  packaging_fee: string | number;
};

export type DeliveryZoneOut = {
  id: string;
  business_id: string;
  name: string;
  fee: string | number;
  min_order: string | number;
  eta_minutes: number | null;
  is_active: boolean;
};

type ZoneFieldErrors = {
  name?: string;
  fee?: string;
  minOrder?: string;
  etaMinutes?: string;
};

export type FulfillmentErrors = {
  fulfillment?: string;
  minOrderAmount?: string;
  defaultPrepMinutes?: string;
  packagingFee?: string;
  zones?: string;
  zoneFields: Record<string, ZoneFieldErrors>;
};

type Fetcher = typeof fetch;

export function createDeliveryZoneDraft(clientId: string): DeliveryZoneDraft {
  return {
    clientId,
    id: null,
    name: "",
    fee: "",
    minOrder: "",
    etaMinutes: "",
    isActive: true,
  };
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

export function validateFulfillment(values: FulfillmentValues): FulfillmentErrors {
  const errors: FulfillmentErrors = { zoneFields: {} };

  if (!values.offersDelivery && !values.offersPickup) {
    errors.fulfillment = "Turn on delivery or pickup to continue.";
  }
  if (values.minOrderAmount.trim() && !isNonNegativeNumber(values.minOrderAmount)) {
    errors.minOrderAmount = "Enter a valid minimum order amount.";
  }
  if (!isNonNegativeNumber(values.defaultPrepMinutes, true)) {
    errors.defaultPrepMinutes = "Enter a valid prep time.";
  }
  if (values.packagingFee.trim() && !isNonNegativeNumber(values.packagingFee)) {
    errors.packagingFee = "Enter a valid packaging fee.";
  }

  if (values.offersDelivery) {
    for (const zone of values.zones) {
      const zoneErrors: ZoneFieldErrors = {};
      if (!zone.name.trim()) zoneErrors.name = "Zone name is required.";
      if (!zone.fee.trim()) {
        zoneErrors.fee = "Delivery fee is required.";
      } else if (!isNonNegativeNumber(zone.fee)) {
        zoneErrors.fee = "Enter a valid delivery fee.";
      }
      if (zone.minOrder.trim() && !isNonNegativeNumber(zone.minOrder)) {
        zoneErrors.minOrder = "Enter a valid minimum order.";
      }
      if (zone.etaMinutes.trim() && !isNonNegativeNumber(zone.etaMinutes, true)) {
        zoneErrors.etaMinutes = "Enter a valid ETA.";
      }
      if (Object.keys(zoneErrors).length > 0) {
        errors.zoneFields[zone.clientId] = zoneErrors;
      }
    }

    const hasCompleteActiveZone = values.zones.some(
      (zone) => zone.isActive && errors.zoneFields[zone.clientId] === undefined,
    );
    if (!hasCompleteActiveZone) {
      errors.zones = "Delivery requires at least one complete active zone.";
    }
  }

  return errors;
}

export function hasFulfillmentErrors(errors: FulfillmentErrors): boolean {
  return (
    Boolean(
      errors.fulfillment ||
        errors.minOrderAmount ||
        errors.defaultPrepMinutes ||
        errors.packagingFee ||
        errors.zones,
    ) || Object.keys(errors.zoneFields).length > 0
  );
}

function moneyOrZero(value: string): string {
  return value.trim() || "0";
}

export function buildBusinessSettingsPayload(values: FulfillmentValues) {
  return {
    offers_delivery: values.offersDelivery,
    offers_pickup: values.offersPickup,
    min_order_amount: moneyOrZero(values.minOrderAmount),
    default_prep_minutes: Number(values.defaultPrepMinutes),
    packaging_fee: moneyOrZero(values.packagingFee),
  };
}

export function buildZonePayload(zone: DeliveryZoneDraft) {
  return {
    name: zone.name.trim(),
    fee: moneyOrZero(zone.fee),
    min_order: moneyOrZero(zone.minOrder),
    eta_minutes: zone.etaMinutes.trim() ? Number(zone.etaMinutes) : null,
    is_active: zone.isActive,
  };
}

export function createFulfillmentValues(
  business: FulfillmentBusinessSnapshot,
  zones: DeliveryZoneOut[],
): FulfillmentValues {
  return {
    offersDelivery: business.offers_delivery,
    offersPickup: business.offers_pickup,
    offersDineIn: false,
    minOrderAmount: String(business.min_order_amount),
    defaultPrepMinutes: String(business.default_prep_minutes),
    packagingFee: String(business.packaging_fee),
    zones: zones.map((zone) => ({
      clientId: zone.id,
      id: zone.id,
      name: zone.name,
      fee: String(zone.fee),
      minOrder: String(zone.min_order),
      etaMinutes: zone.eta_minutes === null ? "" : String(zone.eta_minutes),
      isActive: zone.is_active,
    })),
  };
}

async function fulfillmentRequest<T>({
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
    let message = "Couldn't save fulfillment settings. Please try again.";
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

export function listDeliveryZones({
  accessToken,
  businessId,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  fetcher?: Fetcher;
}): Promise<DeliveryZoneOut[]> {
  return fulfillmentRequest<DeliveryZoneOut[]>({
    path: `/businesses/${businessId}/delivery-zones`,
    accessToken,
    fetcher,
  });
}

export async function saveFulfillment({
  accessToken,
  businessId,
  values,
  deletedZoneIds,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  values: FulfillmentValues;
  deletedZoneIds: string[];
  fetcher?: Fetcher;
}): Promise<void> {
  const errors = validateFulfillment(values);
  if (hasFulfillmentErrors(errors)) {
    throw new ApiError("Check your fulfillment settings before saving.", 422);
  }

  const zonePath = `/businesses/${businessId}/delivery-zones`;
  const zonesToSave = values.offersDelivery ? values.zones : [];
  await Promise.all([
    fulfillmentRequest({
      path: `/businesses/${businessId}`,
      accessToken,
      method: "PATCH",
      body: buildBusinessSettingsPayload(values),
      fetcher,
    }),
    ...zonesToSave.map((zone) =>
      fulfillmentRequest({
        path: zone.id ? `${zonePath}/${zone.id}` : zonePath,
        accessToken,
        method: zone.id ? "PATCH" : "POST",
        body: buildZonePayload(zone),
        fetcher,
      }),
    ),
    ...deletedZoneIds.map((zoneId) =>
      fulfillmentRequest({
        path: `${zonePath}/${zoneId}`,
        accessToken,
        method: "DELETE",
        fetcher,
      }),
    ),
  ]);
}
