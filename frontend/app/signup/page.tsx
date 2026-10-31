import { Suspense } from "react";
import AuthForm from "@/components/AuthForm";

export const metadata = { title: "Create account — Happy Hour Cocktails AI" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <AuthForm mode="signup" />
    </Suspense>
  );
}
