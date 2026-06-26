import { describe, expect, it, vi } from "vitest";

import {
  buildDashboardOverview,
  groupOrdersForBoard,
  listDashboardOrders,
  nextPrimaryOrderAction,
  toggleAcceptingOrders,
  updateDashboardBusiness,
  updateDashboardOrderStatus,
  userDisplayName,
  userInitials,
  type DashboardOrder,
} from "./dashboard";

const baseOrder: DashboardOrder = {
  id: "order-1",
  business_id: "biz-1",
  customer_id: "customer-1",
  order_no: 1024,
  channel: "whatsapp",
  status: "pending",
  fulfillment: "delivery",
  address: "House 18, Block 7",
  zone_id: "zone-1",
  subtotal: "1850.00",
  delivery_fee: "150.00",
  packaging_fee: "50.00",
  total: "2050.00",
  payment_method: "cod",
  payment_status: "unpaid",
  notes: null,
  created_at: "2026-06-20T10:42:00Z",
  customer: {
    id: "customer-1",
    name: "Ayesha Khan",
    wa_phone: "+923001234567",
  },
  zone: {
    id: "zone-1",
    name: "Gulshan",
    fee: "150.00",
    min_order: "0.00",
    eta_minutes: null,
  },
  items: [
    {
      id: "item-1",
      product_id: "product-burger",
      name_snapshot: "Classic Beef Burger",
      price_snapshot: "850.00",
      quantity: 2,
      options_json: [{ name: "Size: Large", price_delta: "250.00" }],
      line_total: "1700.00",
    },
    {
      id: "item-2",
      product_id: "product-coke",
      name_snapshot: "Coke",
      price_snapshot: "150.00",
      quantity: 1,
      options_json: [],
      line_total: "150.00",
    },
  ],
  status_history: [
    {
      id: "history-1",
      status: "pending",
      changed_by: "system",
      created_at: "2026-06-20T10:42:00Z",
    },
  ],
};

function order(patch: Partial<DashboardOrder>): DashboardOrder {
  return { ...baseOrder, ...patch };
}

describe("dashboard order helpers", () => {
  it("groups active orders into the board columns used by the owner dashboard", () => {
    const grouped = groupOrdersForBoard([
      order({ id: "pending", status: "pending" }),
      order({ id: "accepted", status: "accepted" }),
      order({ id: "preparing", status: "preparing" }),
      order({ id: "ready", status: "ready" }),
      order({ id: "out", status: "out_for_delivery" }),
      order({ id: "completed", status: "completed" }),
      order({ id: "cancelled", status: "cancelled" }),
    ]);

    expect(grouped.map((column) => [column.key, column.orders.map((item) => item.id)])).toEqual([
      ["new", ["pending"]],
      ["accepted", ["accepted"]],
      ["preparing", ["preparing"]],
      ["ready_out", ["ready", "out"]],
      ["completed", ["completed"]],
    ]);
  });

  it("maps fulfillment-aware status actions for the board cards and detail drawer", () => {
    expect(nextPrimaryOrderAction(order({ status: "pending" }))).toEqual({
      label: "Accept",
      status: "accepted",
    });
    expect(nextPrimaryOrderAction(order({ status: "accepted" }))).toEqual({
      label: "Start preparing",
      status: "preparing",
    });
    expect(
      nextPrimaryOrderAction(order({ status: "preparing", fulfillment: "delivery" })),
    ).toEqual({ label: "Out for delivery", status: "out_for_delivery" });
    expect(
      nextPrimaryOrderAction(order({ status: "preparing", fulfillment: "pickup" })),
    ).toEqual({ label: "Mark ready", status: "ready" });
    expect(nextPrimaryOrderAction(order({ status: "out_for_delivery" }))).toEqual({
      label: "Complete",
      status: "completed",
    });
    expect(nextPrimaryOrderAction(order({ status: "completed" }))).toBeNull();
  });

  it("builds overview metrics and top items from fetched orders", () => {
    const overview = buildDashboardOverview([
      baseOrder,
      order({
        id: "accepted",
        order_no: 1023,
        status: "accepted",
        total: "1150.00",
        created_at: "2026-06-20T11:00:00Z",
      }),
      order({
        id: "completed",
        order_no: 1022,
        status: "completed",
        total: "900.00",
        created_at: "2026-06-20T12:00:00Z",
        items: [
          {
            ...baseOrder.items[0],
            id: "completed-item",
            name_snapshot: "Classic Beef Burger",
            quantity: 1,
          },
        ],
      }),
    ]);

    expect(overview.todayOrderCount).toBe(3);
    expect(overview.newOrderCount).toBe(1);
    expect(overview.ordersNeedingAttention).toBe(1);
    expect(overview.completedSales).toBe(900);
    expect(overview.completedOrderCount).toBe(1);
    expect(overview.topItems[0]).toEqual({
      name: "Classic Beef Burger",
      quantity: 5,
    });
  });
});

describe("dashboard user identity helpers", () => {
  it("derives a display name with sensible fallbacks", () => {
    expect(userDisplayName("Insha Khan", "demo@orderlyai.dev")).toBe("Insha Khan");
    expect(userDisplayName(null, "demo@orderlyai.dev")).toBe("demo@orderlyai.dev");
    expect(userDisplayName("   ", null)).toBe("Your account");
    expect(userDisplayName(undefined, undefined)).toBe("Your account");
  });

  it("builds up to two initials, falling back to the email", () => {
    expect(userInitials("Insha Khan", "demo@orderlyai.dev")).toBe("IK");
    expect(userInitials("lorenzo", "owner@lorenzo.test")).toBe("L");
    expect(userInitials("  ", "demo@orderlyai.dev")).toBe("D");
    expect(userInitials(null, null)).toBe("");
  });
});

describe("dashboard API helpers", () => {
  it("uses tenant-scoped order endpoints for list and status updates", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify([baseOrder]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ...baseOrder, status: "accepted" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

    await expect(
      listDashboardOrders({
        accessToken: "token",
        businessId: "biz-1",
        fetcher,
      }),
    ).resolves.toHaveLength(1);
    await updateDashboardOrderStatus({
      accessToken: "token",
      businessId: "biz-1",
      orderId: "order-1",
      status: "accepted",
      fetcher,
    });

    expect(fetcher).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/api/v1/businesses/biz-1/orders?limit=100",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer token" }),
      }),
    );
    expect(fetcher).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/businesses/biz-1/orders/order-1/status",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ status: "accepted" }),
      }),
    );
  });

  it("patches accepting_orders through the existing business endpoint", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "biz-1", accepting_orders: false }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await toggleAcceptingOrders({
      accessToken: "token",
      businessId: "biz-1",
      acceptingOrders: false,
      fetcher,
    });

    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/businesses/biz-1",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ accepting_orders: false }),
      }),
    );
  });

  it("patches dashboard business profile fields through the existing business endpoint", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "biz-1", name: "The Green Bistro" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await updateDashboardBusiness({
      accessToken: "token",
      businessId: "biz-1",
      patch: {
        name: "The Green Bistro",
        description: "Fresh comfort food.",
        helpline_phone: "+92 3001234567",
      },
      fetcher,
    });

    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/businesses/biz-1",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          name: "The Green Bistro",
          description: "Fresh comfort food.",
          helpline_phone: "+92 3001234567",
        }),
      }),
    );
  });
});
