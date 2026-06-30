"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema";
import { z } from "zod";
import { toast } from "sonner";
import { ArrowRight, Eye, EyeOff, Loader2, Lock, Mail } from "lucide-react";

import { AuthCard } from "@/components/auth/auth-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, login, storeTokens } from "@/lib/auth";
import { listBusinesses } from "@/lib/business-profile";
import { listDeliveryZones } from "@/lib/fulfillment";
import { resolveOnboardingResumePath } from "@/lib/onboarding-progress";

const loginSchema = z.object({
  email: z.email("Enter a valid email address"),
  password: z.string().min(1, "Password is required"),
  rememberMe: z.boolean(),
});

type LoginValues = z.infer<typeof loginSchema>;

/** The functional sign-in form (used on /, /login and the landing split). */
export function LoginForm({ className }: { className?: string }) {
  const router = useRouter();
  const [showPassword, setShowPassword] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({
    resolver: standardSchemaResolver(loginSchema),
    defaultValues: { email: "", password: "", rememberMe: true },
  });

  async function onSubmit(values: LoginValues) {
    try {
      const tokens = await login(values.email, values.password);
      storeTokens(tokens, values.rememberMe);
      const resumePath = await resolveOnboardingResumePath({
        accessToken: tokens.access_token,
        listBusinesses,
        listDeliveryZones,
      });
      toast.success("Signed in", { description: "Welcome back to OrderlyAI." });
      router.push(resumePath);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Something went wrong.";
      toast.error("Couldn't sign in", { description: message });
    }
  }

  return (
    <AuthCard active="signin" className={className}>
      <div className="mt-6 mb-5 text-center">
        <h1 className="font-heading text-xl font-semibold text-foreground">
          Welcome back 👋
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Sign in to continue to your dashboard.
        </p>
      </div>

      <form
        className="flex flex-col gap-4"
        onSubmit={handleSubmit(onSubmit)}
        noValidate
      >
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
              placeholder="Enter your password"
              autoComplete="current-password"
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

        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 text-sm text-muted-foreground select-none">
            <input
              type="checkbox"
              className="size-4 rounded border-input accent-primary"
              {...register("rememberMe")}
            />
            Remember me
          </label>
          <Link
            href="/login"
            className="text-sm font-medium text-primary hover:underline"
          >
            Forgot password?
          </Link>
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
              Signing in…
            </>
          ) : (
            <>
              Continue
              <ArrowRight />
            </>
          )}
        </Button>
      </form>

      <p className="mt-5 text-center text-sm text-muted-foreground">
        New to OrderlyAI?
        <Link
          href="/signup"
          className="ml-1 font-medium text-primary hover:underline"
        >
          Create an account
        </Link>
      </p>
    </AuthCard>
  );
}
