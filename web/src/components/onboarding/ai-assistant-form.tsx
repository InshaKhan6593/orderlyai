"use client";

import { ArrowLeft, ArrowRight, Bot, MessageCircle } from "lucide-react";
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
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  createAgentConfigValues,
  getAgentConfig,
  saveAgentConfig,
  type AgentConfigOut,
  type AgentConfigValues,
} from "@/lib/ai-assistant";
import { ApiError, clearTokens } from "@/lib/auth";
import {
  pickBusinessForOwner,
  saveSelectedBusinessId,
} from "@/lib/business-selection";
import { listBusinesses, type Business } from "@/lib/business-profile";
import { saveOnboardingResumePath } from "@/lib/onboarding-progress";

type AssistantBusiness = Pick<Business, "id" | "name" | "helpline_phone">;

type AIAssistantInitialState = {
  accessToken: string;
  business: AssistantBusiness;
  config: AgentConfigOut;
};

type AIAssistantFormProps = {
  initialState?: AIAssistantInitialState;
  variant?: "onboarding" | "settings";
  onSaved?: () => void;
};

function accessTokenFromStorage(): string | null {
  return (
    window.localStorage.getItem("orderly.access_token") ??
    window.sessionStorage.getItem("orderly.access_token")
  );
}

function PreviewBubble({
  children,
  align = "left",
}: {
  children: React.ReactNode;
  align?: "left" | "right";
}) {
  return (
    <div
      className={
        align === "right"
          ? "ml-auto max-w-[82%] rounded-xl rounded-br-sm bg-primary/10 px-4 py-3 text-sm leading-relaxed text-foreground"
          : "max-w-[78%] rounded-xl rounded-bl-sm border border-border bg-background px-4 py-3 text-sm leading-relaxed text-foreground shadow-sm"
      }
    >
      {children}
    </div>
  );
}

export function AIAssistantForm({
  initialState,
  variant = "onboarding",
  onSaved,
}: AIAssistantFormProps) {
  const router = useRouter();
  const isSettings = variant === "settings";
  const [accessToken, setAccessToken] = useState(initialState?.accessToken ?? "");
  const [business, setBusiness] = useState<AssistantBusiness | null>(
    initialState?.business ?? null,
  );
  const [values, setValues] = useState<AgentConfigValues>(() =>
    initialState
      ? createAgentConfigValues(initialState.business, initialState.config)
      : {
          greetingMessage: "",
          upsellEnabled: true,
          humanHandoffPhone: "",
          extraInstructions: "",
        },
  );
  const [isLoading, setIsLoading] = useState(!initialState);
  const [isSaving, setIsSaving] = useState(false);
  const [showErrors, setShowErrors] = useState(false);

  useEffect(() => {
    if (initialState) return;
    const token = accessTokenFromStorage();
    if (!token) {
      toast.error("Please sign in to continue.");
      router.replace("/login");
      return;
    }

    let active = true;
    void listBusinesses(token)
      .then(async (businesses) => {
        const selected = pickBusinessForOwner(businesses);
        if (!selected) {
          throw new ApiError("Complete your business profile first.", 400);
        }
        saveSelectedBusinessId(selected.id);
        const config = await getAgentConfig({
          accessToken: token,
          businessId: selected.id,
        });
        if (!active) return;
        setAccessToken(token);
        setBusiness(selected);
        setValues(createAgentConfigValues(selected, config));
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
            : "We couldn't load your assistant settings.",
        );
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [initialState, router]);

  function patch(next: Partial<AgentConfigValues>) {
    setValues((current) => ({ ...current, ...next }));
  }

  function handleSaveExit() {
    saveOnboardingResumePath("/onboarding/assistant");
    clearTokens();
    router.replace("/login");
  }

  async function persist(nextPath: string) {
    if (!business || !accessToken) {
      toast.error("Assistant settings are still loading. Try again in a moment.");
      return;
    }
    if (!values.greetingMessage.trim()) {
      setShowErrors(true);
      toast.error("Add a greeting message before continuing.");
      return;
    }
    setIsSaving(true);
    try {
      await saveAgentConfig({
        accessToken,
        businessId: business.id,
        values,
      });
      saveSelectedBusinessId(business.id);
      saveOnboardingResumePath(nextPath);
      router.push(nextPath);
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't save your assistant settings.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  const businessName = business?.name ?? "your business";
  const greeting = values.greetingMessage.trim();

  async function handleSettingsSave() {
    if (!business || !accessToken) {
      toast.error("Assistant settings are still loading. Try again in a moment.");
      return;
    }
    if (!values.greetingMessage.trim()) {
      setShowErrors(true);
      toast.error("Add a greeting message before saving.");
      return;
    }
    setIsSaving(true);
    try {
      await saveAgentConfig({ accessToken, businessId: business.id, values });
      saveSelectedBusinessId(business.id);
      onSaved?.();
      toast.success("Assistant settings saved.");
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't save your assistant settings.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  const content = (
    <div
      className={
        isSettings
          ? "grid gap-4 lg:grid-cols-[1.05fr_0.95fr]"
          : "mt-3 grid gap-4 lg:grid-cols-[1.05fr_0.95fr]"
      }
    >
        <OnboardingCard>
          <CardHeader className="px-5 py-4 lg:px-6">
            <CardTitle className="font-sans text-lg">Assistant settings</CardTitle>
            <CardDescription>
              These details will guide customer replies when WhatsApp is connected.
            </CardDescription>
          </CardHeader>
          <CardContent className="px-5 pb-5 lg:px-6">
            {isLoading ? (
              <div className="grid min-h-[320px] place-items-center">
                <Spinner />
              </div>
            ) : (
              <FieldGroup className="gap-4">
                <Field data-invalid={showErrors && !values.greetingMessage.trim()}>
                  <FieldLabel htmlFor="assistant-greeting">Greeting message</FieldLabel>
                  <Textarea
                    id="assistant-greeting"
                    value={values.greetingMessage}
                    onChange={(event) =>
                      patch({ greetingMessage: event.target.value })
                    }
                    className="min-h-24 resize-none"
                    aria-invalid={showErrors && !values.greetingMessage.trim()}
                  />
                  <FieldError>
                    {showErrors && !values.greetingMessage.trim()
                      ? "Greeting message is required."
                      : null}
                  </FieldError>
                </Field>

                <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_180px]">
                  <Field>
                    <FieldLabel htmlFor="assistant-handoff">
                      Human handoff number
                    </FieldLabel>
                    <Input
                      id="assistant-handoff"
                      value={values.humanHandoffPhone}
                      onChange={(event) =>
                        patch({ humanHandoffPhone: event.target.value })
                      }
                      placeholder="+92 300 1234567"
                      className="h-10"
                    />
                    <FieldDescription>
                      Where to route customers who ask to talk to a person.
                    </FieldDescription>
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="assistant-language">Language</FieldLabel>
                    <Input
                      id="assistant-language"
                      value="English"
                      readOnly
                      className="h-10 bg-muted/40"
                    />
                    <FieldDescription>Fixed for this build.</FieldDescription>
                  </Field>
                </div>

                <Field
                  orientation="horizontal"
                  className="rounded-lg border border-border p-3"
                >
                  <FieldContent>
                    <FieldTitle>Upsell suggestions</FieldTitle>
                    <FieldDescription>
                      Let the assistant suggest add-ons like drinks or sides.
                    </FieldDescription>
                  </FieldContent>
                  <Switch
                    size="lg"
                    checked={values.upsellEnabled}
                    onCheckedChange={(checked) =>
                      patch({ upsellEnabled: checked })
                    }
                    aria-label="Upsell suggestions"
                  />
                </Field>

                <Field>
                  <FieldLabel htmlFor="assistant-extra">FAQ / extra info</FieldLabel>
                  <Textarea
                    id="assistant-extra"
                    value={values.extraInstructions}
                    onChange={(event) =>
                      patch({ extraInstructions: event.target.value })
                    }
                    placeholder="Parking, catering, payment methods, delivery notes..."
                    className="min-h-20 resize-none"
                  />
                  <FieldDescription>
                    Anything else the assistant should know.
                  </FieldDescription>
                </Field>
              </FieldGroup>
            )}
          </CardContent>
        </OnboardingCard>

        <OnboardingCard>
          <CardHeader className="px-5 py-4 lg:px-6">
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle className="font-sans text-lg">Live preview</CardTitle>
                <CardDescription>Preview only</CardDescription>
              </div>
              <Badge variant="secondary">English</Badge>
            </div>
          </CardHeader>
          <CardContent className="px-5 pb-5 lg:px-6">
            <div className="overflow-hidden rounded-lg border border-border bg-muted/30">
              <div className="flex items-center gap-3 border-b border-border bg-background px-4 py-3">
                <span className="grid size-10 place-items-center rounded-full bg-primary/10 text-primary">
                  <Bot className="size-5" aria-hidden="true" />
                </span>
                <div>
                  <p className="font-medium text-foreground">{businessName}</p>
                  <p className="text-xs text-muted-foreground">AI assistant</p>
                </div>
              </div>
              <div className="flex min-h-[322px] flex-col gap-3 bg-[linear-gradient(135deg,var(--background),var(--muted))] p-4">
                <PreviewBubble>Hi, can I see your menu?</PreviewBubble>
                <PreviewBubble align="right">
                  {greeting || "Your greeting message will appear here."}
                </PreviewBubble>
                {values.upsellEnabled ? (
                  <PreviewBubble align="right">
                    You can add drinks or sides when you choose your meal.
                  </PreviewBubble>
                ) : null}
                {values.extraInstructions.trim() ? (
                  <PreviewBubble align="right">
                    {values.extraInstructions.trim()}
                  </PreviewBubble>
                ) : null}
              </div>
              <Separator />
              <div className="flex items-center gap-2 bg-background p-3">
                <div className="h-10 flex-1 rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
                  Preview only
                </div>
                <Button type="button" variant="outline" size="icon-lg" disabled>
                  <MessageCircle />
                </Button>
              </div>
            </div>
          </CardContent>
        </OnboardingCard>
    </div>
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
      currentStep={6}
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
            onClick={() => router.push("/onboarding/menu")}
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
              saveOnboardingResumePath("/onboarding/assistant");
              router.push("/onboarding/whatsapp");
            }}
          >
            Skip for now
          </Button>
          <Button
            type="button"
            size="lg"
            disabled={isLoading || isSaving}
            onClick={() => void persist("/onboarding/whatsapp")}
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
        stepLabel="Step 6 of 8"
        title="Set up your WhatsApp assistant"
        subtitle="Customize how your AI replies to customers on WhatsApp."
      />
      <div className="mt-2 flex justify-center">
        <Badge variant="outline" className="h-7 border-border bg-background px-3 text-muted-foreground">
          You can finish this later
        </Badge>
      </div>
      {content}
    </OnboardingShell>
  );
}
