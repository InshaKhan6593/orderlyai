import { apiUrl } from "@/lib/api";
import { ApiError } from "@/lib/auth";

type Fetcher = typeof fetch;

export type WhatsAppConnectionMode = "test" | "live";
export type WhatsAppConnectionStatus =
  | "not_configured"
  | "configured"
  | "verified"
  | "error";

export type WhatsAppConnectionOut = {
  id: string | null;
  business_id: string;
  mode: WhatsAppConnectionMode;
  waba_id: string;
  phone_number_id: string;
  display_phone_number: string | null;
  display_name: string | null;
  status: WhatsAppConnectionStatus;
  has_access_token: boolean;
};

export type WhatsAppConnectionValues = {
  mode: WhatsAppConnectionMode;
  wabaId: string;
  phoneNumberId: string;
  displayPhoneNumber: string;
  displayName: string;
  accessToken: string;
};

export type WhatsAppConnectionPayload = {
  mode: WhatsAppConnectionMode;
  waba_id: string;
  phone_number_id: string;
  display_phone_number: string | null;
  display_name: string | null;
  access_token?: string;
};

function trimmedOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function createWhatsAppConnectionValues(
  connection?: WhatsAppConnectionOut | null,
): WhatsAppConnectionValues {
  return {
    mode: connection?.mode ?? "test",
    wabaId: connection?.waba_id ?? "",
    phoneNumberId: connection?.phone_number_id ?? "",
    displayPhoneNumber: connection?.display_phone_number ?? "",
    displayName: connection?.display_name ?? "",
    accessToken: "",
  };
}

export function buildWhatsAppConnectionPayload(
  values: WhatsAppConnectionValues,
): WhatsAppConnectionPayload {
  const accessToken = values.accessToken.trim();
  return {
    mode: values.mode,
    waba_id: values.wabaId.trim(),
    phone_number_id: values.phoneNumberId.trim(),
    display_phone_number: trimmedOrNull(values.displayPhoneNumber),
    display_name: trimmedOrNull(values.displayName),
    ...(accessToken ? { access_token: accessToken } : {}),
  };
}

async function whatsappConnectionRequest<T>({
  accessToken,
  businessId,
  method = "GET",
  body,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  method?: "GET" | "PUT";
  body?: unknown;
  fetcher?: Fetcher;
}): Promise<T> {
  let response: Response;
  try {
    response = await fetcher(apiUrl(`/businesses/${businessId}/whatsapp-connection`), {
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
    let message = "Couldn't save your WhatsApp connection. Please try again.";
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

export function getWhatsAppConnection({
  accessToken,
  businessId,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  fetcher?: Fetcher;
}): Promise<WhatsAppConnectionOut> {
  return whatsappConnectionRequest<WhatsAppConnectionOut>({
    accessToken,
    businessId,
    fetcher,
  });
}

export function saveWhatsAppConnection({
  accessToken,
  businessId,
  values,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  values: WhatsAppConnectionValues;
  fetcher?: Fetcher;
}): Promise<WhatsAppConnectionOut> {
  return whatsappConnectionRequest<WhatsAppConnectionOut>({
    accessToken,
    businessId,
    method: "PUT",
    body: buildWhatsAppConnectionPayload(values),
    fetcher,
  });
}
