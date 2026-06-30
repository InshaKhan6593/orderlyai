"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import {
  Bell,
  BookOpen,
  ChevronDown,
  ClipboardList,
  Home,
  MoreVertical,
  Settings,
  Store,
  Users,
} from "lucide-react";

import { Logo } from "@/components/brand/logo";
import { Switch } from "@/components/ui/switch";
import {
  getCurrentUser,
  readAccessToken,
  type CurrentUserProfile,
} from "@/lib/auth";
import type { Business } from "@/lib/business-profile";
import { userDisplayName, userInitials } from "@/lib/dashboard";
import { cn } from "@/lib/utils";

type DashboardSection = "overview" | "orders" | "menu" | "customers" | "settings";

type DashboardShellProps = {
  active: DashboardSection;
  title: string;
  business: Business | null;
  pendingCount?: number;
  acceptingOrders: boolean;
  onAcceptingOrdersChange?: (checked: boolean) => void;
  children: ReactNode;
};

const NAV_ITEMS = [
  { key: "overview", label: "Overview", href: "/dashboard", icon: Home },
  { key: "orders", label: "Orders", href: "/dashboard/orders", icon: ClipboardList },
  { key: "menu", label: "Menu", href: "/dashboard/menu", icon: BookOpen },
  { key: "customers", label: "Customers", href: "/dashboard/customers", icon: Users },
  { key: "settings", label: "Settings", href: "/dashboard/settings", icon: Settings },
] satisfies {
  key: DashboardSection;
  label: string;
  href: string;
  icon: typeof Home;
}[];

function businessTypeLabel(type?: Business["type"]): string {
  switch (type) {
    case "cafe":
      return "Cafe";
    case "bakery":
      return "Bakery";
    case "home_kitchen":
      return "Home kitchen";
    case "other":
      return "Food business";
    default:
      return "Restaurant";
  }
}

export function DashboardShell({
  active,
  title,
  business,
  pendingCount = 0,
  acceptingOrders,
  onAcceptingOrdersChange,
  children,
}: DashboardShellProps) {
  const [user, setUser] = useState<CurrentUserProfile | null>(null);

  useEffect(() => {
    const token = readAccessToken();
    if (!token) return;
    let active = true;
    getCurrentUser(token)
      .then((profile) => {
        if (active) setUser(profile);
      })
      .catch(() => {
        // Non-fatal: the dashboard still renders without the profile chip.
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground lg:grid lg:grid-cols-[244px_minmax(0,1fr)]">
      <aside className="hidden border-r border-border bg-sidebar lg:flex lg:min-h-screen lg:flex-col">
        <div className="flex h-16 items-center px-5">
          <Logo size="md" />
        </div>

        <nav className="flex flex-1 flex-col gap-1 px-3 py-4">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const selected = item.key === active;
            const count = item.key === "orders" ? pendingCount : 0;
            return (
              <Link
                key={item.key}
                href={item.href}
                className={cn(
                  "flex h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors",
                  selected
                    ? "bg-primary/8 text-primary"
                    : "text-foreground hover:bg-muted",
                )}
              >
                <Icon className="size-5 stroke-[1.8]" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate">{item.label}</span>
                {count > 0 ? (
                  <span className="grid size-6 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
                    {count}
                  </span>
                ) : null}
              </Link>
            );
          })}
        </nav>

        <div className="flex flex-col gap-2 p-3">
          <div className="flex min-h-[56px] items-center gap-2.5 rounded-lg border border-border bg-card px-2.5">
            <span className="grid size-9 place-items-center rounded-md border border-border bg-primary/8 text-primary">
              <Store className="size-5" aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-foreground">
                {business?.name ?? "Your business"}
              </p>
              <p className="text-xs text-muted-foreground">
                {businessTypeLabel(business?.type)}
              </p>
            </div>
            <ChevronDown className="size-4 text-muted-foreground" aria-hidden="true" />
          </div>

          <div className="flex min-h-[56px] items-center gap-2.5 rounded-lg border border-border bg-card px-2.5">
            <span className="grid size-9 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
              {userInitials(user?.full_name, user?.email)}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-foreground">
                {userDisplayName(user?.full_name, user?.email)}
              </p>
              <p className="text-xs text-muted-foreground">Owner</p>
            </div>
            <MoreVertical className="size-4 text-muted-foreground" aria-hidden="true" />
          </div>
        </div>
      </aside>

      <section className="min-w-0">
        <header className="sticky top-0 z-20 flex h-16 items-center border-b border-border bg-background/95 px-4 backdrop-blur sm:px-6">
          <h1 className="hidden font-heading text-xl leading-none font-medium text-foreground md:block">
            {title}
          </h1>
          <Logo className="md:hidden" size="sm" />

          <div className="ml-auto flex items-center gap-4">
            <label className="hidden items-center gap-3 text-sm font-medium text-foreground sm:flex">
              Accepting orders
              <Switch
                size="lg"
                checked={acceptingOrders}
                onCheckedChange={onAcceptingOrdersChange}
                aria-label="Accepting orders"
              />
            </label>
            <span className="h-8 w-px bg-border" aria-hidden="true" />
            <button
              type="button"
              className="relative grid size-9 place-items-center rounded-lg text-foreground hover:bg-muted"
              aria-label="Notifications"
            >
              <Bell className="size-5" aria-hidden="true" />
              {pendingCount > 0 ? (
                <span className="absolute -top-1 -right-1 grid size-5 place-items-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">
                  {pendingCount}
                </span>
              ) : null}
            </button>
            <span className="h-8 w-px bg-border" aria-hidden="true" />
            <div className="flex items-center gap-3">
              <span className="grid size-9 place-items-center rounded-md border border-border bg-primary/8 text-primary">
                <Store className="size-5" aria-hidden="true" />
              </span>
              <span className="hidden text-sm font-medium text-foreground sm:inline">
                {business?.name ?? "Business"}
              </span>
              <ChevronDown className="size-4 text-muted-foreground" aria-hidden="true" />
            </div>
          </div>
        </header>

        <main className="min-h-[calc(100vh-64px)] px-4 py-6 sm:px-8">
          {children}
        </main>
      </section>
    </div>
  );
}
