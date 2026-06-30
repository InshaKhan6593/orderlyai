"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BarChart3, Bell, CalendarDays, ChevronRight, Clock, CreditCard } from "lucide-react";
import { toast } from "sonner";

import { DashboardShell } from "@/components/dashboard/dashboard-shell";
import { OrderStatusBadge } from "@/components/dashboard/order-status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError } from "@/lib/auth";
import {
  pickBusinessForOwner,
  saveSelectedBusinessId,
} from "@/lib/business-selection";
import { listBusinesses, type Business } from "@/lib/business-profile";
import {
  buildDashboardOverview,
  formatMoney,
  listDashboardOrders,
  toggleAcceptingOrders,
  type DashboardOrder,
  type DashboardOverview,
} from "@/lib/dashboard";
import { cn } from "@/lib/utils";

function accessTokenFromStorage(): string | null {
  return (
    window.localStorage.getItem("orderly.access_token") ??
    window.sessionStorage.getItem("orderly.access_token")
  );
}

function todayLabel(): string {
  return new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(new Date());
}

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
  tone = "default",
}: {
  icon: typeof CalendarDays;
  label: string;
  value: string;
  detail: string;
  tone?: "default" | "attention";
}) {
  return (
    <Card className="min-h-[100px] rounded-lg py-0 shadow-sm" size="sm">
      <CardContent className="flex h-full items-center gap-4 p-4">
        <span
          className={cn(
            "grid size-10 shrink-0 place-items-center rounded-lg border",
            tone === "attention"
              ? "border-amber-200 bg-amber-50 text-amber-700"
              : "border-border bg-background text-foreground",
          )}
        >
          <Icon className="size-5 stroke-[1.7]" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="mt-1 text-2xl font-semibold tracking-normal text-foreground">
            {value}
          </p>
          <p
            className={cn(
              "mt-1.5 text-sm",
              tone === "attention" ? "text-amber-700" : "text-muted-foreground",
            )}
          >
            {detail}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function RecentOrdersTable({ orders }: { orders: DashboardOrder[] }) {
  const router = useRouter();
  return (
    <Card className="rounded-lg py-0 shadow-sm">
      <CardHeader className="px-5 py-4">
        <CardTitle className="font-heading text-lg">Recent orders</CardTitle>
        <Link
          href="/dashboard/orders"
          className="text-sm font-medium text-primary hover:underline"
        >
          View all orders
          <ChevronRight className="ml-1 inline size-4" aria-hidden="true" />
        </Link>
      </CardHeader>
      <Separator />
      <CardContent className="px-5 py-4">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Order</TableHead>
              <TableHead>Customer</TableHead>
              <TableHead>Total</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-8" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {orders.slice(0, 7).map((order) => (
              <TableRow
                key={order.id}
                onClick={() => router.push(`/dashboard/orders?order=${order.id}`)}
                className="cursor-pointer hover:bg-muted/50"
              >
                <TableCell className="font-semibold">{order.order_code}</TableCell>
                <TableCell>{order.customer.name ?? order.customer.wa_phone}</TableCell>
                <TableCell>Rs {formatMoney(order.total)}</TableCell>
                <TableCell>
                  <OrderStatusBadge status={order.status} />
                </TableCell>
                <TableCell>
                  <ChevronRight className="size-4 text-muted-foreground" />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function TopItemsCard({ overview }: { overview: DashboardOverview }) {
  return (
    <Card className="rounded-lg py-0 shadow-sm">
      <CardHeader className="px-5 py-4">
        <CardTitle className="font-heading text-lg">Top items this week</CardTitle>
      </CardHeader>
      <Separator />
      <CardContent className="flex flex-col gap-0 p-0">
        {overview.topItems.length === 0 ? (
          <p className="px-6 py-6 text-sm text-muted-foreground">
            Top items appear after orders are placed.
          </p>
        ) : (
          overview.topItems.map((item, index) => (
            <div
              key={item.name}
              className="grid min-h-12 grid-cols-[34px_minmax(0,1fr)_auto] items-center gap-3 border-b border-border px-6 last:border-b-0"
            >
              <span className="grid size-7 place-items-center rounded-full border border-primary/15 bg-primary/8 text-sm text-primary">
                {index + 1}
              </span>
              <span className="truncate text-sm font-medium text-foreground">
                {item.name}
              </span>
              <span className="text-sm text-muted-foreground">
                {item.quantity} orders
              </span>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

export function DashboardOverviewPage() {
  const router = useRouter();
  const [accessToken, setAccessToken] = useState("");
  const [business, setBusiness] = useState<Business | null>(null);
  const [orders, setOrders] = useState<DashboardOrder[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const overview = buildDashboardOverview(orders);

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
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          toast.error("Your session has expired. Please sign in again.");
          router.replace("/login");
          return;
        }
        toast.error(error instanceof ApiError ? error.message : "Couldn't load dashboard.");
      } finally {
        if (active) setIsLoading(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [router]);

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

  return (
    <DashboardShell
      active="overview"
      title="Overview"
      business={business}
      pendingCount={overview.newOrderCount}
      acceptingOrders={business?.accepting_orders ?? true}
      onAcceptingOrdersChange={(checked) => void handleAcceptingOrders(checked)}
    >
      {isLoading ? (
        <div className="grid min-h-[520px] place-items-center">
          <Spinner />
        </div>
      ) : (
        <div className="mx-auto flex max-w-[1220px] flex-col gap-4">
          <section>
            <p className="text-sm text-muted-foreground">
              Here&apos;s what&apos;s happening at {business?.name ?? "your business"} today.
            </p>
            <p className="mt-1 text-xs text-muted-foreground">{todayLabel()}</p>
          </section>

          <section className="grid gap-4 lg:grid-cols-4">
            <MetricCard
              icon={CalendarDays}
              label="Today's orders"
              value={String(overview.todayOrderCount)}
              detail={`${overview.newOrderCount} new`}
            />
            <MetricCard
              icon={CreditCard}
              label="Today's sales"
              value={`Rs ${formatMoney(overview.completedSales)}`}
              detail={`From ${overview.completedOrderCount} completed orders`}
            />
            <MetricCard
              icon={Bell}
              label="Orders needing attention"
              value={String(overview.ordersNeedingAttention)}
              detail="Waiting for acceptance"
              tone="attention"
            />
            <MetricCard
              icon={Clock}
              label="Avg prep time"
              value={`${business?.default_prep_minutes ?? 0} min`}
              detail="Today"
            />
          </section>

          {overview.ordersNeedingAttention > 0 ? (
            <Link
              href="/dashboard/orders"
              className="flex min-h-[68px] items-center gap-4 rounded-lg border border-amber-300 bg-amber-50/45 px-5 text-amber-800 hover:bg-amber-50"
            >
              <Bell className="size-5 shrink-0" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="font-semibold">
                  {overview.ordersNeedingAttention} orders need your attention
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Review new orders before they get cold.
                </p>
              </div>
              <ChevronRight className="size-4" aria-hidden="true" />
            </Link>
          ) : null}

          <section className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(360px,1fr)]">
            <RecentOrdersTable orders={orders} />
            <div className="flex flex-col gap-4">
              <TopItemsCard overview={overview} />
              <Card className="min-h-[208px] justify-center rounded-lg py-0 text-center shadow-sm">
                <CardContent className="grid place-items-center gap-3 px-8 py-7">
                  <span className="grid size-10 place-items-center rounded-lg border border-border bg-background">
                    <BarChart3 className="size-6 stroke-[1.7]" aria-hidden="true" />
                  </span>
                  <div>
                    <h3 className="font-heading text-lg font-medium">
                      Analytics coming soon
                    </h3>
                    <p className="mt-2 max-w-[320px] text-sm text-muted-foreground">
                      Trends, comparisons, and date-range reports will appear here.
                    </p>
                  </div>
                  <Button variant="outline" className="mt-1 min-w-[170px]">
                    Coming soon
                  </Button>
                </CardContent>
              </Card>
            </div>
          </section>
        </div>
      )}
    </DashboardShell>
  );
}
