import type { ComponentProps } from "react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export const ONBOARDING_CONTENT_CLASS_NAME = "max-w-[1040px]";
export const ONBOARDING_MAIN_CLASS_NAME = "items-start py-6 sm:px-8";
export const ONBOARDING_CARD_CLASS_NAME =
  "gap-0 overflow-hidden rounded-lg border-border bg-card py-0 shadow-[0_10px_28px_-22px_rgba(15,23,42,0.5)]";

type OnboardingStepHeaderProps = Omit<ComponentProps<"header">, "children"> & {
  stepLabel: string;
  title: string;
  subtitle: string;
};

export function OnboardingStepHeader({
  stepLabel,
  title,
  subtitle,
  className,
  ...props
}: OnboardingStepHeaderProps) {
  return (
    <header
      data-onboarding-step-header={true}
      className={cn("flex flex-col items-center text-center", className)}
      {...props}
    >
      <Badge variant="outline" className="h-7 border-primary/20 bg-primary/5 px-4 text-sm text-primary">
        {stepLabel}
      </Badge>
      <h1 className="mt-2 font-heading text-3xl leading-tight font-semibold text-[#0A3B2F] sm:text-[34px]">
        {title}
      </h1>
      <p className="mt-1.5 text-sm text-[#263955] sm:text-base">{subtitle}</p>
    </header>
  );
}

type OnboardingCardProps = ComponentProps<typeof Card>;

export function OnboardingCard({ className, ...props }: OnboardingCardProps) {
  return (
    <Card
      data-onboarding-card={true}
      className={cn(ONBOARDING_CARD_CLASS_NAME, className)}
      {...props}
    />
  );
}
