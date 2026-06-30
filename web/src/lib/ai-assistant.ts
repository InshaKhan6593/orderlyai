import { apiUrl } from "@/lib/api";
import { ApiError } from "@/lib/auth";

type Fetcher = typeof fetch;

export type AgentConfigOut = {
  id: string | null;
  business_id: string;
  greeting_message: string;
  language: "en";
  upsell_enabled: boolean;
  human_handoff_phone: string | null;
  extra_instructions: string | null;
};

export type AgentConfigValues = {
  greetingMessage: string;
  upsellEnabled: boolean;
  humanHandoffPhone: string;
  extraInstructions: string;
};

export type AgentConfigBusiness = {
  name: string;
  helpline_phone: string | null;
};

export type AgentConfigPayload = {
  greeting_message: string;
  upsell_enabled: boolean;
  human_handoff_phone: string | null;
  extra_instructions: string | null;
};

export function defaultGreeting(businessName: string): string {
  return `Hi! Welcome to ${businessName}. I can show you our menu and take your order. What would you like today?`;
}

function trimmedOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function createAgentConfigValues(
  business: AgentConfigBusiness,
  config?: AgentConfigOut | null,
): AgentConfigValues {
  return {
    greetingMessage: config?.greeting_message ?? defaultGreeting(business.name),
    upsellEnabled: config?.upsell_enabled ?? true,
    humanHandoffPhone:
      config?.human_handoff_phone ?? business.helpline_phone ?? "",
    extraInstructions: config?.extra_instructions ?? "",
  };
}

export function buildAgentConfigPayload(
  values: AgentConfigValues,
): AgentConfigPayload {
  return {
    greeting_message: values.greetingMessage.trim(),
    upsell_enabled: values.upsellEnabled,
    human_handoff_phone: trimmedOrNull(values.humanHandoffPhone),
    extra_instructions: trimmedOrNull(values.extraInstructions),
  };
}

async function agentConfigRequest<T>({
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
    response = await fetcher(apiUrl(`/businesses/${businessId}/agent-config`), {
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
    let message = "Couldn't save your assistant settings. Please try again.";
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

export function getAgentConfig({
  accessToken,
  businessId,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  fetcher?: Fetcher;
}): Promise<AgentConfigOut> {
  return agentConfigRequest<AgentConfigOut>({
    accessToken,
    businessId,
    fetcher,
  });
}

export function saveAgentConfig({
  accessToken,
  businessId,
  values,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  values: AgentConfigValues;
  fetcher?: Fetcher;
}): Promise<AgentConfigOut> {
  return agentConfigRequest<AgentConfigOut>({
    accessToken,
    businessId,
    method: "PUT",
    body: buildAgentConfigPayload(values),
    fetcher,
  });
}
