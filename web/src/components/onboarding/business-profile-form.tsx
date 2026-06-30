"use client";

import { standardSchemaResolver } from "@hookform/resolvers/standard-schema";
import {
  ArrowLeft,
  ArrowRight,
  Coffee,
  Croissant,
  Ellipsis,
  House,
  Upload,
  UtensilsCrossed,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
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
import { CardContent } from "@/components/ui/card";
import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
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
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  businessProfileSchema,
  hasRequiredBusinessProfileFields,
  listBusinesses,
  saveBusinessProfile,
  shouldShowFieldError,
  type Business,
  type BusinessProfileValues,
} from "@/lib/business-profile";
import { ApiError, clearTokens } from "@/lib/auth";
import {
  pickBusinessForOwner,
  saveSelectedBusinessId,
} from "@/lib/business-selection";
import {
  loadOnboardingImage,
  saveOnboardingImage,
} from "@/lib/onboarding-image-store";
import { saveOnboardingResumePath } from "@/lib/onboarding-progress";
import { cn } from "@/lib/utils";

/** Marker stored in logo_url/cover_url for a locally-held (not yet uploaded) image. */
function localImagePath(file: Blob): string {
  const name = file instanceof File ? file.name : "image";
  return `local-file://${encodeURIComponent(name)}`;
}

const DEFAULT_VALUES: BusinessProfileValues = {
  name: "",
  type: "restaurant",
  description: "",
  logoPath: "",
  coverPath: "",
  timezone: "Asia/Karachi",
  currency: "PKR",
  languages: ["en"],
  phoneCountry: "+92",
  phoneNumber: "",
  email: "",
  address: "",
  mapsUrl: "",
};

const businessTypeOptions = [
  { value: "restaurant", label: "Restaurant", icon: UtensilsCrossed },
  { value: "cafe", label: "Café", icon: Coffee },
  { value: "bakery", label: "Bakery", icon: Croissant },
  { value: "home_kitchen", label: "Home Kitchen", icon: House },
  { value: "other", label: "Other", icon: Ellipsis },
] as const;

const timezoneOptions = [
  { value: "Asia/Karachi", label: "Asia/Karachi" },
  { value: "Asia/Dubai", label: "Asia/Dubai" },
  { value: "Asia/Kolkata", label: "Asia/Kolkata" },
  { value: "Asia/Dhaka", label: "Asia/Dhaka" },
  { value: "Europe/London", label: "Europe/London" },
  { value: "Europe/Paris", label: "Europe/Paris" },
  { value: "America/New_York", label: "America/New_York" },
  { value: "America/Los_Angeles", label: "America/Los_Angeles" },
  { value: "UTC", label: "UTC" },
];

const currencyOptions = [
  { value: "PKR", label: "PKR · ₨" },
  { value: "USD", label: "USD · $" },
  { value: "INR", label: "INR · ₹" },
  { value: "AED", label: "AED · د.إ" },
  { value: "GBP", label: "GBP · £" },
  { value: "EUR", label: "EUR · €" },
];

const languageOptions = [
  { value: "en", label: "English" },
  { value: "ur", label: "Urdu" },
  { value: "hi", label: "Hindi" },
  { value: "ar", label: "Arabic" },
];

const countryCodeOptions = [
  { value: "+92", label: "+92" },
  { value: "+971", label: "+971" },
  { value: "+91", label: "+91" },
  { value: "+44", label: "+44" },
  { value: "+1", label: "+1" },
];

function accessTokenFromStorage(): string | null {
  return (
    window.localStorage.getItem("orderly.access_token") ??
    window.sessionStorage.getItem("orderly.access_token")
  );
}

function valuesFromBusiness(business: Business): BusinessProfileValues {
  const phoneMatch = business.helpline_phone?.match(/^(\+\d+)\s*(.*)$/);
  return {
    name: business.name,
    type: business.type,
    description: business.description ?? "",
    logoPath: business.logo_url ?? "",
    coverPath: business.cover_url ?? "",
    timezone: business.timezone,
    currency: business.currency,
    languages: business.languages.length > 0 ? business.languages : ["en"],
    phoneCountry: phoneMatch?.[1] ?? "+92",
    phoneNumber: phoneMatch?.[2] ?? "",
    email: business.email ?? "",
    address: business.address ?? "",
    mapsUrl: business.maps_url ?? "",
  };
}

type ImageUploaderProps = {
  id: string;
  label: string;
  helper: string;
  aspect: "square" | "cover";
  previewUrl?: string;
  onFile: (file: File, previewUrl: string) => void;
};

function ImageUploader({
  id,
  label,
  helper,
  aspect,
  previewUrl,
  onFile,
}: ImageUploaderProps) {
  return (
    <Field>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <label
        htmlFor={id}
        className={cn(
          "group grid cursor-pointer place-items-center overflow-hidden rounded-lg border border-dashed border-muted-foreground/45 bg-background transition-colors hover:border-primary hover:bg-primary/5",
          aspect === "square" ? "size-[136px]" : "h-[116px] w-full",
        )}
      >
        {previewUrl ? (
          // A blob URL is required here because uploads are local-only in this phase.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={previewUrl}
            alt={`${label} preview`}
            className="size-full object-cover"
          />
        ) : (
          <span className="flex flex-col items-center gap-2 text-center text-muted-foreground">
            <span className="grid size-9 place-items-center text-foreground">
              <Upload className="size-7 stroke-[1.5]" />
            </span>
            <span className="text-xs">{helper}</span>
          </span>
        )}
      </label>
      <Input
        id={id}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file, URL.createObjectURL(file));
        }}
      />
    </Field>
  );
}

type BusinessProfileFormProps = {
  variant?: "onboarding" | "settings";
  onSaved?: (business: Business) => void;
};

export function BusinessProfileForm({
  variant = "onboarding",
  onSaved,
}: BusinessProfileFormProps = {}) {
  const router = useRouter();
  const isSettings = variant === "settings";
  const [businessId, setBusinessId] = useState<string>();
  const [isLoadingProfile, setIsLoadingProfile] = useState(true);
  const [logoPreview, setLogoPreview] = useState<string>();
  const [coverPreview, setCoverPreview] = useState<string>();

  const {
    control,
    handleSubmit,
    register,
    reset,
    setValue,
    getValues,
    formState: { errors, isSubmitting, isValid, submitCount, touchedFields },
  } = useForm<BusinessProfileValues>({
    resolver: standardSchemaResolver(businessProfileSchema),
    mode: "onChange",
    defaultValues: DEFAULT_VALUES,
  });

  const description = useWatch({ control, name: "description" });
  const [businessName, businessType, timezone, currency] = useWatch({
    control,
    name: ["name", "type", "timezone", "currency"],
  });
  const hasRequiredFields = hasRequiredBusinessProfileFields({
    name: businessName,
    type: businessType,
    timezone,
    currency,
  });
  const showNameError = shouldShowFieldError(
    Boolean(errors.name),
    Boolean(touchedFields.name),
    submitCount,
  );

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
        if (!active) return;
        const business = pickBusinessForOwner(businesses);
        if (business) {
          saveSelectedBusinessId(business.id);
          setBusinessId(business.id);
          reset(valuesFromBusiness(business));
          if (business.logo_url?.startsWith("http")) {
            setLogoPreview(business.logo_url);
          }
          if (business.cover_url?.startsWith("http")) {
            setCoverPreview(business.cover_url);
          }
        }

        // Restore locally-persisted images (interim, until real upload exists).
        // Runs even with no business yet, since images can be picked before the
        // first save. A real http logo/cover from the backend takes precedence.
        const [logoBlob, coverBlob] = await Promise.all([
          loadOnboardingImage("logo").catch(() => null),
          loadOnboardingImage("cover").catch(() => null),
        ]);
        if (!active) return;
        if (logoBlob && !business?.logo_url?.startsWith("http")) {
          setLogoPreview(URL.createObjectURL(logoBlob));
          setValue("logoPath", localImagePath(logoBlob), { shouldDirty: false });
        }
        if (coverBlob && !business?.cover_url?.startsWith("http")) {
          setCoverPreview(URL.createObjectURL(coverBlob));
          setValue("coverPath", localImagePath(coverBlob), { shouldDirty: false });
        }
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          toast.error("Your session has expired. Please sign in again.");
          router.replace("/login");
          return;
        }
        toast.error("We couldn't load your saved profile.", {
          description: "You can still complete the form and try saving again.",
        });
      })
      .finally(() => {
        if (active) setIsLoadingProfile(false);
      });

    return () => {
      active = false;
    };
  }, [reset, router, setValue]);

  async function onSubmit(values: BusinessProfileValues) {
    const accessToken = accessTokenFromStorage();
    if (!accessToken) {
      toast.error("Please sign in to continue.");
      router.replace("/login");
      return;
    }

    try {
      const saved = await saveBusinessProfile({
        accessToken,
        values,
        existingBusinessId: businessId,
      });
      setBusinessId(saved.id);
      saveSelectedBusinessId(saved.id);
      if (isSettings) {
        reset(valuesFromBusiness(saved));
        if (saved.logo_url?.startsWith("http")) setLogoPreview(saved.logo_url);
        if (saved.cover_url?.startsWith("http")) setCoverPreview(saved.cover_url);
        onSaved?.(saved);
        toast.success("Business profile saved.");
        return;
      }
      saveOnboardingResumePath("/onboarding/hours");
      toast.success("Business profile saved.");
      router.push("/onboarding/hours");
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't save your business profile. Please try again.",
      );
    }
  }

  async function handleSaveExit() {
    const accessToken = accessTokenFromStorage();
    if (!accessToken) {
      router.replace("/login");
      return;
    }

    const values = getValues();
    // Nothing to persist yet (no business created and required fields blank) —
    // just leave rather than erroring on an empty create.
    if (!businessId && !hasRequiredBusinessProfileFields(values)) {
      saveOnboardingResumePath("/onboarding/business-profile");
      clearTokens();
      router.replace("/login");
      return;
    }

    try {
      const saved = await saveBusinessProfile({
        accessToken,
        values,
        existingBusinessId: businessId,
      });
      setBusinessId(saved.id);
      saveSelectedBusinessId(saved.id);
      saveOnboardingResumePath("/onboarding/hours");
      toast.success("Progress saved.");
      clearTokens();
      router.replace("/login");
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : "Couldn't save your progress. Please try again.",
      );
    }
  }

  const isBusy = isLoadingProfile || isSubmitting;

  const formContent = (
    <form
      id="business-profile-form"
      className={isSettings ? "" : "mt-3"}
      onSubmit={handleSubmit(onSubmit)}
    >
        <OnboardingCard>
          <CardContent className="p-0">
            <div className="grid lg:grid-cols-[0.62fr_1fr]">
              <div className="grid gap-4 border-b border-border p-5 sm:grid-cols-2 lg:grid-cols-1 lg:border-r lg:border-b-0 lg:p-6">
                <ImageUploader
                  id="business-logo"
                  label="Logo"
                  helper="Upload a square image"
                  aspect="square"
                  previewUrl={logoPreview}
                  onFile={(file, previewUrl) => {
                    if (logoPreview?.startsWith("blob:")) URL.revokeObjectURL(logoPreview);
                    setLogoPreview(previewUrl);
                    setValue("logoPath", localImagePath(file), { shouldDirty: true });
                    void saveOnboardingImage("logo", file).catch(() => {});
                  }}
                />
                <ImageUploader
                  id="business-cover"
                  label="Cover image"
                  helper="Optional · JPG or PNG"
                  aspect="cover"
                  previewUrl={coverPreview}
                  onFile={(file, previewUrl) => {
                    if (coverPreview?.startsWith("blob:")) URL.revokeObjectURL(coverPreview);
                    setCoverPreview(previewUrl);
                    setValue("coverPath", localImagePath(file), { shouldDirty: true });
                    void saveOnboardingImage("cover", file).catch(() => {});
                  }}
                />
              </div>

              <FieldGroup className="gap-3 p-5 lg:p-6">
                <Field data-invalid={showNameError}>
                  <FieldLabel htmlFor="business-name">Business name *</FieldLabel>
                  <Input
                    id="business-name"
                    placeholder="e.g. The Green Bistro"
                    aria-invalid={showNameError}
                    className="h-11"
                    {...register("name")}
                  />
                  <FieldError errors={showNameError ? [errors.name] : []} />
                </Field>

                <Controller
                  name="type"
                  control={control}
                  render={({ field }) => (
                    <FieldSet>
                      <FieldLegend variant="label">Business type *</FieldLegend>
                      <ToggleGroup
                        value={[field.value]}
                        onValueChange={(value) => {
                          if (value[0]) field.onChange(value[0]);
                        }}
                        variant="outline"
                        spacing={2}
                        className="grid w-full grid-cols-2 sm:grid-cols-5"
                        aria-label="Business type"
                      >
                        {businessTypeOptions.map((option) => {
                          const Icon = option.icon;
                          return (
                            <ToggleGroupItem
                              key={option.value}
                              value={option.value}
                              className="h-[72px] min-w-0 flex-col gap-1.5 px-2 aria-pressed:border-primary aria-pressed:bg-primary/5 aria-pressed:text-primary"
                            >
                              <Icon className="size-5" />
                              <span className="text-xs sm:text-sm">{option.label}</span>
                            </ToggleGroupItem>
                          );
                        })}
                      </ToggleGroup>
                      <FieldError errors={[errors.type]} />
                    </FieldSet>
                  )}
                />

                <Field data-invalid={Boolean(errors.description)}>
                  <FieldLabel htmlFor="business-description">Tagline / description</FieldLabel>
                  <div className="relative">
                    <Textarea
                      id="business-description"
                      placeholder="Tell customers what makes your business special..."
                      maxLength={160}
                      aria-invalid={Boolean(errors.description)}
                      className="min-h-[72px] resize-none pb-7"
                      {...register("description")}
                    />
                    <span className="pointer-events-none absolute right-3 bottom-2 text-xs text-muted-foreground">
                      {description.length} / 160
                    </span>
                  </div>
                  <FieldError errors={[errors.description]} />
                </Field>
              </FieldGroup>
            </div>

            <Separator />

            <div className="grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-[1.05fr_0.72fr_1.45fr] lg:px-6">
              <Controller
                name="timezone"
                control={control}
                render={({ field }) => (
                  <Field data-invalid={Boolean(errors.timezone)}>
                    <FieldLabel>Timezone *</FieldLabel>
                    <Select
                      items={timezoneOptions}
                      value={field.value}
                      onValueChange={field.onChange}
                    >
                      <SelectTrigger className="h-11 w-full" aria-invalid={Boolean(errors.timezone)}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent alignItemWithTrigger={false}>
                        <SelectGroup>
                          {timezoneOptions.map((timezone) => (
                            <SelectItem key={timezone.value} value={timezone.value}>
                              {timezone.label}
                            </SelectItem>
                          ))}
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                    <FieldError errors={[errors.timezone]} />
                  </Field>
                )}
              />

              <Controller
                name="currency"
                control={control}
                render={({ field }) => (
                  <Field data-invalid={Boolean(errors.currency)}>
                    <FieldLabel>Currency *</FieldLabel>
                    <Select
                      items={currencyOptions}
                      value={field.value}
                      onValueChange={field.onChange}
                    >
                      <SelectTrigger className="h-11 w-full" aria-invalid={Boolean(errors.currency)}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent alignItemWithTrigger={false}>
                        <SelectGroup>
                          {currencyOptions.map((currency) => (
                            <SelectItem key={currency.value} value={currency.value}>
                              {currency.label}
                            </SelectItem>
                          ))}
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                    <FieldError errors={[errors.currency]} />
                  </Field>
                )}
              />

              <Controller
                name="languages"
                control={control}
                render={({ field }) => (
                  <Field data-invalid={Boolean(errors.languages)} className="sm:col-span-2 lg:col-span-1">
                    <FieldLabel>Languages</FieldLabel>
                    <Select
                      items={languageOptions}
                      multiple
                      value={field.value}
                      onValueChange={field.onChange}
                    >
                      <SelectTrigger className="h-11 w-full" aria-invalid={Boolean(errors.languages)}>
                        <SelectValue>
                          {(values: string[]) => (
                            <span className="flex gap-1">
                              {values.map((value) => (
                                <Badge key={value} variant="secondary">
                                  {languageOptions.find((item) => item.value === value)?.label ?? value}
                                </Badge>
                              ))}
                            </span>
                          )}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent alignItemWithTrigger={false}>
                        <SelectGroup>
                          {languageOptions.map((language) => (
                            <SelectItem key={language.value} value={language.value}>
                              {language.label}
                            </SelectItem>
                          ))}
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                    <FieldError errors={[errors.languages]} />
                  </Field>
                )}
              />
            </div>

            <div className="px-5 lg:px-6">
              <Separator />
            </div>

            <div className="p-4 lg:px-6 lg:pb-5">
              <div className="mb-3">
                <h2 className="text-lg font-medium text-foreground">Contact &amp; info</h2>
                <p className="text-sm text-muted-foreground">
                  Shown to customers and used by your assistant.
                </p>
              </div>

              <FieldGroup className="grid gap-4 md:grid-cols-2">
                <Field>
                  <FieldLabel>Helpline / contact phone</FieldLabel>
                  <div className="grid grid-cols-[104px_1fr] gap-3">
                    <Controller
                      name="phoneCountry"
                      control={control}
                      render={({ field }) => (
                        <Select
                          items={countryCodeOptions}
                          value={field.value}
                          onValueChange={field.onChange}
                        >
                          <SelectTrigger className="h-11 w-full">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent alignItemWithTrigger={false}>
                            <SelectGroup>
                              {countryCodeOptions.map((country) => (
                                <SelectItem key={country.value} value={country.value}>
                                  {country.label}
                                </SelectItem>
                              ))}
                            </SelectGroup>
                          </SelectContent>
                        </Select>
                      )}
                    />
                    <Input
                      type="tel"
                      aria-label="Helpline phone number"
                      className="h-11"
                      {...register("phoneNumber")}
                    />
                  </div>
                </Field>

                <Field data-invalid={Boolean(errors.email)}>
                  <FieldLabel htmlFor="business-email">Public email</FieldLabel>
                  <Input
                    id="business-email"
                    type="email"
                    placeholder="hello@business.com"
                    className="h-11"
                    aria-invalid={Boolean(errors.email)}
                    {...register("email")}
                  />
                  <FieldError errors={[errors.email]} />
                </Field>

                <Field>
                  <FieldLabel htmlFor="business-address">Address</FieldLabel>
                  <Textarea
                    id="business-address"
                    placeholder="Enter your business address..."
                    className="min-h-11 resize-none"
                    {...register("address")}
                  />
                </Field>

                <Field data-invalid={Boolean(errors.mapsUrl)}>
                  <FieldLabel htmlFor="business-maps-url">Google Maps link</FieldLabel>
                  <Input
                    id="business-maps-url"
                    type="url"
                    placeholder="https://maps.google.com/..."
                    className="h-11"
                    aria-invalid={Boolean(errors.mapsUrl)}
                    {...register("mapsUrl")}
                  />
                  <FieldError errors={[errors.mapsUrl]} />
                </Field>
              </FieldGroup>
            </div>
          </CardContent>
        </OnboardingCard>
      </form>
  );

  if (isSettings) {
    return (
      <div className="flex flex-col">
        {formContent}
        <div className="mt-6 flex items-center justify-end border-t border-border pt-4">
          <Button
            type="submit"
            form="business-profile-form"
            className="h-10 min-w-[150px]"
            disabled={!hasRequiredFields || !isValid || isBusy}
          >
            {isBusy ? <Spinner data-icon="inline-start" /> : null}
            {isSubmitting ? "Saving..." : "Save changes"}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <OnboardingShell
      currentStep={2}
      onSaveExit={handleSaveExit}
      contentClassName={ONBOARDING_CONTENT_CLASS_NAME}
      mainClassName={ONBOARDING_MAIN_CLASS_NAME}
      footerClassName="w-full justify-between gap-3"
      footer={
        <>
          <Button
            type="button"
            variant="outline"
            size="lg"
            className="h-10 min-w-[104px]"
            onClick={() => router.push("/onboarding")}
          >
            <ArrowLeft data-icon="inline-start" />
            Back
          </Button>
          <Button
            type="submit"
            form="business-profile-form"
            size="lg"
            className="h-10 min-w-[136px]"
            disabled={!hasRequiredFields || !isValid || isBusy}
          >
            {isBusy ? (
              <Spinner data-icon="inline-start" />
            ) : (
              <ArrowRight data-icon="inline-end" />
            )}
            {isSubmitting ? "Saving..." : "Continue"}
          </Button>
        </>
      }
    >
      <OnboardingStepHeader
        stepLabel="Step 2 of 8"
        title="Tell us about your business"
        subtitle="This is what your customers will see."
      />
      {formContent}
    </OnboardingShell>
  );
}
