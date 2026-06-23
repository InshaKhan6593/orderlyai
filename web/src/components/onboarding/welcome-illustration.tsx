import Image from "next/image";

import { cn } from "@/lib/utils";

export function WelcomeIllustration({ className }: { className?: string }) {
  return (
    <Image
      src="/onboarding-welcome-illustration.png"
      alt="A storefront with a green chat bubble"
      width={468}
      height={422}
      className={cn("h-auto w-full object-contain", className)}
      priority
      unoptimized
    />
  );
}
