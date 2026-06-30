import { AuthLayout } from "@/components/auth/auth-layout";
import { LoginForm } from "@/components/auth/login-form";

export default function Home() {
  // The landing page IS the sign-in split screen (login lives on the landing).
  return (
    <AuthLayout>
      <LoginForm className="max-w-sm" />
    </AuthLayout>
  );
}
