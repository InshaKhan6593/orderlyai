import Image from "next/image";

import { cn } from "@/lib/utils";

type LogoSize = "sm" | "md" | "lg";

type LogoProps = {
  className?: string;
  /** Show the "OrderlyAI" wordmark next to the mark. */
  withWordmark?: boolean;
  /** Mark + wordmark scale. */
  size?: LogoSize;
  /** Select the mark treatment for its background surface. */
  variant?: "default" | "landing";
};

const SIZES: Record<LogoSize, { mark: string; text: string }> = {
  sm: { mark: "size-8", text: "text-[1.05rem]" },
  md: { mark: "size-10", text: "text-xl" },
  lg: { mark: "size-12", text: "text-2xl" },
};

export function Logo({
  className,
  withWordmark = true,
  size = "md",
  variant = "default",
}: LogoProps) {
  const s = SIZES[size];

  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <Image
        src={
          variant === "landing"
            ? "/landing-logo-mark-dark-flat.png"
            : "/onboarding-logo-mark.png"
        }
        alt={withWordmark ? "" : "OrderlyAI"}
        width={variant === "landing" ? 320 : 63}
        height={variant === "landing" ? 320 : 63}
        className={cn(
          s.mark,
          "shrink-0 object-contain",
          variant === "default" && "mix-blend-multiply",
        )}
        priority
        unoptimized
      />

      {withWordmark && (
        <span className={cn("font-bold tracking-normal text-foreground", s.text)}>
          Orderly<span className="text-foreground dark:text-gold">AI</span>
        </span>
      )}
    </span>
  );
}
