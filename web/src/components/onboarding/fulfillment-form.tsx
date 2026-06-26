"use client";

import {
  ArrowLeft,
  ArrowRight,
  Plus,
  ShoppingBag,
  Trash2,
  Truck,
  Utensils,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { OnboardingShell } from "@/components/onboarding/onboarding-shell";
import {
  ONBOARDING_CONTENT_CLASS_NAME,
  ONBOARDING_MAIN_CLASS_NAME,
  OnboardingCard,
  OnboardingStepHeader,
} from "@/components/onboarding/onboarding-step-ui";
import { Button } from "@/components/ui/button";
import {
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldTitle,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
  InputGroupText,
} from "@/components/ui/input-group";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, clearTokens } from "@/lib/auth";
import {
  pickBusinessForOwner,
  saveSelectedBusinessId,
} from "@/lib/business-selection";
import { listBusinesses } from "@/lib/business-profile";
import {
  createDeliveryZoneDraft,
  createFulfillmentValues,
  hasFulfillmentErrors,
  listDeliveryZones,
  saveFulfillment,
  validateFulfillment,
  type DeliveryZoneDraft,
  type FulfillmentErrors,
  type FulfillmentValues,
} from "@/lib/fulfillment";
import { saveOnboardingResumePath } from "@/lib/onboarding-progress";

const CURRENCY_SYMBOLS: Record<string, string> = {
  PKR: "₨",
  USD: "$",
  INR: "₹",
  AED: "د.إ",
  GBP: "£",
  EUR: "€",
};

type FulfillmentOptionProps = {
  icon: typeof Truck;
  title: string;
  description: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
};

function FulfillmentOption({
  icon: Icon,
  title,
  description,
  checked,
  onCheckedChange,
}: FulfillmentOptionProps) {
  return (
    <Field
      orientation="horizontal"
      className="min-h-[72px] rounded-lg border border-border p-2.5"
    >
      <Icon className="size-6 shrink-0 stroke-[1.5] text-foreground" />
      <FieldContent className="min-w-0">
        <FieldTitle>{title}</FieldTitle>
        <FieldDescription>{description}</FieldDescription>
      </FieldContent>
      <div className="ml-auto flex shrink-0 items-center gap-2">
        <Switch
          size="lg"
          checked={checked}
          onCheckedChange={onCheckedChange}
          aria-label={`${title} ${checked ? "enabled" : "disabled"}`}
        />
        <span className={checked ? "text-xs font-medium text-primary" : "text-xs text-muted-foreground"}>
          {checked ? "ON" : "OFF"}
        </span>
      </div>
    </Field>
  );
}

type ZoneRowProps = {
  zone: DeliveryZoneDraft;
  currencySymbol: string;
  errors?: FulfillmentErrors["zoneFields"][string];
  showErrors: boolean;
  onChange: (patch: Partial<DeliveryZoneDraft>) => void;
  onRemove: () => void;
};

function ZoneRow({
  zone,
  currencySymbol,
  errors,
  showErrors,
  onChange,
  onRemove,
}: ZoneRowProps) {
  return (
    <TableRow>
      <TableCell>
        <Input
          value={zone.name}
          onChange={(event) => onChange({ name: event.target.value })}
          placeholder="e.g. Gulshan"
          aria-label="Zone name"
          aria-invalid={showErrors && Boolean(errors?.name)}
          className="h-9 min-w-[150px]"
        />
      </TableCell>
      <TableCell>
        <InputGroup className="h-9 min-w-[128px]">
          <InputGroupAddon>
            <InputGroupText>{currencySymbol}</InputGroupText>
          </InputGroupAddon>
          <InputGroupInput
            type="number"
            min="0"
            step="0.01"
            value={zone.fee}
            onChange={(event) => onChange({ fee: event.target.value })}
            aria-label="Delivery fee"
            aria-invalid={showErrors && Boolean(errors?.fee)}
          />
        </InputGroup>
      </TableCell>
      <TableCell>
        <InputGroup className="h-9 min-w-[128px]">
          <InputGroupAddon>
            <InputGroupText>{currencySymbol}</InputGroupText>
          </InputGroupAddon>
          <InputGroupInput
            type="number"
            min="0"
            step="0.01"
            value={zone.minOrder}
            onChange={(event) => onChange({ minOrder: event.target.value })}
            aria-label="Zone minimum order"
            aria-invalid={showErrors && Boolean(errors?.minOrder)}
          />
        </InputGroup>
      </TableCell>
      <TableCell>
        <Input
          type="number"
          min="0"
          step="1"
          value={zone.etaMinutes}
          onChange={(event) => onChange({ etaMinutes: event.target.value })}
          aria-label="Zone ETA in minutes"
          aria-invalid={showErrors && Boolean(errors?.etaMinutes)}
          className="h-9 min-w-[105px]"
        />
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <Switch
            size="lg"
            checked={zone.isActive}
            onCheckedChange={(checked) => onChange({ isActive: checked })}
            aria-label={`${zone.name || "Delivery zone"} active`}
          />
          <span className="text-xs text-muted-foreground">
            {zone.isActive ? "ON" : "OFF"}
          </span>
        </div>
      </TableCell>
      <TableCell className="text-right">
        <Button
          type="button"
          variant="destructive"
          size="icon-sm"
          onClick={onRemove}
          aria-label={`Remove ${zone.name || "delivery zone"}`}
        >
          <Trash2 />
        </Button>
      </TableCell>
    </TableRow>
  );
}

function accessTokenFromStorage(): string | null {
  return (
    window.localStorage.getItem("orderly.access_token") ??
    window.sessionStorage.getItem("orderly.access_token")
  );
}

type FulfillmentFormProps = {
  variant?: "onboarding" | "settings";
  onSaved?: () => void;
};

export function FulfillmentForm({
  variant = "onboarding",
  onSaved,
}: FulfillmentFormProps = {}) {
  const router = useRouter();
  const isSettings = variant === "settings";
  const nextZoneNumber = useRef(2);
  const [businessId, setBusinessId] = useState<string>();
  const [currency, setCurrency] = useState("PKR");
  const [values, setValues] = useState<FulfillmentValues>(() => ({
    offersDelivery: true,
    offersPickup: true,
    offersDineIn: false,
    minOrderAmount: "0",
    defaultPrepMinutes: "30",
    packagingFee: "0",
    zones: [createDeliveryZoneDraft("zone-new-1")],
  }));
  const [deletedZoneIds, setDeletedZoneIds] = useState<string[]>([]);
  const [showErrors, setShowErrors] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  const errors = validateFulfillment(values);
  const currencySymbol = CURRENCY_SYMBOLS[currency] ?? currency;

  useEffect(() => {
    const accessToken = accessTokenFromStorage();
    if (!accessToken) {
      toast.error("Please sign in to continue.");
      router.replace("/login");
      return;
    }

    let active = true;
    void listBusinesses(accessToken)
      .then(async (businesses) => {
        const business = pickBusinessForOwner(businesses);
        if (!business) {
          throw new ApiError("Complete your business profile first.", 400);
        }
        saveSelectedBusinessId(business.id);
        const zones = await listDeliveryZones({
          accessToken,
          businessId: business.id,
        });
        if (!active) return;

        const restored = createFulfillmentValues(business, zones);
        if (restored.offersDelivery && restored.zones.length === 0) {
          restored.zones = [createDeliveryZoneDraft("zone-new-1")];
        }
        setBusinessId(business.id);
        setCurrency(business.currency);
        setValues(restored);
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          toast.error("Your session has expired. Please sign in again.");
          router.replace("/login");
          return;
        }
        toast.error(
          error instanceof ApiError
            ? error.message
            : "We couldn't load your fulfillment settings.",
        );
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [router]);

  function updateZone(clientId: string, patch: Partial<DeliveryZoneDraft>) {
    setValues((current) => ({
      ...current,
      zones: current.zones.map((zone) =>
        zone.clientId === clientId ? { ...zone, ...patch } : zone,
      ),
    }));
  }

  function addZone() {
    const zone = createDeliveryZoneDraft(`zone-new-${nextZoneNumber.current}`);
    nextZoneNumber.current += 1;
    setValues((current) => ({ ...current, zones: [...current.zones, zone] }));
  }

  function removeZone(zoneToRemove: DeliveryZoneDraft) {
    if (zoneToRemove.id) {
      setDeletedZoneIds((current) => [...current, zoneToRemove.id as string]);
    }
    setValues((current) => {
      const remaining = current.zones.filter(
        (zone) => zone.clientId !== zoneToRemove.clientId,
      );
      return {
        ...current,
        zones:
          remaining.length > 0
            ? remaining
            : [createDeliveryZoneDraft(`zone-new-${nextZoneNumber.current++}`)],
      };
    });
  }

  function setDeliveryEnabled(checked: boolean) {
    setValues((current) => ({
      ...current,
      offersDelivery: checked,
      zones:
        checked && current.zones.length === 0
          ? [createDeliveryZoneDraft(`zone-new-${nextZoneNumber.current++}`)]
          : current.zones,
    }));
  }

  async function persist(destination: string) {
    setShowErrors(true);
    if (hasFulfillmentErrors(errors)) {
      toast.error("Check your fulfillment settings before continuing.");
      return;
    }

    const accessToken = accessTokenFromStorage();
    if (!accessToken || !businessId) {
      toast.error("Complete your business profile before saving fulfillment settings.");
      router.replace(accessToken ? "/onboarding/business-profile" : "/login");
      return;
    }

    setIsSaving(true);
    try {
      saveSelectedBusinessId(businessId);
      await saveFulfillment({
        accessToken,
        businessId,
        values,
        deletedZoneIds,
      });
      setDeletedZoneIds([]);
      saveOnboardingResumePath(
        destination === "/login" ? "/onboarding/fulfillment" : destination,
      );
      toast.success("Fulfillment settings saved.");
      if (destination === "/login") clearTokens();
      router.push(destination);
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't save fulfillment settings. Please try again.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  async function handleSettingsSave() {
    setShowErrors(true);
    if (hasFulfillmentErrors(errors)) {
      toast.error("Check your fulfillment settings before saving.");
      return;
    }
    const accessToken = accessTokenFromStorage();
    if (!accessToken || !businessId) {
      toast.error("Complete your business profile before saving fulfillment settings.");
      return;
    }
    setIsSaving(true);
    try {
      saveSelectedBusinessId(businessId);
      await saveFulfillment({ accessToken, businessId, values, deletedZoneIds });
      setDeletedZoneIds([]);
      onSaved?.();
      toast.success("Fulfillment settings saved.");
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't save fulfillment settings. Please try again.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  const content = (
    <>
      <OnboardingCard className={isSettings ? "" : "mt-3"}>
        <CardHeader className="px-5 py-3 lg:px-6">
          <CardTitle className="font-sans text-lg">Fulfillment options</CardTitle>
        </CardHeader>
        <CardContent className="px-5 pb-4 lg:px-6">
          <div className="grid gap-4 md:grid-cols-3">
            <FulfillmentOption
              icon={Truck}
              title="Delivery"
              description="Deliver to customer addresses"
              checked={values.offersDelivery}
              onCheckedChange={setDeliveryEnabled}
            />
            <FulfillmentOption
              icon={ShoppingBag}
              title="Pickup"
              description="Customers collect their order"
              checked={values.offersPickup}
              onCheckedChange={(checked) =>
                setValues((current) => ({ ...current, offersPickup: checked }))
              }
            />
            <FulfillmentOption
              icon={Utensils}
              title="Dine-in"
              description="Order at the table"
              checked={values.offersDineIn}
              onCheckedChange={(checked) =>
                setValues((current) => ({ ...current, offersDineIn: checked }))
              }
            />
          </div>
          {showErrors && errors.fulfillment ? (
            <FieldError className="mt-3">{errors.fulfillment}</FieldError>
          ) : null}
        </CardContent>
      </OnboardingCard>

      <OnboardingCard className="mt-3">
        <CardHeader className="px-5 py-3 lg:px-6">
          <CardTitle className="font-sans text-lg">Order settings</CardTitle>
        </CardHeader>
        <CardContent className="px-5 pb-4 lg:px-6">
          <FieldGroup className="grid gap-4 md:grid-cols-3">
            <Field data-invalid={showErrors && Boolean(errors.minOrderAmount)}>
              <FieldLabel htmlFor="minimum-order">Minimum order amount</FieldLabel>
              <InputGroup className="h-11">
                <InputGroupAddon>
                  <InputGroupText>{currencySymbol}</InputGroupText>
                </InputGroupAddon>
                <InputGroupInput
                  id="minimum-order"
                  type="number"
                  min="0"
                  step="0.01"
                  value={values.minOrderAmount}
                  onChange={(event) =>
                    setValues((current) => ({
                      ...current,
                      minOrderAmount: event.target.value,
                    }))
                  }
                  aria-invalid={showErrors && Boolean(errors.minOrderAmount)}
                />
              </InputGroup>
              <FieldError>{showErrors ? errors.minOrderAmount : undefined}</FieldError>
            </Field>

            <Field data-invalid={showErrors && Boolean(errors.defaultPrepMinutes)}>
              <FieldLabel htmlFor="prep-time">Default prep time</FieldLabel>
              <InputGroup className="h-11">
                <InputGroupInput
                  id="prep-time"
                  type="number"
                  min="0"
                  step="1"
                  value={values.defaultPrepMinutes}
                  onChange={(event) =>
                    setValues((current) => ({
                      ...current,
                      defaultPrepMinutes: event.target.value,
                    }))
                  }
                  aria-invalid={showErrors && Boolean(errors.defaultPrepMinutes)}
                />
                <InputGroupAddon align="inline-end">
                  <InputGroupText>minutes</InputGroupText>
                </InputGroupAddon>
              </InputGroup>
              <FieldError>{showErrors ? errors.defaultPrepMinutes : undefined}</FieldError>
            </Field>

            <Field data-invalid={showErrors && Boolean(errors.packagingFee)}>
              <FieldLabel htmlFor="packaging-fee">Packaging fee</FieldLabel>
              <InputGroup className="h-11">
                <InputGroupAddon>
                  <InputGroupText>{currencySymbol}</InputGroupText>
                </InputGroupAddon>
                <InputGroupInput
                  id="packaging-fee"
                  type="number"
                  min="0"
                  step="0.01"
                  value={values.packagingFee}
                  onChange={(event) =>
                    setValues((current) => ({
                      ...current,
                      packagingFee: event.target.value,
                    }))
                  }
                  aria-invalid={showErrors && Boolean(errors.packagingFee)}
                />
              </InputGroup>
              <FieldDescription>Optional</FieldDescription>
              <FieldError>{showErrors ? errors.packagingFee : undefined}</FieldError>
            </Field>
          </FieldGroup>
        </CardContent>
      </OnboardingCard>

      {values.offersDelivery ? (
        <OnboardingCard className="mt-3">
          <CardHeader className="grid gap-3 px-5 py-3 has-data-[slot=card-action]:grid-cols-1 sm:has-data-[slot=card-action]:grid-cols-[minmax(0,1fr)_auto] lg:px-6">
            <div>
              <CardTitle className="font-sans text-lg">Delivery zones</CardTitle>
              <CardDescription className="mt-0.5">
                Add the areas you deliver to and the fee for each.
              </CardDescription>
            </div>
            <CardAction className="col-start-1 row-start-auto row-span-1 justify-self-start sm:col-start-2 sm:row-start-1 sm:row-span-2 sm:justify-self-end">
              <Button type="button" variant="outline" size="lg" onClick={addZone}>
                <Plus data-icon="inline-start" />
                Add zone
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="px-0 pb-3">
            <Table className="min-w-[850px] border-y">
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-5">Zone name *</TableHead>
                  <TableHead>Delivery fee *</TableHead>
                  <TableHead>Min order</TableHead>
                  <TableHead>ETA (minutes)</TableHead>
                  <TableHead>Active</TableHead>
                  <TableHead aria-label="Actions" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {values.zones.map((zone) => (
                  <ZoneRow
                    key={zone.clientId}
                    zone={zone}
                    currencySymbol={currencySymbol}
                    errors={errors.zoneFields[zone.clientId]}
                    showErrors={showErrors}
                    onChange={(patch) => updateZone(zone.clientId, patch)}
                    onRemove={() => removeZone(zone)}
                  />
                ))}
              </TableBody>
            </Table>
            <div className="px-5 pt-3 lg:px-6">
              {showErrors && errors.zones ? (
                <FieldError>{errors.zones}</FieldError>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Delivery requires at least one active zone.
                </p>
              )}
            </div>
          </CardContent>
        </OnboardingCard>
      ) : null}
    </>
  );

  if (isSettings) {
    return (
      <div className="flex flex-col">
        {content}
        <div className="mt-6 flex items-center justify-end border-t border-border pt-4">
          <Button
            type="button"
            onClick={() => void handleSettingsSave()}
            disabled={isLoading || isSaving}
            className="h-10 min-w-[150px]"
          >
            {isSaving ? <Spinner data-icon="inline-start" /> : null}
            Save changes
          </Button>
        </div>
      </div>
    );
  }

  return (
    <OnboardingShell
      currentStep={4}
      contentClassName={ONBOARDING_CONTENT_CLASS_NAME}
      mainClassName={ONBOARDING_MAIN_CLASS_NAME}
      footerClassName="w-full justify-between gap-3"
      onSaveExit={() => void persist("/login")}
      footer={
        <>
          <Button
            type="button"
            variant="outline"
            size="lg"
            onClick={() => router.push("/onboarding/hours")}
            className="h-10 min-w-[104px]"
          >
            <ArrowLeft data-icon="inline-start" />
            Back
          </Button>
          <Button
            type="button"
            variant="link"
            size="lg"
            onClick={() => {
              saveOnboardingResumePath("/onboarding/fulfillment");
              router.push("/onboarding/menu");
            }}
          >
            Skip for now
          </Button>
          <Button
            type="button"
            size="lg"
            disabled={isLoading || isSaving}
            onClick={() => void persist("/onboarding/menu")}
            className="h-10 min-w-[136px]"
          >
            {isSaving ? <Spinner data-icon="inline-start" /> : null}
            Continue
            <ArrowRight data-icon="inline-end" />
          </Button>
        </>
      }
    >
      <OnboardingStepHeader
        stepLabel="Step 4 of 8"
        title="How do customers get their food?"
        subtitle="Choose your fulfillment options and delivery settings."
      />
      {content}
    </OnboardingShell>
  );
}
