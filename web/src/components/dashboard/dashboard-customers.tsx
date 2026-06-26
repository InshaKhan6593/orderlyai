"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { MessageCircle, Users } from "lucide-react";
import { toast } from "sonner";

import { DashboardShell } from "@/components/dashboard/dashboard-shell";
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
  listDashboardOrders,
  toggleAcceptingOrders,
  type DashboardOrder,
} from "@/lib/dashboard";

function accessTokenFromStorage(): string | null {
  return (
    window.localStorage.getItem("orderly.access_token") ??
    window.sessionStorage.getItem("orderly.access_token")
  );
}

export function DashboardCustomersPage() {
  const router = useRouter();
  const [accessToken, setAccessToken] = useState("");
  const [business, setBusiness] = useState<Business | null>(null);
  const [orders, setOrders] = useState<DashboardOrder[]>([]);
  const [isLoading, setIsLoading] = useState(true);

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
        toast.error(error instanceof ApiError ? error.message : "Couldn't load customers.");
      } finally {
        if (active) setIsLoading(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [router]);

  const pendingCount = orders.filter((order) => order.status === "pending").length;
  const customers = useMemo(() => {
    const byId = new Map<
      string,
      { name: string; phone: string; orderCount: number; lastOrderAt: string }
    >();
    for (const order of orders) {
      const current = byId.get(order.customer.id);
      byId.set(order.customer.id, {
        name: order.customer.name ?? "WhatsApp customer",
        phone: order.customer.wa_phone,
        orderCount: (current?.orderCount ?? 0) + 1,
        lastOrderAt:
          !current || new Date(order.created_at) > new Date(current.lastOrderAt)
            ? order.created_at
            : current.lastOrderAt,
      });
    }
    return [...byId.values()].sort(
      (a, b) => new Date(b.lastOrderAt).getTime() - new Date(a.lastOrderAt).getTime(),
    );
  }, [orders]);

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
      active="customers"
      title="Customers"
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
        <div className="mx-auto flex max-w-[960px] flex-col gap-4">
          <section>
            <p className="text-sm text-muted-foreground">
              Customer history collected from WhatsApp orders.
            </p>
          </section>
          <Card className="rounded-lg py-0 shadow-sm">
            <CardHeader className="px-5 py-4">
              <CardTitle className="font-heading text-lg">Recent customers</CardTitle>
            </CardHeader>
            <Separator />
            <CardContent className="p-5">
              {customers.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Phone</TableHead>
                      <TableHead>Orders</TableHead>
                      <TableHead className="w-28">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {customers.map((customer) => (
                      <TableRow key={customer.phone}>
                        <TableCell className="font-medium">{customer.name}</TableCell>
                        <TableCell>{customer.phone}</TableCell>
                        <TableCell>{customer.orderCount}</TableCell>
                        <TableCell>
                          <Button variant="outline" size="sm">
                            <MessageCircle data-icon="inline-start" />
                            Message
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <div className="grid min-h-[260px] place-items-center text-center">
                  <div>
                    <Users className="mx-auto size-10 text-muted-foreground" />
                    <p className="mt-3 font-medium text-foreground">No customers yet</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Customers appear after their first order.
                    </p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </DashboardShell>
  );
}
