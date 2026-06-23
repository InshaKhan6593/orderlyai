"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  Info,
  Link2,
} from "lucide-react";
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
import { CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from "@/components/ui/input-group";
import { Spinner } from "@/components/ui/spinner";
import { ApiError } from "@/lib/auth";
import { listBusinesses, type Business } from "@/lib/business-profile";
import { saveOnboardingResumePath } from "@/lib/onboarding-progress";
import {
  createWhatsAppConnectionValues,
  getWhatsAppConnection,
  saveWhatsAppConnection,
  type WhatsAppConnectionOut,
  type WhatsAppConnectionValues,
} from "@/lib/whatsapp-connection";

type WhatsAppBusiness = Pick<Business, "id" | "name">;

type WhatsAppConnectionInitialState = {
  accessToken: string;
  business: WhatsAppBusiness;
  connection: WhatsAppConnectionOut;
};

type WhatsAppConnectionFormProps = {
  initialState?: WhatsAppConnectionInitialState;
};

function accessTokenFromStorage(): string | null {
  return (
    window.localStorage.getItem("orderly.access_token") ??
    window.sessionStorage.getItem("orderly.access_token")
  );
}

function isBlank(value: string): boolean {
  return value.trim().length === 0;
}

export function WhatsAppConnectionForm({
  initialState,
}: WhatsAppConnectionFormProps) {
  const router = useRouter();
  const [accessToken, setAccessToken] = useState(initialState?.accessToken ?? "");
  const [business, setBusiness] = useState<WhatsAppBusiness | null>(
    initialState?.business ?? null,
  );
  const [connection, setConnection] = useState<WhatsAppConnectionOut | null>(
    initialState?.connection ?? null,
  );
  const [values, setValues] = useState<WhatsAppConnectionValues>(() =>
    createWhatsAppConnectionValues(initialState?.connection),
  );
  const [isLoading, setIsLoading] = useState(!initialState);
  const [isSaving, setIsSaving] = useState(false);
  const [showToken, setShowToken] = useState(false);
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
        const selected =
          businesses.find((item) => item.status === "onboarding") ?? businesses[0];
        if (!selected) {
          throw new ApiError("Complete your business profile first.", 400);
        }
        const saved = await getWhatsAppConnection({
          accessToken: token,
          businessId: selected.id,
        });
        if (!active) return;
        setAccessToken(token);
        setBusiness(selected);
        setConnection(saved);
        setValues(createWhatsAppConnectionValues(saved));
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
            : "We couldn't load your WhatsApp connection.",
        );
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [initialState, router]);

  function patch(next: Partial<WhatsAppConnectionValues>) {
    setValues((current) => ({ ...current, ...next }));
  }

  function handleSaveExit() {
    saveOnboardingResumePath("/onboarding/whatsapp");
    router.push("/login");
  }

  const hasSavedToken = connection?.has_access_token ?? false;
  const tokenRequired = !hasSavedToken;
  const missingWabaId = isBlank(values.wabaId);
  const missingPhoneNumberId = isBlank(values.phoneNumberId);
  const missingAccessToken = tokenRequired && isBlank(values.accessToken);
  const isConfigured = connection?.status === "configured" || connection?.status === "verified";

  async function persist(nextPath?: string) {
    if (!business || !accessToken) {
      toast.error("WhatsApp connection is still loading. Try again in a moment.");
      return;
    }
    if (missingWabaId || missingPhoneNumberId || missingAccessToken) {
      setShowErrors(true);
      toast.error("Add the required Meta WhatsApp details before saving.");
      return;
    }

    setIsSaving(true);
    try {
      const saved = await saveWhatsAppConnection({
        accessToken,
        businessId: business.id,
        values,
      });
      setConnection(saved);
      setValues(createWhatsAppConnectionValues(saved));
      saveOnboardingResumePath(nextPath ?? "/onboarding/whatsapp");
      if (nextPath) {
        router.push(nextPath);
      } else {
        toast.success("WhatsApp test connection saved.");
      }
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't save your WhatsApp connection.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <OnboardingShell
      currentStep={7}
      contentClassName={ONBOARDING_CONTENT_CLASS_NAME}
      mainClassName={ONBOARDING_MAIN_CLASS_NAME}
      footerClassName="grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2"
      onSaveExit={handleSaveExit}
      footer={
        <>
          <Button
            type="button"
            variant="outline"
            size="lg"
            onClick={() => router.push("/onboarding/assistant")}
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
              saveOnboardingResumePath("/onboarding/whatsapp");
              router.push("/onboarding/review");
            }}
          >
            Skip for now
          </Button>
          <Button
            type="button"
            size="lg"
            disabled={isLoading || isSaving}
            onClick={() => void persist("/onboarding/review")}
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
        stepLabel="Step 7 of 8"
        title="Connect your WhatsApp number"
        subtitle="Connect a number so customers can chat with your ordering assistant."
      />
      <div className="mt-2 flex justify-center">
        <Badge variant="outline" className="h-7 border-border bg-background px-3 text-muted-foreground">
          Optional
        </Badge>
      </div>

      <div className="mt-4 flex flex-col gap-3">
        <OnboardingCard>
          <CardContent className="flex flex-col items-center px-5 py-5 text-center">
            <Image
              src="/onboarding-whatsapp-phone.png"
              alt="WhatsApp phone connection"
              width={220}
              height={165}
              priority
              className="h-auto w-[200px] sm:w-[220px]"
            />
            <div className="mt-3 flex flex-wrap items-center justify-center gap-3">
              <span className="text-sm font-medium text-foreground">Connection status</span>
              <Badge variant={isConfigured ? "secondary" : "outline"} className="h-7 gap-2 px-3">
                {isConfigured ? <CheckCircle2 /> : <span className="size-2 rounded-full bg-muted-foreground" />}
                {isConfigured ? "Configured" : "Disconnected"}
              </Badge>
            </div>
            <div className="mt-4 flex w-full max-w-[460px] flex-col gap-2 sm:flex-row">
              <Button type="button" size="lg" className="h-10 flex-1" disabled>
                <Link2 data-icon="inline-start" />
                Connect WhatsApp
              </Button>
              <Badge variant="outline" className="h-10 justify-center px-3 text-muted-foreground">
                Coming soon
              </Badge>
            </div>
            <p className="mt-3 max-w-[520px] text-sm text-muted-foreground">
              Self-serve Meta Embedded Signup will be available later. For now, paste your Meta test number details below.
            </p>
          </CardContent>
        </OnboardingCard>

        <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-amber-950">
          <div className="flex gap-3">
            <AlertTriangle className="mt-0.5 shrink-0" aria-hidden="true" />
            <div>
              <p className="font-medium">Use a separate number</p>
              <p className="mt-1 text-sm leading-relaxed">
                The number connected to Cloud API cannot also run in the normal WhatsApp or WhatsApp Business app.
              </p>
            </div>
          </div>
        </div>

        <OnboardingCard>
          <CardHeader className="px-5 py-4 lg:px-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle className="font-sans text-lg">Use your Meta test number</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  For your test number, paste the values from Meta. Clients provide the same WABA ID, phone number ID, and token for manual onboarding.
                </p>
              </div>
              <Badge variant="outline">Advanced</Badge>
            </div>
          </CardHeader>
          <CardContent className="px-5 pb-5 lg:px-6">
            {isLoading ? (
              <div className="grid min-h-[244px] place-items-center">
                <Spinner />
              </div>
            ) : (
              <FieldGroup className="gap-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field data-invalid={showErrors && missingWabaId}>
                    <FieldLabel htmlFor="whatsapp-waba-id">WABA ID</FieldLabel>
                    <Input
                      id="whatsapp-waba-id"
                      value={values.wabaId}
                      onChange={(event) => patch({ wabaId: event.target.value })}
                      placeholder="e.g. 123456789012345"
                      className="h-10"
                      aria-invalid={showErrors && missingWabaId}
                    />
                    <FieldDescription>WhatsApp Business Account ID.</FieldDescription>
                    <FieldError>
                      {showErrors && missingWabaId ? "WABA ID is required." : null}
                    </FieldError>
                  </Field>

                  <Field data-invalid={showErrors && missingPhoneNumberId}>
                    <FieldLabel htmlFor="whatsapp-phone-number-id">
                      Phone number ID
                    </FieldLabel>
                    <Input
                      id="whatsapp-phone-number-id"
                      value={values.phoneNumberId}
                      onChange={(event) =>
                        patch({ phoneNumberId: event.target.value })
                      }
                      placeholder="e.g. 987654321098765"
                      className="h-10"
                      aria-invalid={showErrors && missingPhoneNumberId}
                    />
                    <FieldDescription>Used when sending replies through Graph API.</FieldDescription>
                    <FieldError>
                      {showErrors && missingPhoneNumberId
                        ? "Phone number ID is required."
                        : null}
                    </FieldError>
                  </Field>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <Field>
                    <FieldLabel htmlFor="whatsapp-display-phone">
                      Display phone number
                    </FieldLabel>
                    <Input
                      id="whatsapp-display-phone"
                      value={values.displayPhoneNumber}
                      onChange={(event) =>
                        patch({ displayPhoneNumber: event.target.value })
                      }
                      placeholder="+1 555 010 1234"
                      className="h-10"
                    />
                    <FieldDescription>Optional, used for dashboard context.</FieldDescription>
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="whatsapp-display-name">Display name</FieldLabel>
                    <Input
                      id="whatsapp-display-name"
                      value={values.displayName}
                      onChange={(event) => patch({ displayName: event.target.value })}
                      placeholder={`${business?.name ?? "The Green Bistro"} Bot`}
                      className="h-10"
                    />
                    <FieldDescription>Optional label for this connection.</FieldDescription>
                  </Field>
                </div>

                <Field data-invalid={showErrors && missingAccessToken}>
                  <FieldLabel htmlFor="whatsapp-access-token">Access token</FieldLabel>
                  <InputGroup className="h-10">
                    <InputGroupInput
                      id="whatsapp-access-token"
                      type={showToken ? "text" : "password"}
                      value={values.accessToken}
                      onChange={(event) =>
                        patch({ accessToken: event.target.value })
                      }
                      placeholder={
                        hasSavedToken
                          ? "Saved token; leave blank to keep it"
                          : "Paste Meta access token"
                      }
                      aria-invalid={showErrors && missingAccessToken}
                    />
                    <InputGroupAddon align="inline-end">
                      <InputGroupButton
                        size="icon-xs"
                        aria-label={showToken ? "Hide access token" : "Show access token"}
                        onClick={() => setShowToken((current) => !current)}
                      >
                        {showToken ? <EyeOff /> : <Eye />}
                      </InputGroupButton>
                    </InputGroupAddon>
                  </InputGroup>
                  <FieldDescription>
                    Write-only in OrderlyAI responses. Leave blank after saving to keep the existing token.
                  </FieldDescription>
                  <FieldError>
                    {showErrors && missingAccessToken
                      ? "Access token is required for the first save."
                      : null}
                  </FieldError>
                </Field>

                <div className="rounded-lg border border-border bg-muted/25 px-4 py-3">
                  <div className="flex gap-3">
                    <Info className="mt-0.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                    <p className="text-sm leading-relaxed text-muted-foreground">
                      OrderlyAI provides the webhook callback URL and verify token. A client does not need to give those if they connect through your Meta app.
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <Button
                    type="button"
                    variant="outline"
                    size="lg"
                    disabled={isSaving}
                    onClick={() => void persist()}
                    className="h-10 min-w-[150px]"
                  >
                    {isSaving ? <Spinner data-icon="inline-start" /> : null}
                    Save test connection
                  </Button>
                  {hasSavedToken ? (
                    <span className="text-sm text-muted-foreground">
                      Access token saved.
                    </span>
                  ) : null}
                </div>
              </FieldGroup>
            )}
          </CardContent>
        </OnboardingCard>
      </div>
    </OnboardingShell>
  );
}
