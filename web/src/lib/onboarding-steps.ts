/** The 8-step onboarding wizard (design docs 09 §B). Order is the wizard order. */
export type OnboardingStep = {
  num: number;
  title: string;
  subtitle: string;
  href: string;
};

export const ONBOARDING_STEPS: readonly OnboardingStep[] = [
  { num: 1, title: "Welcome", subtitle: "Start your setup journey", href: "/onboarding" },
  { num: 2, title: "Business Profile", subtitle: "Tell us about your business", href: "/onboarding/business-profile" },
  { num: 3, title: "Hours", subtitle: "Set your operating hours", href: "/onboarding/hours" },
  { num: 4, title: "Fulfillment & Delivery", subtitle: "Choose how you fulfill orders", href: "/onboarding/fulfillment" },
  { num: 5, title: "Menu", subtitle: "Add menu items", href: "/onboarding/menu" },
  { num: 6, title: "AI Assistant", subtitle: "Customize your assistant", href: "/onboarding/assistant" },
  { num: 7, title: "Connect WhatsApp", subtitle: "Link your WhatsApp number", href: "/onboarding/whatsapp" },
  { num: 8, title: "Review & Go Live", subtitle: "Launch your store", href: "/onboarding/review" },
] as const;
