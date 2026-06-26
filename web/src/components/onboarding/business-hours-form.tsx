"use client";

import { ArrowLeft, ArrowRight, Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { OnboardingShell } from "@/components/onboarding/onboarding-shell";
import {
  ONBOARDING_CONTENT_CLASS_NAME,
  ONBOARDING_MAIN_CLASS_NAME,
  OnboardingCard,
  OnboardingStepHeader,
} from "@/components/onboarding/onboarding-step-ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { Switch } from "@/components/ui/switch";
import { ApiError, clearTokens } from "@/lib/auth";
import {
  addTimeSlot,
  applyMondayHours,
  createDefaultBusinessHours,
  isBusinessHoursValid,
  isOvernightSlot,
  isTimeSlotValid,
  listBusinessHours,
  markWeekendClosed,
  removeTimeSlot,
  saveBusinessHours,
  scheduleFromHours,
  setDayOpen,
  TIME_OPTIONS,
  updateTimeSlot,
  type BusinessDayHours,
  type TimeSlot,
} from "@/lib/business-hours";
import {
  pickBusinessForOwner,
  saveSelectedBusinessId,
} from "@/lib/business-selection";
import { listBusinesses } from "@/lib/business-profile";
import { saveOnboardingResumePath } from "@/lib/onboarding-progress";

function accessTokenFromStorage(): string | null {
  return (
    window.localStorage.getItem("orderly.access_token") ??
    window.sessionStorage.getItem("orderly.access_token")
  );
}

type ScheduleRowProps = {
  day: BusinessDayHours;
  dayIndex: number;
  onOpenChange: (dayIndex: number, isOpen: boolean) => void;
  onSlotChange: (
    dayIndex: number,
    slotIndex: number,
    field: keyof TimeSlot,
    value: string,
  ) => void;
  onAddSlot: (dayIndex: number) => void;
  onRemoveSlot: (dayIndex: number, slotIndex: number) => void;
};

function ScheduleRow({
  day,
  dayIndex,
  onOpenChange,
  onSlotChange,
  onAddSlot,
  onRemoveSlot,
}: ScheduleRowProps) {
  return (
    <div className="grid min-h-[64px] items-center gap-4 px-5 py-3 lg:grid-cols-[92px_124px_minmax(0,1fr)_126px] lg:px-7">
      <p className="text-sm font-medium text-foreground">{day.day}</p>

      <div className="flex items-center gap-3">
        <Switch
          size="lg"
          checked={day.isOpen}
          onCheckedChange={(checked) => onOpenChange(dayIndex, checked)}
          aria-label={`${day.day} is ${day.isOpen ? "open" : "closed"}`}
        />
        <span className={day.isOpen ? "text-sm text-primary" : "text-sm text-muted-foreground"}>
          {day.isOpen ? "Open" : "Closed"}
        </span>
      </div>

      {day.isOpen ? (
        <div className="flex min-w-0 flex-wrap items-center gap-2.5">
          {day.slots.map((slot, slotIndex) => {
            const isInvalid = !isTimeSlotValid(slot);
            const isOvernight = isOvernightSlot(slot);

            return (
              <div key={slotIndex} className="contents">
                {slotIndex > 0 ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => onRemoveSlot(dayIndex, slotIndex)}
                    aria-label={`Remove ${day.day} time slot ${slotIndex + 1}`}
                  >
                    <Trash2 />
                  </Button>
                ) : null}
                <Select
                  items={TIME_OPTIONS}
                  value={slot.opensAt}
                  onValueChange={(value) => {
                    if (value !== null) {
                      onSlotChange(dayIndex, slotIndex, "opensAt", value);
                    }
                  }}
                >
                  <SelectTrigger
                    className="h-11 w-[132px]"
                    aria-label={`${day.day} slot ${slotIndex + 1} opening time`}
                    aria-invalid={isInvalid}
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent alignItemWithTrigger={false}>
                    <SelectGroup>
                      {TIME_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
                <span className="text-sm text-muted-foreground">to</span>
                <Select
                  items={TIME_OPTIONS}
                  value={slot.closesAt}
                  onValueChange={(value) => {
                    if (value !== null) {
                      onSlotChange(dayIndex, slotIndex, "closesAt", value);
                    }
                  }}
                >
                  <SelectTrigger
                    className="h-11 w-[132px]"
                    aria-label={`${day.day} slot ${slotIndex + 1} closing time`}
                    aria-invalid={isInvalid}
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent alignItemWithTrigger={false}>
                    <SelectGroup>
                      {TIME_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
                {isOvernight ? (
                  <Badge variant="secondary" className="h-6 shrink-0">
                    Next day
                  </Badge>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}

      {day.isOpen ? (
        <Button
          type="button"
          variant="outline"
          size="lg"
          disabled={day.slots.length >= 2}
          onClick={() => onAddSlot(dayIndex)}
          className="justify-self-start lg:justify-self-end"
        >
          <Plus data-icon="inline-start" />
          Add time slot
        </Button>
      ) : null}
    </div>
  );
}

type BusinessHoursFormProps = {
  variant?: "onboarding" | "settings";
  onSaved?: () => void;
};

export function BusinessHoursForm({
  variant = "onboarding",
  onSaved,
}: BusinessHoursFormProps = {}) {
  const router = useRouter();
  const isSettings = variant === "settings";
  const [businessId, setBusinessId] = useState<string>();
  const [timezone, setTimezone] = useState("Asia/Karachi");
  const [acceptingOrders, setAcceptingOrders] = useState(true);
  const [schedule, setSchedule] = useState(createDefaultBusinessHours);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const isValid = isBusinessHoursValid(schedule);

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
        const rows = await listBusinessHours({ accessToken, businessId: business.id });
        if (!active) return;
        setBusinessId(business.id);
        setTimezone(business.timezone);
        setAcceptingOrders(business.accepting_orders);
        if (rows.length > 0) setSchedule(scheduleFromHours(rows));
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          toast.error("Your session has expired. Please sign in again.");
          router.replace("/login");
          return;
        }
        toast.error(
          error instanceof ApiError ? error.message : "We couldn't load your hours.",
        );
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [router]);

  async function persist(destination: string) {
    if (!isValid) {
      toast.error("Check your hours before continuing.", {
        description: "Opening and closing times must be different.",
      });
      return;
    }

    const accessToken = accessTokenFromStorage();
    if (!accessToken || !businessId) {
      toast.error("Complete your business profile before saving hours.");
      router.replace(accessToken ? "/onboarding/business-profile" : "/login");
      return;
    }

    setIsSaving(true);
    try {
      saveSelectedBusinessId(businessId);
      await saveBusinessHours({ accessToken, businessId, schedule, acceptingOrders });
      saveOnboardingResumePath(
        destination === "/login" ? "/onboarding/hours" : destination,
      );
      toast.success("Opening hours saved.");
      if (destination === "/login") clearTokens();
      router.push(destination);
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't save your hours. Please try again.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  function handleSlotChange(
    dayIndex: number,
    slotIndex: number,
    field: keyof TimeSlot,
    value: string,
  ) {
    setSchedule((current) =>
      updateTimeSlot(current, dayIndex, slotIndex, field, value),
    );
  }

  async function handleSettingsSave() {
    if (!isValid) {
      toast.error("Check your hours before saving.", {
        description: "Opening and closing times must be different.",
      });
      return;
    }
    const accessToken = accessTokenFromStorage();
    if (!accessToken || !businessId) {
      toast.error("Complete your business profile before saving hours.");
      return;
    }
    setIsSaving(true);
    try {
      saveSelectedBusinessId(businessId);
      await saveBusinessHours({ accessToken, businessId, schedule, acceptingOrders });
      onSaved?.();
      toast.success("Opening hours saved.");
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't save your hours. Please try again.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  const content = (
    <>
      <OnboardingCard className={isSettings ? "" : "mt-3"}>
        <CardHeader className="grid gap-3 px-5 py-3 has-data-[slot=card-action]:grid-cols-1 sm:items-center sm:has-data-[slot=card-action]:grid-cols-[minmax(0,1fr)_auto] lg:px-6">
          <div>
            <CardTitle className="font-sans text-lg">Accepting orders now</CardTitle>
            <CardDescription className="mt-0.5 max-w-2xl leading-snug">
              Turn off to instantly pause new orders even during open hours — useful when the kitchen is busy.
            </CardDescription>
          </div>
          <CardAction className="col-start-1 row-start-auto row-span-1 flex items-center gap-4 self-center justify-self-start sm:col-start-2 sm:row-start-1 sm:row-span-2 sm:justify-self-end">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-primary">{acceptingOrders ? "ON" : "OFF"}</span>
              <Switch
                size="lg"
                checked={acceptingOrders}
                onCheckedChange={setAcceptingOrders}
                aria-label="Accepting orders now"
              />
            </div>
            <Badge variant={acceptingOrders ? "secondary" : "outline"}>
              {acceptingOrders ? "Accepting orders" : "Orders paused"}
            </Badge>
          </CardAction>
        </CardHeader>
      </OnboardingCard>

      <OnboardingCard className="mt-3">
        <CardHeader className="gap-4 px-5 py-4 has-data-[slot=card-action]:grid-cols-1 lg:items-center lg:px-6 lg:has-data-[slot=card-action]:grid-cols-[minmax(0,1fr)_auto]">
          <div>
            <CardTitle className="font-sans text-lg">Weekly schedule</CardTitle>
            <CardDescription className="mt-1">Timezone: {timezone}</CardDescription>
          </div>
          <CardAction className="col-start-1 row-start-auto row-span-1 flex flex-wrap gap-3 justify-self-start lg:col-start-2 lg:row-start-1 lg:row-span-2 lg:justify-self-end">
            <Button
              type="button"
              variant="outline"
              size="lg"
              onClick={() => setSchedule(applyMondayHours)}
            >
              Apply Monday&apos;s hours to all days
            </Button>
            <Button
              type="button"
              variant="outline"
              size="lg"
              onClick={() => setSchedule(markWeekendClosed)}
            >
              Mark weekend closed
            </Button>
          </CardAction>
        </CardHeader>

        <CardContent className="px-0 pb-2">
          <Separator />
          <div className="divide-y divide-border">
            {schedule.map((day, dayIndex) => (
              <ScheduleRow
                key={day.day}
                day={day}
                dayIndex={dayIndex}
                onOpenChange={(index, isOpen) =>
                  setSchedule((current) => setDayOpen(current, index, isOpen))
                }
                onSlotChange={handleSlotChange}
                onAddSlot={(index) =>
                  setSchedule((current) => addTimeSlot(current, index))
                }
                onRemoveSlot={(index, slotIndex) =>
                  setSchedule((current) => removeTimeSlot(current, index, slotIndex))
                }
              />
            ))}
          </div>
        </CardContent>
      </OnboardingCard>
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
            disabled={isLoading || isSaving || !isValid}
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
      currentStep={3}
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
            onClick={() => router.push("/onboarding/business-profile")}
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
              router.push("/onboarding/fulfillment");
            }}
          >
            Skip for now
          </Button>
          <Button
            type="button"
            size="lg"
            disabled={isLoading || isSaving || !isValid}
            onClick={() => void persist("/onboarding/fulfillment")}
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
        stepLabel="Step 3 of 8"
        title="When are you open?"
        subtitle="Customers can only order during open hours."
      />
      {content}
    </OnboardingShell>
  );
}
