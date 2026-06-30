"use client";

import { ArrowRight, Check } from "lucide-react";
import { useRouter } from "next/navigation";

import { OnboardingShell } from "@/components/onboarding/onboarding-shell";
import { WelcomeIllustration } from "@/components/onboarding/welcome-illustration";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { clearTokens } from "@/lib/auth";
import { saveOnboardingResumePath } from "@/lib/onboarding-progress";

const checklist = [
  "Add your business details",
  "Set your hours and delivery",
  "Build your menu",
];

export default function OnboardingWelcomePage() {
  const router = useRouter();

  function handleStart() {
    saveOnboardingResumePath("/onboarding/business-profile");
    router.push("/onboarding/business-profile");
  }

  function handleSaveExit() {
    clearTokens();
    router.replace("/login");
  }

  return (
    <OnboardingShell
      currentStep={1}
      onSaveExit={handleSaveExit}
      footer={
        <>
          <span className="inline-flex h-11 items-center gap-2 rounded-[10px] border border-primary/20 bg-primary/5 px-4 text-sm font-medium text-primary">
            <Check className="size-4" />
            Saved
          </span>
          <Button
            size="lg"
            className="h-12 min-w-[176px] rounded-[10px] px-8 text-base"
            onClick={handleStart}
          >
            Get started
            <ArrowRight data-icon="inline-end" />
          </Button>
        </>
      }
    >
      <div className="flex flex-col items-center text-center">
        <Badge
          variant="outline"
          className="h-7 border-primary/20 bg-primary/5 px-4 text-sm text-primary"
        >
          Step 1 of 8
        </Badge>
        <h1 className="mt-6 font-heading text-4xl leading-tight font-semibold text-[#0A3B2F] sm:text-5xl">
          Welcome to OrderlyAI
        </h1>
        <p className="mt-3 text-base text-[#263955] sm:text-lg">
          Let&apos;s set up your business for WhatsApp ordering.
        </p>
      </div>

      <Card className="mt-9 gap-0 overflow-hidden rounded-[10px] border border-border bg-white py-0 shadow-[0_12px_28px_-18px_rgba(15,23,42,0.55)] ring-0">
        <div className="grid gap-7 p-7 sm:grid-cols-[1fr_0.9fr] sm:items-center sm:gap-10 sm:p-9">
          <div className="flex items-center justify-center">
            <WelcomeIllustration className="max-w-[260px]" />
          </div>
          <div>
            <h2 className="max-w-[15rem] text-lg leading-snug font-medium text-[#17233C]">
              You&apos;ll be ready to take orders in just a few steps.
            </h2>
            <ol className="mt-6 flex flex-col gap-5">
              {checklist.map((item, i) => (
                <li key={item} className="flex items-center gap-3">
                  <span className="grid size-7 shrink-0 place-items-center rounded-full border border-border bg-white text-sm font-medium text-foreground shadow-[0_1px_3px_rgba(15,23,42,0.08)]">
                    {i + 1}
                  </span>
                  <span className="text-sm text-foreground">{item}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </Card>
    </OnboardingShell>
  );
}
