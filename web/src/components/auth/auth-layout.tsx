import { Check, Cloud, Headphones, ShieldCheck } from "lucide-react";

import { Logo } from "@/components/brand/logo";

const points = [
  "An AI assistant takes orders right inside WhatsApp.",
  "Every order lands on one live dashboard.",
  "Menu, hours & delivery zones — set up in minutes.",
];

const trust = [
  {
    icon: ShieldCheck,
    title: "Secure & private",
    sub: "Your data is safe with us",
  },
  { icon: Cloud, title: "Always online", sub: "99.9% uptime guarantee" },
  { icon: Headphones, title: "24/7 support", sub: "We're here to help" },
];

/**
 * Split-screen auth shell: dark marketing panel on the left, the form (passed as
 * children) inside the light glass panel on the right. Shared by /, /login and
 * /signup so every entry point looks identical.
 */
export function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid lg:grid-cols-2">
      {/* Left — brand / marketing (dark) */}
      <div className="dark relative hidden h-svh flex-col justify-between overflow-hidden bg-[#0B2A1F] px-12 py-10 text-foreground lg:flex">
        <div className="pointer-events-none absolute -top-24 -right-20 size-96 rounded-full bg-primary/20 blur-[120px]" />
        <div className="pointer-events-none absolute -bottom-24 -left-20 size-80 rounded-full bg-gold/15 blur-[120px]" />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.04] [background-image:linear-gradient(white_1px,transparent_1px),linear-gradient(90deg,white_1px,transparent_1px)] [background-size:32px_32px]"
        />

        <div className="relative">
          <Logo size="lg" variant="landing" />
        </div>

        <div className="relative max-w-md">
          <span className="inline-flex items-center gap-2 rounded-full border border-border bg-card/40 px-4 py-1.5 text-xs font-medium text-muted-foreground">
            <span className="size-1.5 rounded-full bg-primary" />
            WhatsApp ordering + AI for food businesses
          </span>
          <h1 className="mt-6 font-heading text-4xl leading-[1.08] font-semibold tracking-tight text-balance xl:text-5xl">
            Run your food orders on WhatsApp — without the chaos.
          </h1>
          <ul className="mt-8 flex flex-col gap-3.5">
            {points.map((point) => (
              <li key={point} className="flex items-start gap-3">
                <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-primary/15 text-primary">
                  <Check className="size-3.5" />
                </span>
                <span className="text-sm text-foreground/90">{point}</span>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-muted-foreground">
          © {new Date().getFullYear()} OrderlyAI · Ordering over WhatsApp for
          small food businesses
        </p>
      </div>

      {/* Right — form (light, glass). Its own viewport-height scroll area so the
          page body never scrolls (and focusing a field can't scroll the page). */}
      <div className="relative flex h-svh flex-col overflow-x-hidden overflow-y-auto bg-muted px-6 py-6 sm:px-10">
        <div className="pointer-events-none absolute top-0 right-0 size-72 rounded-full bg-primary/10 blur-[100px]" />
        <div className="relative lg:hidden">
          <Logo size="md" />
        </div>
        <div className="relative flex flex-1 flex-col items-center justify-center py-6">
          {children}
          <div className="mt-6 w-full max-w-md border-t border-border/70 pt-5">
            <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-4">
              {trust.map(({ icon: Icon, title, sub }) => (
                <div key={title} className="flex items-center gap-2.5">
                  <Icon className="size-5 shrink-0 text-primary" />
                  <div>
                    <p className="text-xs font-medium text-foreground">
                      {title}
                    </p>
                    <p className="text-[0.7rem] text-muted-foreground">{sub}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
