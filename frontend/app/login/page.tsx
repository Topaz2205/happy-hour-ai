import { Suspense } from "react";
import AuthForm from "@/components/AuthForm";

export const metadata = { title: "Sign in — Happy Hour Cocktails AI" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <AuthForm mode="login" />
    </Suspense>
  );
}
