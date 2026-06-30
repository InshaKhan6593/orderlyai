"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema";
import { z } from "zod";
import { toast } from "sonner";
import { ArrowRight, Eye, EyeOff, Loader2, Lock, Mail, User } from "lucide-react";

import { AuthCard } from "@/components/auth/auth-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, register as registerAccount, storeTokens } from "@/lib/auth";
import { saveOnboardingResumePath } from "@/lib/onboarding-progress";

const signupSchema = z.object({
  fullName: z.string().trim().max(255).optional(),
  email: z.email("Enter a valid email address"),
  // Backend requires 8–128 chars (RegisterIn).
  password: z
    .string()
    .min(8, "Use at least 8 characters")
    .max(128, "That password is too long"),
});

type SignupValues = z.infer<typeof signupSchema>;

/** The functional create-account form (used on /signup). */
export function SignupForm({ className }: { className?: string }) {
  const router = useRouter();
  const [showPassword, setShowPassword] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SignupValues>({
    resolver: standardSchemaResolver(signupSchema),
    defaultValues: { fullName: "", email: "", password: "" },
  });

  async function onSubmit(values: SignupValues) {
    try {
      const tokens = await registerAccount(
        values.email,
        values.password,
        values.fullName,
      );
      storeTokens(tokens);
      saveOnboardingResumePath("/onboarding");
      toast.success("Account created", {
        description: "Let's set up your business.",
      });
      router.push("/onboarding");
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Something went wrong.";
      toast.error("Couldn't create your account", { description: message });
    }
  }

  return (
    <AuthCard active="signup" className={className}>
      <div className="mt-6 mb-5 text-center">
        <h1 className="font-heading text-xl font-semibold text-foreground">
          Create your account 🎉
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Start taking WhatsApp orders in minutes.
        </p>
      </div>

      <form
        className="flex flex-col gap-4"
        onSubmit={handleSubmit(onSubmit)}
        noValidate
      >
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="fullName">
            Your name <span className="text-muted-foreground">(optional)</span>
          </Label>
          <div className="relative">
            <User className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="fullName"
              type="text"
              placeholder="Jane Cook"
              autoComplete="name"
              aria-invalid={Boolean(errors.fullName)}
              className="h-11 pl-9"
              {...register("fullName")}
            />
          </div>
          {errors.fullName && (
            <p className="text-xs text-destructive">{errors.fullName.message}</p>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email">Business email</Label>
          <div className="relative">
            <Mail className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="email"
              type="email"
              placeholder="you@yourbusiness.com"
              autoComplete="email"
              aria-invalid={Boolean(errors.email)}
              className="h-11 pl-9"
              {...register("email")}
            />
          </div>
          {errors.email && (
            <p className="text-xs text-destructive">{errors.email.message}</p>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">Password</Label>
          <div className="relative">
            <Lock className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              placeholder="At least 8 characters"
              autoComplete="new-password"
              aria-invalid={Boolean(errors.password)}
              className="h-11 pr-9 pl-9"
              {...register("password")}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="absolute top-1/2 right-2.5 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
            >
              {showPassword ? (
                <EyeOff className="size-4" />
              ) : (
                <Eye className="size-4" />
              )}
            </button>
          </div>
          {errors.password && (
            <p className="text-xs text-destructive">{errors.password.message}</p>
          )}
        </div>

        <Button
          type="submit"
          size="lg"
          className="mt-1 h-11 w-full text-[0.95rem]"
          disabled={isSubmitting}
        >
          {isSubmitting ? (
            <>
              <Loader2 className="animate-spin" />
              Creating account…
            </>
          ) : (
            <>
              Create account
              <ArrowRight />
            </>
          )}
        </Button>
      </form>

      <p className="mt-5 text-center text-sm text-muted-foreground">
        Already have an account?
        <Link
          href="/login"
          className="ml-1 font-medium text-primary hover:underline"
        >
          Sign in
        </Link>
      </p>
    </AuthCard>
  );
}
