import { apiUrl } from "@/lib/api";
import { ApiError } from "@/lib/auth";
import type { Business } from "@/lib/business-profile";

type Fetcher = typeof fetch;

export type DashboardOrderStatus =
  | "pending"
  | "accepted"
  | "rejected"
  | "preparing"
  | "ready"
  | "out_for_delivery"
  | "completed"
  | "cancelled";

export type DashboardOrderItem = {
  id: string;
  product_id: string | null;
  name_snapshot: string;
  price_snapshot: string | number;
  quantity: number;
  options_json: { name?: string; price_delta?: string | number }[];
  line_total: string | number;
};

export type DashboardOrderHistory = {
  id: string;
  status: DashboardOrderStatus;
  changed_by: string | null;
  created_at: string;
};

export type DashboardOrderCustomer = {
  id: string;
  name: string | null;
  wa_phone: string;
};

export type DashboardOrderZone = {
  id: string;
  name: string;
  fee: string | number;
  min_order: string | number;
  eta_minutes: number | null;
};

export type DashboardOrder = {
  id: string;
  business_id: string;
  customer_id: string;
  order_no: number;
  channel: string;
  status: DashboardOrderStatus;
  fulfillment: "delivery" | "pickup";
  address: string | null;
  zone_id: string | null;
  subtotal: string | number;
  delivery_fee: string | number;
  packaging_fee: string | number;
  total: string | number;
  payment_method: "cod" | "link" | "paid";
  payment_status: "unpaid" | "paid" | "refunded";
  notes: string | null;
  created_at: string;
  customer: DashboardOrderCustomer;
  zone: DashboardOrderZone | null;
  items: DashboardOrderItem[];
  status_history: DashboardOrderHistory[];
};

export type BoardColumnKey =
  | "new"
  | "accepted"
  | "preparing"
  | "ready_out"
  | "completed";

export type BoardColumn = {
  key: BoardColumnKey;
  title: string;
  statuses: DashboardOrderStatus[];
  orders: DashboardOrder[];
};

export type OrderAction = {
  label: string;
  status: DashboardOrderStatus;
};

export type DashboardOverview = {
  todayOrderCount: number;
  newOrderCount: number;
  ordersNeedingAttention: number;
  completedSales: number;
  completedOrderCount: number;
  topItems: { name: string; quantity: number }[];
};

const BOARD_DEFINITION: Omit<BoardColumn, "orders">[] = [
  { key: "new", title: "New", statuses: ["pending"] },
  { key: "accepted", title: "Accepted", statuses: ["accepted"] },
  { key: "preparing", title: "Preparing", statuses: ["preparing"] },
  { key: "ready_out", title: "Ready / Out", statuses: ["ready", "out_for_delivery"] },
  { key: "completed", title: "Completed", statuses: ["completed"] },
];

function numberValue(value: string | number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function formatMoney(value: string | number): string {
  return numberValue(value).toLocaleString("en-US", {
    maximumFractionDigits: 0,
  });
}

export function statusLabel(status: DashboardOrderStatus): string {
  switch (status) {
    case "pending":
      return "New";
    case "accepted":
      return "Accepted";
    case "preparing":
      return "Preparing";
    case "ready":
      return "Ready";
    case "out_for_delivery":
      return "Out for delivery";
    case "completed":
      return "Completed";
    case "rejected":
      return "Rejected";
    case "cancelled":
      return "Cancelled";
  }
}

export function groupOrdersForBoard(orders: DashboardOrder[]): BoardColumn[] {
  return BOARD_DEFINITION.map((definition) => ({
    ...definition,
    orders: orders.filter((order) => definition.statuses.includes(order.status)),
  }));
}

export function nextPrimaryOrderAction(order: DashboardOrder): OrderAction | null {
  switch (order.status) {
    case "pending":
      return { label: "Accept", status: "accepted" };
    case "accepted":
      return { label: "Start preparing", status: "preparing" };
    case "preparing":
      return order.fulfillment === "delivery"
        ? { label: "Out for delivery", status: "out_for_delivery" }
        : { label: "Mark ready", status: "ready" };
    case "ready":
    case "out_for_delivery":
      return { label: "Complete", status: "completed" };
    default:
      return null;
  }
}

export function secondaryOrderAction(order: DashboardOrder): OrderAction | null {
  if (order.status === "pending") return { label: "Reject", status: "rejected" };
  if (order.status === "accepted" || order.status === "preparing") {
    return { label: "Cancel", status: "cancelled" };
  }
  return null;
}

export function buildDashboardOverview(orders: DashboardOrder[]): DashboardOverview {
  const completed = orders.filter((order) => order.status === "completed");
  const topItemTotals = new Map<string, number>();

  for (const order of orders) {
    for (const item of order.items) {
      topItemTotals.set(
        item.name_snapshot,
        (topItemTotals.get(item.name_snapshot) ?? 0) + item.quantity,
      );
    }
  }

  return {
    todayOrderCount: orders.length,
    newOrderCount: orders.filter((order) => order.status === "pending").length,
    ordersNeedingAttention: orders.filter((order) => order.status === "pending").length,
    completedSales: completed.reduce((sum, order) => sum + numberValue(order.total), 0),
    completedOrderCount: completed.length,
    topItems: [...topItemTotals.entries()]
      .map(([name, quantity]) => ({ name, quantity }))
      .sort((a, b) => b.quantity - a.quantity)
      .slice(0, 4),
  };
}

async function dashboardRequest<T>({
  path,
  accessToken,
  method = "GET",
  body,
  fetcher = fetch,
}: {
  path: string;
  accessToken: string;
  method?: "GET" | "PATCH";
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
    let message = "Couldn't load the dashboard. Please try again.";
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

export function listDashboardOrders({
  accessToken,
  businessId,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  fetcher?: Fetcher;
}): Promise<DashboardOrder[]> {
  return dashboardRequest<DashboardOrder[]>({
    path: `/businesses/${businessId}/orders?limit=100`,
    accessToken,
    fetcher,
  });
}

export function updateDashboardOrderStatus({
  accessToken,
  businessId,
  orderId,
  status,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  orderId: string;
  status: DashboardOrderStatus;
  fetcher?: Fetcher;
}): Promise<DashboardOrder> {
  return dashboardRequest<DashboardOrder>({
    path: `/businesses/${businessId}/orders/${orderId}/status`,
    method: "PATCH",
    accessToken,
    body: { status },
    fetcher,
  });
}

export function toggleAcceptingOrders({
  accessToken,
  businessId,
  acceptingOrders,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  acceptingOrders: boolean;
  fetcher?: Fetcher;
}): Promise<Business> {
  return dashboardRequest<Business>({
    path: `/businesses/${businessId}`,
    method: "PATCH",
    accessToken,
    body: { accepting_orders: acceptingOrders },
    fetcher,
  });
}

export function updateDashboardBusiness({
  accessToken,
  businessId,
  patch,
  fetcher = fetch,
}: {
  accessToken: string;
  businessId: string;
  patch: Partial<Business>;
  fetcher?: Fetcher;
}): Promise<Business> {
  return dashboardRequest<Business>({
    path: `/businesses/${businessId}`,
    method: "PATCH",
    accessToken,
    body: patch,
    fetcher,
  });
}

/** Display name for the signed-in user: full name, else email, else a neutral fallback. */
export function userDisplayName(
  fullName?: string | null,
  email?: string | null,
): string {
  return fullName?.trim() || email?.trim() || "Your account";
}

/** Up to two uppercase initials from the user's name, falling back to the email. */
export function userInitials(
  fullName?: string | null,
  email?: string | null,
): string {
  const name = fullName?.trim();
  if (name) {
    const initials = name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part.charAt(0))
      .join("");
    if (initials) return initials.toUpperCase();
  }
  const handle = email?.trim();
  return handle ? handle.charAt(0).toUpperCase() : "";
}
