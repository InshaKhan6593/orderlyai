import Link from "next/link";
import { Check, LogOut } from "lucide-react";

import { Logo } from "@/components/brand/logo";
import { ONBOARDING_STEPS } from "@/lib/onboarding-steps";
import { cn } from "@/lib/utils";

type OnboardingShellProps = {
  /** 1-based index of the active step. */
  currentStep: number;
  children: React.ReactNode;
  /** Right-aligned actions in the sticky footer (e.g. Continue button). */
  footer?: React.ReactNode;
  /** Per-step width override for the centered content area. */
  contentClassName?: string;
  /** Per-step layout override for the main scroll area. */
  mainClassName?: string;
  /** Per-step alignment override for footer actions. */
  footerClassName?: string;
  /** Per-step spacing override for the sticky footer container. */
  footerContainerClassName?: string;
  /**
   * When provided, "Save & exit" runs this handler (persist current progress,
   * then navigate) instead of just linking away and discarding unsaved input.
   */
  onSaveExit?: () => void;
};

export function OnboardingShell({
  currentStep,
  children,
  footer,
  contentClassName,
  mainClassName,
  footerClassName,
  footerContainerClassName,
  onSaveExit,
}: OnboardingShellProps) {
  const total = ONBOARDING_STEPS.length;
  const progress = Math.round((currentStep / total) * 100);
  const active = ONBOARDING_STEPS[currentStep - 1];

  return (
    <div className="flex h-svh overflow-hidden bg-white text-foreground">
      <aside className="hidden w-[280px] shrink-0 flex-col justify-between border-r border-border/80 bg-white px-7 py-8 md:flex lg:w-[340px] lg:px-8">
        <div>
          <Logo size="lg" />

          <nav className="mt-12 flex flex-col">
            {ONBOARDING_STEPS.map((step, i) => {
              const state =
                step.num < currentStep
                  ? "done"
                  : step.num === currentStep
                    ? "current"
                    : "upcoming";
              const isLast = i === total - 1;

              return (
                <div
                  key={step.num}
                  className={cn("relative flex gap-4 pb-5", isLast && "pb-0")}
                >
                  <div className="relative flex w-8 shrink-0 justify-center">
                    {!isLast && (
                      <span
                        className={cn(
                          "absolute top-8 bottom-[-0.75rem] left-1/2 -translate-x-1/2",
                          step.num <= currentStep
                            ? "w-px bg-primary"
                            : "border-l border-dashed border-border",
                        )}
                      />
                    )}
                    <span
                      className={cn(
                        "relative z-10 grid size-8 shrink-0 place-items-center rounded-full border bg-white text-sm leading-none font-medium transition-colors",
                        state === "current" &&
                          "border-primary bg-primary text-primary-foreground shadow-[0_6px_16px_-7px_rgba(22,163,74,0.7)]",
                        state === "done" &&
                          "border-primary bg-primary text-primary-foreground",
                        state === "upcoming" &&
                          "border-border text-muted-foreground shadow-[0_1px_3px_rgba(15,23,42,0.08)]",
                      )}
                    >
                      {state === "done" ? (
                        <Check className="size-3.5" />
                      ) : (
                        step.num
                      )}
                    </span>
                  </div>

                  <div className="min-w-0 pt-0.5">
                    <p
                      className={cn(
                        "text-base leading-tight font-medium",
                        state === "current" ? "text-primary" : "text-foreground",
                      )}
                    >
                      {step.title}
                    </p>
                    <p className="mt-1.5 text-sm leading-tight text-[#2F5078]">
                      {step.subtitle}
                    </p>
                  </div>
                </div>
              );
            })}
          </nav>
        </div>

        {onSaveExit ? (
          <button
            type="button"
            onClick={onSaveExit}
            className="flex items-center gap-3 px-1 text-base text-foreground transition-colors hover:text-primary"
          >
            <LogOut className="size-5" />
            Save &amp; exit
          </button>
        ) : (
          <Link
            href="/login"
            className="flex items-center gap-3 px-1 text-base text-foreground transition-colors hover:text-primary"
          >
            <LogOut className="size-5" />
            Save &amp; exit
          </Link>
        )}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col bg-[radial-gradient(ellipse_at_50%_33%,rgba(22,163,74,0.095)_0%,rgba(22,163,74,0.045)_31%,rgba(255,255,255,0)_64%),linear-gradient(180deg,#ffffff_0%,#fbfffd_48%,#ffffff_100%)]">
        <div className="border-b border-border/80 bg-white px-5 py-3 md:hidden">
          <div className="flex items-center justify-between gap-4">
            <Logo withWordmark={false} />
            <span className="text-sm font-medium text-muted-foreground">
              Step {currentStep} of {total} &middot; {active?.title}
            </span>
          </div>
          <div className="mt-3 h-1 w-full rounded-full bg-border">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        <div className="hidden px-8 pt-8 md:block">
          <div className="h-1 w-full rounded-full bg-border">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        <main
          className={cn(
            "relative flex min-h-0 flex-1 items-center justify-center overflow-y-auto px-6 py-10 sm:px-10",
            mainClassName,
          )}
        >
          <div className={cn("w-full max-w-[680px]", contentClassName)}>
            {children}
          </div>
        </main>

        {footer && (
          <div
            className={cn(
              "border-t border-border/80 bg-white/95 px-6 py-3 backdrop-blur sm:px-9",
              footerContainerClassName,
            )}
          >
            <div
              className={cn(
                "flex flex-wrap items-center justify-end gap-3",
                footerClassName,
              )}
            >
              {footer}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
