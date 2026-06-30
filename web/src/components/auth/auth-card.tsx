import { AuthTabs } from "@/components/auth/auth-tabs";
import { cn } from "@/lib/utils";

/**
 * Rounded glass card that frames an auth form, with the shared Sign in /
 * Create account tab switch on top. Corners are moderately rounded (rounded-2xl)
 * and the padding is generous so the card has real height.
 */
export function AuthCard({
  active,
  className,
  children,
}: {
  active: "signin" | "signup";
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "w-full rounded-2xl border border-border bg-card/80 p-6 shadow-[0_24px_70px_-28px_rgba(15,61,46,0.45)] backdrop-blur-xl sm:p-7",
        className,
      )}
    >
      <AuthTabs active={active} />
      {children}
    </div>
  );
}
