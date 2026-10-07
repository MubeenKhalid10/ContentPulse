import type { Metadata } from "next";
import { Suspense } from "react";

import { LocalResetForm } from "@/components/auth/local-reset-form";

export const metadata: Metadata = { title: "Choose a new password" };

export default function LocalResetPasswordPage() {
  return (
    <Suspense>
      <LocalResetForm />
    </Suspense>
  );
}
