import Link from "next/link";
import { Lock, UserPlus } from "lucide-react";

import { cn } from "@/lib/utils";

const base =
  "flex items-center justify-center gap-1.5 rounded-lg py-2 transition-colors";
const activeCls = "bg-card text-primary shadow-sm ring-1 ring-foreground/5";
const idleCls = "text-muted-foreground hover:text-foreground";

/** Segmented Sign in / Create account switch shared by both auth forms. */
export function AuthTabs({ active }: { active: "signin" | "signup" }) {
  return (
    <div className="grid grid-cols-2 gap-1 rounded-xl border border-border bg-muted/60 p-1 text-sm font-medium">
      {active === "signin" ? (
        <span className={cn(base, activeCls)}>
          <Lock className="size-3.5" />
          Sign in
        </span>
      ) : (
        <Link href="/login" className={cn(base, idleCls)}>
          <Lock className="size-3.5" />
          Sign in
        </Link>
      )}
      {active === "signup" ? (
        <span className={cn(base, activeCls)}>
          <UserPlus className="size-3.5" />
          Create account
        </span>
      ) : (
        <Link href="/signup" className={cn(base, idleCls)}>
          <UserPlus className="size-3.5" />
          Create account
        </Link>
      )}
    </div>
  );
}
