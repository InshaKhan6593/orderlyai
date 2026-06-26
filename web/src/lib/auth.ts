import { apiUrl } from "@/lib/api";

type Tokens = {
  access_token: string;
  refresh_token: string;
  token_type: string;
};

const ACCESS_KEY = "orderly.access_token";
const REFRESH_KEY = "orderly.refresh_token";

/**
 * Tokens are kept in web storage for now so the scaffold is testable end-to-end.
 * `remember` chooses localStorage (persists across sessions) vs sessionStorage
 * (cleared when the tab closes) — this is what the "Remember me" checkbox drives.
 * Swapped for httpOnly cookies + refresh rotation when the auth flow is hardened.
 */
export function storeTokens(tokens: Tokens, remember = true): void {
  if (typeof window === "undefined") return;
  const primary = remember ? localStorage : sessionStorage;
  const secondary = remember ? sessionStorage : localStorage;
  primary.setItem(ACCESS_KEY, tokens.access_token);
  primary.setItem(REFRESH_KEY, tokens.refresh_token);
  // Make sure a prior choice in the other store doesn't linger.
  secondary.removeItem(ACCESS_KEY);
  secondary.removeItem(REFRESH_KEY);
}

/** Sign out: drop access + refresh tokens from both stores. */
export function clearTokens(): void {
  if (typeof window === "undefined") return;
  for (const store of [window.localStorage, window.sessionStorage]) {
    store.removeItem(ACCESS_KEY);
    store.removeItem(REFRESH_KEY);
  }
}

/** Error envelope returned by the backend: { error: { code, message } }. */
type ApiErrorBody = { error?: { code?: string; message?: string } };

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

/** Shared POST helper for the auth endpoints. Maps the backend error envelope. */
async function postAuth(
  path: string,
  body: Record<string, unknown>,
  fallback: (status: number) => string,
): Promise<Tokens> {
  let res: Response;
  try {
    res = await fetch(apiUrl(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(
      "Couldn't reach the server. Is the API running on http://localhost:8000?",
      0,
    );
  }

  if (!res.ok) {
    let message = fallback(res.status);
    let code: string | undefined;
    try {
      const errorBody = (await res.json()) as ApiErrorBody;
      if (errorBody.error?.message) message = errorBody.error.message;
      code = errorBody.error?.code;
    } catch {
      // non-JSON error body — keep the status-based message
    }
    throw new ApiError(message, res.status, code);
  }

  return (await res.json()) as Tokens;
}

/** POST /auth/login — returns access + refresh tokens, or throws ApiError. */
export function login(email: string, password: string): Promise<Tokens> {
  return postAuth("/auth/login", { email, password }, (status) =>
    status === 401
      ? "Incorrect email or password."
      : "Login failed. Please try again.",
  );
}

/** POST /auth/register — creates the account and returns tokens, or throws. */
export function register(
  email: string,
  password: string,
  fullName?: string,
): Promise<Tokens> {
  return postAuth(
    "/auth/register",
    { email, password, full_name: fullName?.trim() || null },
    (status) =>
      status === 409
        ? "An account with this email already exists."
        : "Couldn't create your account. Please try again.",
  );
}

/** The shape returned by GET /auth/me (mirrors the backend `UserOut`). */
export type CurrentUserProfile = {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
};

/** Read the stored access token (localStorage preferred, then sessionStorage). */
export function readAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return (
    window.localStorage.getItem(ACCESS_KEY) ??
    window.sessionStorage.getItem(ACCESS_KEY)
  );
}

/** GET /auth/me — the authenticated user, or throws ApiError. */
export async function getCurrentUser(
  accessToken: string,
  fetcher: typeof fetch = fetch,
): Promise<CurrentUserProfile> {
  let res: Response;
  try {
    res = await fetcher(apiUrl("/auth/me"), {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
  } catch {
    throw new ApiError(
      "Couldn't reach the server. Is the API running on http://localhost:8000?",
      0,
    );
  }

  if (!res.ok) {
    let message = "Couldn't load your account.";
    let code: string | undefined;
    try {
      const errorBody = (await res.json()) as ApiErrorBody;
      if (errorBody.error?.message) message = errorBody.error.message;
      code = errorBody.error?.code;
    } catch {
      // non-JSON error body — keep the status-based message
    }
    throw new ApiError(message, res.status, code);
  }

  return (await res.json()) as CurrentUserProfile;
}
