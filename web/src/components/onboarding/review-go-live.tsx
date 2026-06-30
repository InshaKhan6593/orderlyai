"use client";

import { useEffect, useState, type ComponentType, type SVGProps } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Bot,
  Check,
  Clock,
  Store,
  Truck,
  UtensilsCrossed,
} from "lucide-react";
import { toast } from "sonner";

import { WhatsAppIcon } from "@/components/brand/whatsapp-icon";
import { OnboardingShell } from "@/components/onboarding/onboarding-shell";
import {
  ONBOARDING_MAIN_CLASS_NAME,
  OnboardingCard,
  OnboardingStepHeader,
} from "@/components/onboarding/onboarding-step-ui";
import { WelcomeIllustration } from "@/components/onboarding/welcome-illustration";
import { Button } from "@/components/ui/button";
import { CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { getAgentConfig } from "@/lib/ai-assistant";
import { ApiError, clearTokens } from "@/lib/auth";
import {
  pickBusinessForOwner,
  saveSelectedBusinessId,
} from "@/lib/business-selection";
import {
  goLiveBusiness,
  listBusinesses,
  type Business,
} from "@/lib/business-profile";
import { listDeliveryZones } from "@/lib/fulfillment";
import { listCategories, listProducts } from "@/lib/menu";
import {
  ONBOARDING_RESUME_STORAGE_KEY,
  saveOnboardingResumePath,
} from "@/lib/onboarding-progress";
import {
  getWhatsAppConnection,
  type WhatsAppConnectionStatus,
} from "@/lib/whatsapp-connection";
import { cn } from "@/lib/utils";

const TYPE_LABELS: Record<Business["type"], string> = {
  restaurant: "Restaurant",
  cafe: "Café",
  bakery: "Bakery",
  home_kitchen: "Home kitchen",
  other: "Other",
};

type ChecklistDetails = {
  categoryCount: number;
  productCount: number;
  activeZoneCount: number;
  agentConfigured: boolean;
  agentUpsell: boolean;
  agentHandoff: boolean;
  whatsappStatus: WhatsAppConnectionStatus;
};

type ChecklistRow = {
  key: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  title: string;
  summary: string;
  statusText: string;
  ok: boolean;
  href: string;
};

function accessTokenFromStorage(): string | null {
  return (
    window.localStorage.getItem("orderly.access_token") ??
    window.sessionStorage.getItem("orderly.access_token")
  );
}

/** Dark-green filled tick when done, neutral outline dot when pending. */
function StatusDot({ done }: { done: boolean }) {
  if (done) {
    return (
      <span className="grid size-[18px] shrink-0 place-items-center rounded-full bg-primary">
        <Check className="size-3 text-white" strokeWidth={3.5} />
      </span>
    );
  }
  return (
    <span className="grid size-[18px] shrink-0 place-items-center rounded-full border border-border bg-white">
      <span className="size-1.5 rounded-full bg-muted-foreground/50" />
    </span>
  );
}

function fulfillmentLabel(business: Business): string {
  if (business.offers_delivery && business.offers_pickup) return "Delivery + Pickup";
  if (business.offers_delivery) return "Delivery";
  if (business.offers_pickup) return "Pickup";
  return "Not set";
}

function whatsappSummary(status: WhatsAppConnectionStatus): {
  text: string;
  statusText: string;
  ok: boolean;
} {
  switch (status) {
    case "verified":
      return { text: "Number connected and verified", statusText: "Verified", ok: true };
    case "configured":
      return { text: "Test number connected", statusText: "Connected", ok: true };
    case "error":
      return { text: "Connection needs attention", statusText: "Error", ok: false };
    default:
      return { text: "No number connected", statusText: "Skipped", ok: false };
  }
}

function buildRows(business: Business, details: ChecklistDetails): ChecklistRow[] {
  const wa = whatsappSummary(details.whatsappStatus);
  return [
    {
      key: "profile",
      icon: Store,
      title: "Business profile",
      summary: `${business.name} · ${TYPE_LABELS[business.type]}${
        business.helpline_phone || business.email ? " · Contact added" : ""
      }`,
      statusText: business.name.trim() && business.type ? "Complete" : "Incomplete",
      ok: Boolean(business.name.trim() && business.type),
      href: "/onboarding/business-profile",
    },
    {
      key: "hours",
      icon: Clock,
      title: "Hours",
      summary: business.timezone,
      statusText: "Configured",
      ok: true,
      href: "/onboarding/hours",
    },
    {
      key: "fulfillment",
      icon: Truck,
      title: "Fulfillment",
      summary: `${fulfillmentLabel(business)} · ${details.activeZoneCount} active ${
        details.activeZoneCount === 1 ? "zone" : "zones"
      }`,
      statusText:
        business.offers_delivery || business.offers_pickup ? "Complete" : "Not set",
      ok: business.offers_delivery || business.offers_pickup,
      href: "/onboarding/fulfillment",
    },
    {
      key: "menu",
      icon: UtensilsCrossed,
      title: "Menu",
      summary: `${details.categoryCount} ${
        details.categoryCount === 1 ? "category" : "categories"
      } · ${details.productCount} ${
        details.productCount === 1 ? "dish" : "dishes"
      }`,
      statusText: details.productCount > 0 ? "Complete" : "Add dishes",
      ok: details.productCount > 0,
      href: "/onboarding/menu",
    },
    {
      key: "assistant",
      icon: Bot,
      title: "AI assistant",
      summary: details.agentConfigured
        ? `${details.agentUpsell ? "Upsell on" : "Upsell off"} · ${
            details.agentHandoff ? "Human handoff" : "No handoff"
          }`
        : "Using default greeting",
      statusText: details.agentConfigured ? "Configured" : "Default",
      ok: details.agentConfigured,
      href: "/onboarding/assistant",
    },
    {
      key: "whatsapp",
      icon: WhatsAppIcon,
      title: "WhatsApp",
      summary: wa.text,
      statusText: wa.statusText,
      ok: wa.ok,
      href: "/onboarding/whatsapp",
    },
  ];
}

export function ReviewGoLive() {
  const router = useRouter();
  const [accessToken, setAccessToken] = useState("");
  const [business, setBusiness] = useState<Business | null>(null);
  const [details, setDetails] = useState<ChecklistDetails | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isGoingLive, setIsGoingLive] = useState(false);
  const [isLive, setIsLive] = useState(false);

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
        if (!selected) {
          throw new ApiError("Complete your business profile first.", 400);
        }
        saveSelectedBusinessId(selected.id);

        const [categories, products, zones, agentConfig, whatsappStatus] =
          await Promise.all([
            listCategories({ accessToken: token, businessId: selected.id }).catch(
              () => [],
            ),
            listProducts({ accessToken: token, businessId: selected.id }).catch(
              () => [],
            ),
            listDeliveryZones({ accessToken: token, businessId: selected.id }).catch(
              () => [],
            ),
            getAgentConfig({ accessToken: token, businessId: selected.id }).catch(
              () => null,
            ),
            getWhatsAppConnection({ accessToken: token, businessId: selected.id })
              .then((connection) => connection.status)
              .catch(() => "not_configured" as WhatsAppConnectionStatus),
          ]);

        if (!active) return;
        setAccessToken(token);
        setBusiness(selected);
        setIsLive(selected.status === "active");
        setDetails({
          categoryCount: categories.length,
          productCount: products.filter((product) => !product.is_archived).length,
          activeZoneCount: zones.filter((zone) => zone.is_active).length,
          agentConfigured: Boolean(agentConfig?.id),
          agentUpsell: agentConfig?.upsell_enabled ?? false,
          agentHandoff: Boolean(agentConfig?.human_handoff_phone),
          whatsappStatus,
        });
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          toast.error("Your session has expired. Please sign in again.");
          router.replace("/login");
          return;
        }
        toast.error(
          error instanceof ApiError ? error.message : "We couldn't load your setup.",
        );
      } finally {
        if (active) setIsLoading(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [router]);

  const businessProfileComplete = Boolean(business?.name.trim() && business?.type);
  const hasMenuItems = (details?.productCount ?? 0) > 0;
  const canGoLive = businessProfileComplete && hasMenuItems;
  const rows = business && details ? buildRows(business, details) : [];

  function handleEdit(href: string) {
    saveOnboardingResumePath("/onboarding/review");
    router.push(href);
  }

  function handleFinishLater() {
    saveOnboardingResumePath("/onboarding/review");
    clearTokens();
    router.replace("/login");
  }

  async function handleGoLive() {
    if (!business || !accessToken) {
      toast.error("Still loading your setup. Try again in a moment.");
      return;
    }
    if (!canGoLive) {
      toast.error("Complete the required items before going live.");
      return;
    }

    setIsGoingLive(true);
    try {
      const updated = await goLiveBusiness({ accessToken, businessId: business.id });
      saveSelectedBusinessId(updated.id);
      setBusiness(updated);
      setIsLive(true);
      window.localStorage.removeItem(ONBOARDING_RESUME_STORAGE_KEY);
      toast.success("Your store is live! 🎉");
      router.push("/dashboard");
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't take your store live. Please try again.",
      );
    } finally {
      setIsGoingLive(false);
    }
  }

  return (
    <OnboardingShell
      currentStep={8}
      contentClassName="max-w-[780px]"
      mainClassName={ONBOARDING_MAIN_CLASS_NAME}
      footerClassName="grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2"
      onSaveExit={handleFinishLater}
      footer={
        <>
          <Button
            type="button"
            variant="outline"
            size="lg"
            onClick={() => router.push("/onboarding/whatsapp")}
            className="h-10 min-w-[104px]"
          >
            <ArrowLeft data-icon="inline-start" />
            Back
          </Button>
          <Button
            type="button"
            variant="link"
            size="lg"
            onClick={handleFinishLater}
          >
            I&apos;ll finish later
          </Button>
          <Button
            type="button"
            size="lg"
            disabled={isLoading || isGoingLive || (!isLive && !canGoLive)}
            onClick={() => {
              if (isLive) {
                router.push("/dashboard");
              } else {
                void handleGoLive();
              }
            }}
            className="h-10 min-w-[136px]"
          >
            {isGoingLive ? <Spinner data-icon="inline-start" /> : null}
            {isLive ? "Go to dashboard" : "Go live"}
            <ArrowRight data-icon="inline-end" />
          </Button>
        </>
      }
    >
      <OnboardingStepHeader
        stepLabel="Step 8 of 8"
        title="You're almost ready 🎉"
        subtitle="Review your setup before opening your store."
      />

      <div className="mt-5 flex flex-col gap-3">
        <div
          className={cn(
            "flex items-center gap-4 rounded-lg border px-4 py-3",
            isLive
              ? "border-primary/40 bg-primary/10"
              : canGoLive
                ? "border-primary/30 bg-primary/5"
                : "border-amber-300 bg-amber-50",
          )}
        >
          <WelcomeIllustration className="w-14 shrink-0 sm:w-16" />
          <div className="min-w-0">
            <p
              className={cn(
                "font-medium",
                canGoLive || isLive ? "text-[#0A3B2F]" : "text-amber-950",
              )}
            >
              {isLive
                ? "Your store is live"
                : canGoLive
                  ? "Ready to go live"
                  : "Almost there"}
            </p>
            <p
              className={cn(
                "mt-0.5 text-sm",
                canGoLive || isLive ? "text-muted-foreground" : "text-amber-900",
              )}
            >
              {isLive
                ? "Customers can now order from your store on WhatsApp."
                : canGoLive
                  ? "Your business profile and menu meet the launch requirements."
                  : "Add the required items below before you can open your store."}
            </p>
          </div>
        </div>

        <OnboardingCard>
          <CardHeader className="px-5 py-4">
            <CardTitle className="font-sans text-base">Setup checklist</CardTitle>
          </CardHeader>
          <Separator />
          <CardContent className="px-0 py-0">
            {isLoading ? (
              <div className="grid min-h-[260px] place-items-center">
                <Spinner />
              </div>
            ) : (
              rows.map((row, index) => {
                const Icon = row.icon;
                return (
                  <div key={row.key}>
                    {index > 0 ? <Separator /> : null}
                    <div className="flex items-center gap-3 px-5 py-3.5">
                      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-muted text-foreground">
                        <Icon className="size-[18px]" strokeWidth={2.25} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-foreground">
                          {row.title}
                        </p>
                        <p className="truncate text-sm text-muted-foreground">
                          {row.summary}
                        </p>
                      </div>
                      <div className="hidden w-[140px] shrink-0 items-center gap-2 sm:flex">
                        <StatusDot done={row.ok} />
                        <span
                          className={cn(
                            "text-sm font-medium",
                            row.ok ? "text-primary" : "text-muted-foreground",
                          )}
                        >
                          {row.statusText}
                        </span>
                      </div>
                      <Button
                        type="button"
                        variant="link"
                        size="sm"
                        className="h-auto w-10 shrink-0 justify-start p-0 text-sm font-medium text-primary"
                        onClick={() => handleEdit(row.href)}
                      >
                        Edit
                      </Button>
                    </div>
                  </div>
                );
              })
            )}
          </CardContent>
        </OnboardingCard>

        <div className="rounded-lg border border-border bg-muted/25 px-4 py-3">
          <p className="text-sm font-medium text-foreground">Required to go live</p>
          <div className="mt-2.5 flex flex-wrap gap-x-6 gap-y-2">
            <span className="inline-flex items-center gap-2 text-sm font-medium text-foreground">
              <StatusDot done={businessProfileComplete} />
              Business profile
            </span>
            <span className="inline-flex items-center gap-2 text-sm font-medium text-foreground">
              <StatusDot done={hasMenuItems} />
              At least 1 dish
            </span>
          </div>
        </div>

        <p className="text-center text-xs text-muted-foreground">
          You can update any setting from the dashboard.
        </p>
      </div>
    </OnboardingShell>
  );
}
