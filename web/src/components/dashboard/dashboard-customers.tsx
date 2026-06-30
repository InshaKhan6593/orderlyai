"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, Users } from "lucide-react";
import { toast } from "sonner";

import { WhatsAppIcon } from "@/components/brand/whatsapp-icon";
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
  listDashboardCustomers,
  listDashboardOrders,
  toggleAcceptingOrders,
  type DashboardCustomer,
} from "@/lib/dashboard";

const PAGE_SIZE = 10;

function accessTokenFromStorage(): string | null {
  return (
    window.localStorage.getItem("orderly.access_token") ??
    window.sessionStorage.getItem("orderly.access_token")
  );
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

/** Page numbers to render, collapsing long runs with an ellipsis so the jump bar stays compact. */
function pageItems(current: number, total: number): (number | "ellipsis")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const items: (number | "ellipsis")[] = [1];
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  if (start > 2) items.push("ellipsis");
  for (let p = start; p <= end; p += 1) items.push(p);
  if (end < total - 1) items.push("ellipsis");
  items.push(total);
  return items;
}

export function DashboardCustomersPage() {
  const router = useRouter();
  const [accessToken, setAccessToken] = useState("");
  const [business, setBusiness] = useState<Business | null>(null);
  const [customers, setCustomers] = useState<DashboardCustomer[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [page, setPage] = useState(1);
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
        const [loadedCustomers, loadedOrders] = await Promise.all([
          listDashboardCustomers({ accessToken: token, businessId: selected.id }),
          listDashboardOrders({ accessToken: token, businessId: selected.id }),
        ]);
        if (!active) return;
        setAccessToken(token);
        setBusiness(selected);
        setCustomers(loadedCustomers);
        setPendingCount(loadedOrders.filter((order) => order.status === "pending").length);
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

  const pageCount = Math.max(1, Math.ceil(customers.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const visible = useMemo(
    () => customers.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE),
    [customers, currentPage],
  );

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
        <div className="mx-auto flex max-w-[1100px] flex-col gap-4">
          <section>
            <p className="text-sm text-muted-foreground">
              Customer history collected from WhatsApp orders.
            </p>
          </section>
          <Card className="rounded-lg py-0 shadow-sm">
            <CardHeader className="flex-row items-center justify-between px-5 py-4">
              <CardTitle className="font-heading text-lg">Recent customers</CardTitle>
              {customers.length > 0 ? (
                <span className="text-sm text-muted-foreground">{customers.length} total</span>
              ) : null}
            </CardHeader>
            <Separator />
            <CardContent className="p-5">
              {customers.length > 0 ? (
                <>
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Name</TableHead>
                          <TableHead>Phone</TableHead>
                          <TableHead>Email</TableHead>
                          <TableHead>Orders</TableHead>
                          <TableHead>Last order</TableHead>
                          <TableHead className="w-28">Action</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {visible.map((customer) => (
                          <TableRow key={customer.id}>
                            <TableCell className="font-medium">
                              {customer.name ?? "WhatsApp customer"}
                            </TableCell>
                            <TableCell className="whitespace-nowrap">{customer.wa_phone}</TableCell>
                            <TableCell className="text-muted-foreground">
                              {customer.email ?? "—"}
                            </TableCell>
                            <TableCell>{customer.order_count}</TableCell>
                            <TableCell className="whitespace-nowrap text-muted-foreground">
                              {formatDate(customer.last_order_at)}
                            </TableCell>
                            <TableCell>
                              <Button variant="outline" size="sm">
                                <WhatsAppIcon data-icon="inline-start" />
                                Message
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>

                  {pageCount > 1 ? (
                    <nav
                      className="mt-4 flex items-center justify-between gap-2"
                      aria-label="Customers pagination"
                    >
                      <p className="text-sm text-muted-foreground">
                        Page {currentPage} of {pageCount}
                      </p>
                      <div className="flex items-center gap-1">
                        <Button
                          type="button"
                          variant="outline"
                          size="icon-sm"
                          onClick={() => setPage((p) => Math.max(1, p - 1))}
                          disabled={currentPage === 1}
                          aria-label="Previous page"
                        >
                          <ChevronLeft />
                        </Button>
                        {pageItems(currentPage, pageCount).map((item, index) =>
                          item === "ellipsis" ? (
                            <span
                              key={`ellipsis-${index}`}
                              className="px-1.5 text-sm text-muted-foreground"
                              aria-hidden="true"
                            >
                              …
                            </span>
                          ) : (
                            <Button
                              key={item}
                              type="button"
                              variant={item === currentPage ? "default" : "outline"}
                              size="icon-sm"
                              onClick={() => setPage(item)}
                              aria-label={`Page ${item}`}
                              aria-current={item === currentPage ? "page" : undefined}
                            >
                              {item}
                            </Button>
                          ),
                        )}
                        <Button
                          type="button"
                          variant="outline"
                          size="icon-sm"
                          onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                          disabled={currentPage === pageCount}
                          aria-label="Next page"
                        >
                          <ChevronRight />
                        </Button>
                      </div>
                    </nav>
                  ) : null}
                </>
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
