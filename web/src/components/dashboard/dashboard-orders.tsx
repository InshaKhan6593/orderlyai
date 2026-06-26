"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Bell,
  CalendarDays,
  Grid2X2,
  List,
  MessageCircle,
  Search,
  ShoppingBag,
  Volume2,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { DashboardShell } from "@/components/dashboard/dashboard-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { ApiError } from "@/lib/auth";
import {
  pickBusinessForOwner,
  saveSelectedBusinessId,
} from "@/lib/business-selection";
import { listBusinesses, type Business } from "@/lib/business-profile";
import {
  formatMoney,
  groupOrdersForBoard,
  listDashboardOrders,
  nextPrimaryOrderAction,
  secondaryOrderAction,
  statusLabel,
  toggleAcceptingOrders,
  updateDashboardOrderStatus,
  type BoardColumn,
  type DashboardOrder,
  type DashboardOrderStatus,
} from "@/lib/dashboard";
import { cn } from "@/lib/utils";

function accessTokenFromStorage(): string | null {
  return (
    window.localStorage.getItem("orderly.access_token") ??
    window.sessionStorage.getItem("orderly.access_token")
  );
}

function timeAgo(value: string): string {
  const then = new Date(value).getTime();
  const diffMs = Date.now() - then;
  const minutes = Math.max(1, Math.round(diffMs / 60000));
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  return `${hours} hr ago`;
}

function statusBadgeClass(status: DashboardOrderStatus): string {
  switch (status) {
    case "pending":
      return "border-primary/25 bg-primary/10 text-primary";
    case "accepted":
      return "border-blue-300 bg-blue-50 text-blue-700";
    case "preparing":
      return "border-amber-300 bg-amber-50 text-amber-700";
    case "ready":
    case "out_for_delivery":
      return "border-violet-300 bg-violet-50 text-violet-700";
    case "completed":
      return "border-primary/25 bg-primary/10 text-primary";
    default:
      return "border-border bg-muted text-muted-foreground";
  }
}

function paymentBadge(order: DashboardOrder) {
  if (order.payment_status === "paid" || order.payment_method === "paid") {
    return { label: "Paid", className: "border-primary/25 bg-primary/10 text-primary" };
  }
  if (order.payment_method === "cod") {
    return { label: "COD", className: "border-amber-300 bg-amber-50 text-amber-700" };
  }
  return { label: "Link", className: "border-blue-300 bg-blue-50 text-blue-700" };
}

function fulfillmentBadge(order: DashboardOrder) {
  if (order.fulfillment === "pickup") {
    return {
      label: "Pickup",
      className: "border-blue-300 bg-blue-50 text-blue-700",
    };
  }
  return {
    label: `Delivery${order.zone?.name ? ` - ${order.zone.name}` : ""}`,
    className: "border-primary/25 bg-primary/10 text-primary",
  };
}

function itemSummary(order: DashboardOrder): string {
  return order.items
    .slice(0, 2)
    .map((item) => `${item.quantity}x ${item.name_snapshot}`)
    .join(", ");
}

function OrderCard({
  order,
  selected,
  onSelect,
  onAdvance,
}: {
  order: DashboardOrder;
  selected: boolean;
  onSelect: () => void;
  onAdvance: (status: DashboardOrderStatus) => void;
}) {
  const primary = nextPrimaryOrderAction(order);
  const secondary = secondaryOrderAction(order);
  const payment = paymentBadge(order);
  const fulfillment = fulfillmentBadge(order);

  return (
    <article
      className={cn(
        "rounded-lg border bg-card p-3 shadow-sm transition-colors",
        selected ? "border-primary ring-1 ring-primary/30" : "border-border",
      )}
    >
      <button type="button" className="block w-full text-left" onClick={onSelect}>
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-semibold text-foreground">#{order.order_no}</p>
            <p className="mt-2 text-sm text-foreground">
              {order.customer.name ?? order.customer.wa_phone}
            </p>
          </div>
          <span className="text-xs text-muted-foreground">{timeAgo(order.created_at)}</span>
        </div>
        <Badge variant="outline" className={cn("mt-2", fulfillment.className)}>
          {fulfillment.label}
        </Badge>
        <p className="mt-3 line-clamp-2 text-sm leading-5 text-muted-foreground">
          {itemSummary(order)}
        </p>
        <div className="mt-4 flex items-center justify-between gap-3">
          <p className="font-semibold text-foreground">Rs {formatMoney(order.total)}</p>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className={payment.className}>
              {payment.label}
            </Badge>
            <MessageCircle className="size-4 text-muted-foreground" aria-hidden="true" />
          </div>
        </div>
      </button>

      {primary ? (
        <div className="mt-4 flex flex-col gap-2">
          <Button type="button" className="h-9 w-full" onClick={() => onAdvance(primary.status)}>
            {primary.label}
          </Button>
          {secondary ? (
            <Button
              type="button"
              variant="destructive"
              className="h-9 w-full border border-destructive/70 bg-background"
              onClick={() => onAdvance(secondary.status)}
            >
              {secondary.label}
            </Button>
          ) : null}
        </div>
      ) : (
        <Badge variant="outline" className={cn("mt-4", statusBadgeClass(order.status))}>
          {statusLabel(order.status)}
        </Badge>
      )}
    </article>
  );
}

function BoardColumnView({
  column,
  selectedOrderId,
  onSelect,
  onAdvance,
}: {
  column: BoardColumn;
  selectedOrderId?: string;
  onSelect: (order: DashboardOrder) => void;
  onAdvance: (order: DashboardOrder, status: DashboardOrderStatus) => void;
}) {
  return (
    <section className="min-h-[650px] rounded-lg border border-border bg-background">
      <div className="flex h-[56px] items-center gap-2 border-b border-border px-4">
        <h3 className="font-semibold text-foreground">{column.title}</h3>
        <span className="grid size-6 place-items-center rounded-full border border-primary/25 bg-primary/8 text-sm text-primary">
          {column.orders.length}
        </span>
      </div>
      <div className="flex flex-col gap-3 p-3">
        {column.orders.map((order) => (
          <OrderCard
            key={order.id}
            order={order}
            selected={selectedOrderId === order.id}
            onSelect={() => onSelect(order)}
            onAdvance={(status) => onAdvance(order, status)}
          />
        ))}
      </div>
    </section>
  );
}

function OrderDetail({
  order,
  onClose,
  onAdvance,
}: {
  order: DashboardOrder | null;
  onClose: () => void;
  onAdvance: (order: DashboardOrder, status: DashboardOrderStatus) => void;
}) {
  if (!order) {
    return (
      <aside className="hidden border-l border-border bg-card xl:grid xl:place-items-center">
        <div className="px-8 text-center">
          <ShoppingBag className="mx-auto size-10 text-muted-foreground" />
          <p className="mt-3 font-medium text-foreground">Select an order</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Order details and actions will appear here.
          </p>
        </div>
      </aside>
    );
  }

  const primary = nextPrimaryOrderAction(order);
  const secondary = secondaryOrderAction(order);
  const fulfillment = fulfillmentBadge(order);

  return (
    <aside className="border-l border-border bg-card xl:min-h-[calc(100vh-64px)]">
      <div className="sticky top-16 flex max-h-[calc(100vh-64px)] flex-col overflow-y-auto">
        <div className="flex min-h-[70px] items-center gap-3 border-b border-border px-5">
          <h2 className="font-heading text-xl font-medium text-foreground">
            Order #{order.order_no}
          </h2>
          <Badge variant="outline" className={statusBadgeClass(order.status)}>
            {statusLabel(order.status)}
          </Badge>
          <Badge variant="outline" className={fulfillment.className}>
            {fulfillment.label}
          </Badge>
          <button
            type="button"
            className="ml-auto grid size-8 place-items-center rounded-lg hover:bg-muted"
            onClick={onClose}
            aria-label="Close order detail"
          >
            <X className="size-5" />
          </button>
        </div>

        <div className="flex flex-col gap-5 p-5">
          <section>
            <h3 className="text-base font-semibold text-foreground">Items</h3>
            <div className="mt-3 flex flex-col gap-4">
              {order.items.map((item) => (
                <div key={item.id}>
                  <div className="flex items-start justify-between gap-4 text-sm">
                    <p>
                      {item.quantity}x {item.name_snapshot}
                    </p>
                    <p className="shrink-0">Rs {formatMoney(item.line_total)}</p>
                  </div>
                  {item.options_json.length > 0 ? (
                    <ul className="mt-2 flex flex-col gap-1 pl-5 text-sm text-muted-foreground">
                      {item.options_json.map((option, index) => (
                        <li key={`${item.id}-${index}`} className="flex justify-between gap-3">
                          <span>{option.name ?? "Option"}</span>
                          <span>+Rs {formatMoney(option.price_delta ?? 0)}</span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ))}
            </div>
          </section>

          <Separator />

          <section className="flex flex-col gap-2 text-sm">
            <div className="flex justify-between gap-3">
              <span>Subtotal</span>
              <span>Rs {formatMoney(order.subtotal)}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span>Delivery fee</span>
              <span>Rs {formatMoney(order.delivery_fee)}</span>
            </div>
            <div className="flex justify-between gap-3">
              <span>Packaging fee</span>
              <span>Rs {formatMoney(order.packaging_fee)}</span>
            </div>
            <Separator className="my-1" />
            <div className="flex justify-between gap-3 text-base font-semibold">
              <span>Total</span>
              <span>Rs {formatMoney(order.total)}</span>
            </div>
          </section>

          <Separator />

          <section>
            <h3 className="text-base font-semibold text-foreground">Customer</h3>
            <p className="mt-2 text-sm text-foreground">
              {order.customer.name ?? "WhatsApp customer"}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">{order.customer.wa_phone}</p>
            <Button variant="outline" className="mt-3 h-8">
              <MessageCircle data-icon="inline-start" />
              Message on WhatsApp
            </Button>
          </section>

          <Separator />

          <section>
            <h3 className="text-base font-semibold text-foreground">Fulfillment</h3>
            {order.fulfillment === "delivery" ? (
              <div className="mt-2 text-sm">
                <p className="font-medium text-primary">Delivery address</p>
                <p className="mt-1 text-muted-foreground">{order.address ?? "No address"}</p>
                <p className="mt-1 text-muted-foreground">
                  Zone: {order.zone?.name ?? "Not assigned"}
                </p>
              </div>
            ) : (
              <p className="mt-2 text-sm text-muted-foreground">
                Customer will pick this order up.
              </p>
            )}
          </section>

          <Separator />

          <section>
            <h3 className="text-base font-semibold text-foreground">Payment</h3>
            <div className="mt-2 flex items-center gap-2 text-sm">
              <span>{order.payment_method === "cod" ? "Cash on delivery" : "Payment link"}</span>
              <Badge variant="outline" className={paymentBadge(order).className}>
                {order.payment_status === "paid" ? "Paid" : "Pending"}
              </Badge>
            </div>
          </section>

          <Separator />

          <section>
            <h3 className="text-base font-semibold text-foreground">Order timeline</h3>
            <div className="mt-3 flex flex-col gap-3">
              {order.status_history.map((entry) => (
                <div key={entry.id} className="grid grid-cols-[12px_minmax(0,1fr)] gap-3">
                  <span className="mt-1 size-2.5 rounded-full bg-primary" />
                  <p className="text-sm text-muted-foreground">
                    {statusLabel(entry.status)} -{" "}
                    {new Intl.DateTimeFormat("en-US", {
                      hour: "numeric",
                      minute: "2-digit",
                    }).format(new Date(entry.created_at))}
                  </p>
                </div>
              ))}
            </div>
          </section>
        </div>

        {primary || secondary ? (
          <div className="mt-auto grid grid-cols-2 gap-4 border-t border-border p-5">
            {primary ? (
              <Button className="h-12" onClick={() => onAdvance(order, primary.status)}>
                {primary.label === "Accept" ? "Accept order" : primary.label}
              </Button>
            ) : null}
            {secondary ? (
              <Button
                variant="destructive"
                className="h-12 border border-destructive/70 bg-background"
                onClick={() => onAdvance(order, secondary.status)}
              >
                {secondary.label}
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </aside>
  );
}

export function DashboardOrdersPage() {
  const router = useRouter();
  const [accessToken, setAccessToken] = useState("");
  const [business, setBusiness] = useState<Business | null>(null);
  const [orders, setOrders] = useState<DashboardOrder[]>([]);
  const [selectedOrderId, setSelectedOrderId] = useState<string>();
  const [search, setSearch] = useState("");
  const [fulfillment, setFulfillment] = useState("all");
  const [isLoading, setIsLoading] = useState(true);
  const [updatingOrderId, setUpdatingOrderId] = useState<string | null>(null);

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
        const loadedOrders = await listDashboardOrders({
          accessToken: token,
          businessId: selected.id,
        });
        if (!active) return;
        setAccessToken(token);
        setBusiness(selected);
        setOrders(loadedOrders);
        setSelectedOrderId(loadedOrders[0]?.id);
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          toast.error("Your session has expired. Please sign in again.");
          router.replace("/login");
          return;
        }
        toast.error(error instanceof ApiError ? error.message : "Couldn't load orders.");
      } finally {
        if (active) setIsLoading(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [router]);

  const pendingCount = orders.filter((order) => order.status === "pending").length;
  const filteredOrders = useMemo(() => {
    const query = search.trim().toLowerCase();
    return orders.filter((order) => {
      const matchesFulfillment = fulfillment === "all" || order.fulfillment === fulfillment;
      const matchesQuery =
        !query ||
        String(order.order_no).includes(query) ||
        (order.customer.name ?? "").toLowerCase().includes(query) ||
        order.customer.wa_phone.toLowerCase().includes(query);
      return matchesFulfillment && matchesQuery;
    });
  }, [fulfillment, orders, search]);
  const columns = groupOrdersForBoard(filteredOrders);
  const selectedOrder =
    orders.find((order) => order.id === selectedOrderId) ?? filteredOrders[0] ?? null;

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

  async function handleAdvance(order: DashboardOrder, status: DashboardOrderStatus) {
    if (!accessToken || !business || updatingOrderId) return;
    setUpdatingOrderId(order.id);
    try {
      const updated = await updateDashboardOrderStatus({
        accessToken,
        businessId: business.id,
        orderId: order.id,
        status,
      });
      setOrders((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setSelectedOrderId(updated.id);
      toast.success(`Order #${updated.order_no} updated.`);
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : "Couldn't update this order.",
      );
    } finally {
      setUpdatingOrderId(null);
    }
  }

  return (
    <DashboardShell
      active="orders"
      title="Orders"
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
        <div className="grid gap-0 xl:grid-cols-[minmax(0,1fr)_392px]">
          <div className="min-w-0 pr-0 xl:pr-6">
            <div className="mb-5 flex flex-wrap items-center gap-3">
              <Button variant="outline" className="h-11 min-w-[140px] justify-between">
                <CalendarDays data-icon="inline-start" />
                Today
              </Button>
              <Select value={fulfillment} onValueChange={(value) => setFulfillment(value ?? "all")}>
                <SelectTrigger className="h-11 w-[190px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent alignItemWithTrigger={false}>
                  <SelectGroup>
                    <SelectItem value="all">All fulfillment</SelectItem>
                    <SelectItem value="delivery">Delivery</SelectItem>
                    <SelectItem value="pickup">Pickup</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
              <div className="relative min-w-[260px] flex-1 max-w-[320px]">
                <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search orders..."
                  className="h-11 pl-9"
                />
              </div>
              <div className="ml-auto flex items-center gap-2">
                <Button variant="outline" size="icon-lg" aria-label="Board view">
                  <Grid2X2 />
                </Button>
                <Button variant="outline" size="icon-lg" aria-label="List view">
                  <List />
                </Button>
                <Button variant="outline" className="h-11">
                  <Volume2 data-icon="inline-start" />
                  Sound on
                </Button>
              </div>
            </div>

            <div className="grid gap-3 lg:grid-cols-5">
              {columns.map((column) => (
                <BoardColumnView
                  key={column.key}
                  column={column}
                  selectedOrderId={selectedOrder?.id}
                  onSelect={(order) => setSelectedOrderId(order.id)}
                  onAdvance={(order, status) => void handleAdvance(order, status)}
                />
              ))}
            </div>

            {filteredOrders.length === 0 ? (
              <Card className="mt-4 rounded-lg py-0">
                <CardContent className="grid min-h-[180px] place-items-center p-6 text-center">
                  <div>
                    <Bell className="mx-auto size-8 text-muted-foreground" />
                    <p className="mt-3 font-medium text-foreground">No orders found</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      New WhatsApp orders will appear here.
                    </p>
                  </div>
                </CardContent>
              </Card>
            ) : null}
          </div>
          <OrderDetail
            order={selectedOrder}
            onClose={() => setSelectedOrderId(undefined)}
            onAdvance={(order, status) => void handleAdvance(order, status)}
          />
        </div>
      )}
    </DashboardShell>
  );
}
