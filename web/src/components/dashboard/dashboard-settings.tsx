"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Clock,
  CreditCard,
  MapPin,
  MessageCircle,
  Sparkles,
  Store,
  Truck,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { DashboardShell } from "@/components/dashboard/dashboard-shell";
import { AIAssistantForm } from "@/components/onboarding/ai-assistant-form";
import { BusinessHoursForm } from "@/components/onboarding/business-hours-form";
import { BusinessProfileForm } from "@/components/onboarding/business-profile-form";
import { FulfillmentForm } from "@/components/onboarding/fulfillment-form";
import { WhatsAppConnectionForm } from "@/components/onboarding/whatsapp-connection-form";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
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
import { cn } from "@/lib/utils";

type TabId =
  | "profile"
  | "hours"
  | "fulfillment"
  | "zones"
  | "assistant"
  | "whatsapp";

type SettingsTab = {
  id: TabId;
  label: string;
  icon: typeof Store;
  title: string;
  subtitle: string;
};

const SETTINGS_TABS: SettingsTab[] = [
  {
    id: "profile",
    label: "Business Profile",
    icon: Store,
    title: "Business Profile",
    subtitle: "Update the information customers and your assistant see.",
  },
  {
    id: "hours",
    label: "Hours",
    icon: Clock,
    title: "Business hours",
    subtitle: "Set when customers can place orders.",
  },
  {
    id: "fulfillment",
    label: "Fulfillment & Delivery",
    icon: Truck,
    title: "Fulfillment & delivery",
    subtitle: "Choose fulfillment options, order settings, and delivery zones.",
  },
  {
    id: "zones",
    label: "Delivery Zones",
    icon: MapPin,
    title: "Delivery zones",
    subtitle: "Manage the areas you deliver to and their fees.",
  },
  {
    id: "assistant",
    label: "AI Assistant",
    icon: Sparkles,
    title: "AI assistant",
    subtitle: "Customize how your assistant replies to customers on WhatsApp.",
  },
  {
    id: "whatsapp",
    label: "WhatsApp",
    icon: MessageCircle,
    title: "WhatsApp connection",
    subtitle: "Connect your Meta WhatsApp number so customers can order.",
  },
];

const DISABLED_TABS = [
  { label: "Plan & Billing", icon: CreditCard },
  { label: "Team", icon: Users },
];

function accessTokenFromStorage(): string | null {
  return (
    window.localStorage.getItem("orderly.access_token") ??
    window.sessionStorage.getItem("orderly.access_token")
  );
}

export function DashboardSettingsPage() {
  const router = useRouter();
  const [accessToken, setAccessToken] = useState("");
  const [business, setBusiness] = useState<Business | null>(null);
  const [orders, setOrders] = useState<DashboardOrder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabId>("profile");

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
        }).catch(() => [] as DashboardOrder[]);
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
        toast.error(error instanceof ApiError ? error.message : "Couldn't load settings.");
      } finally {
        if (active) setIsLoading(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [router]);

  const pendingCount = orders.filter((order) => order.status === "pending").length;

  async function reloadBusiness() {
    const token = accessToken || accessTokenFromStorage();
    if (!token) return;
    try {
      const businesses = await listBusinesses(token);
      const selected = pickBusinessForOwner(businesses);
      if (selected) {
        saveSelectedBusinessId(selected.id);
        setBusiness(selected);
      }
    } catch {
      // Non-fatal: the top bar keeps its previous business snapshot.
    }
  }

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

  const active = SETTINGS_TABS.find((tab) => tab.id === activeTab) ?? SETTINGS_TABS[0];

  function renderActiveTab() {
    switch (activeTab) {
      case "profile":
        return (
          <BusinessProfileForm
            variant="settings"
            onSaved={(updated) => setBusiness(updated)}
          />
        );
      case "hours":
        return <BusinessHoursForm variant="settings" onSaved={reloadBusiness} />;
      case "fulfillment":
      case "zones":
        return <FulfillmentForm variant="settings" onSaved={reloadBusiness} />;
      case "assistant":
        return <AIAssistantForm variant="settings" />;
      case "whatsapp":
        return <WhatsAppConnectionForm variant="settings" />;
      default:
        return null;
    }
  }

  return (
    <DashboardShell
      active="settings"
      title="Settings"
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
        <div className="mx-auto flex max-w-[1220px] flex-col gap-4">
          <section>
            <p className="text-sm text-muted-foreground">
              Manage your business, ordering, and account preferences.
            </p>
          </section>

          <Card className="rounded-lg py-0 shadow-sm">
            <CardContent className="grid min-h-[560px] p-0 lg:grid-cols-[208px_minmax(0,1fr)]">
              <aside className="border-b border-border p-3 lg:border-r lg:border-b-0">
                <nav className="flex flex-col gap-1">
                  {SETTINGS_TABS.map((tab) => {
                    const Icon = tab.icon;
                    const isActive = tab.id === activeTab;
                    return (
                      <button
                        key={tab.id}
                        type="button"
                        onClick={() => setActiveTab(tab.id)}
                        className={cn(
                          "flex h-10 items-center gap-2.5 rounded-lg px-3 text-left text-sm font-medium",
                          isActive
                            ? "bg-primary/8 text-primary"
                            : "text-foreground hover:bg-muted",
                        )}
                      >
                        <Icon className="size-5" aria-hidden="true" />
                        <span className="min-w-0 flex-1 truncate">{tab.label}</span>
                      </button>
                    );
                  })}
                  {DISABLED_TABS.map((tab, index) => {
                    const Icon = tab.icon;
                    return (
                      <button
                        key={tab.label}
                        type="button"
                        disabled
                        className={cn(
                          "flex h-10 items-center gap-2.5 rounded-lg px-3 text-left text-sm font-medium",
                          "cursor-not-allowed text-muted-foreground",
                          index === 0 && "mt-4 border-t border-border pt-5",
                        )}
                      >
                        <Icon className="size-5" aria-hidden="true" />
                        <span className="min-w-0 flex-1 truncate">{tab.label}</span>
                        <Badge variant="secondary">Coming soon</Badge>
                      </button>
                    );
                  })}
                </nav>
              </aside>

              <section className="p-5">
                <div className="mb-5">
                  <h3 className="font-heading text-xl font-medium text-foreground">
                    {active.title}
                  </h3>
                  <p className="mt-1 text-sm text-muted-foreground">{active.subtitle}</p>
                </div>

                {renderActiveTab()}
              </section>
            </CardContent>
          </Card>
        </div>
      )}
    </DashboardShell>
  );
}
