"use client";

import { ArrowLeft, ArrowRight, Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
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
import { Switch } from "@/components/ui/switch";
import {
  addTimeSlot,
  applyMondayHours,
  createDefaultBusinessHours,
  isBusinessHoursValid,
  isOvernightSlot,
  isTimeSlotValid,
  markWeekendClosed,
  removeTimeSlot,
  setDayOpen,
  TIME_OPTIONS,
  updateTimeSlot,
  type BusinessDayHours,
  type TimeSlot,
} from "@/lib/business-hours";
import { saveOnboardingResumePath } from "@/lib/onboarding-progress";

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

export function BusinessHoursForm() {
  const router = useRouter();
  const [acceptingOrders, setAcceptingOrders] = useState(true);
  const [schedule, setSchedule] = useState(createDefaultBusinessHours);
  const isValid = isBusinessHoursValid(schedule);

  function handleContinue() {
    if (!isValid) {
      toast.error("Check your hours before continuing.", {
        description: "Opening and closing times must be different.",
      });
      return;
    }
    saveOnboardingResumePath("/onboarding/fulfillment");
    router.push("/onboarding/fulfillment");
  }

  function handleSaveExit() {
    saveOnboardingResumePath(isValid ? "/onboarding/fulfillment" : "/onboarding/hours");
    router.push("/login");
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

  return (
    <OnboardingShell
      currentStep={3}
      contentClassName={ONBOARDING_CONTENT_CLASS_NAME}
      mainClassName={ONBOARDING_MAIN_CLASS_NAME}
      footerClassName="w-full justify-between gap-3"
      onSaveExit={handleSaveExit}
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
            disabled={!isValid}
            onClick={handleContinue}
            className="h-10 min-w-[136px]"
          >
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

      <OnboardingCard className="mt-3">
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
            <CardDescription className="mt-1">Timezone: Asia/Karachi</CardDescription>
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
    </OnboardingShell>
  );
}
