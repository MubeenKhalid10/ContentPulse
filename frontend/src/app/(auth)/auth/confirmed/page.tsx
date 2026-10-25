import type { Metadata } from "next";
import { Suspense } from "react";

import { EmailConfirmed } from "@/components/auth/email-confirmed";

export const metadata: Metadata = { title: "Email confirmed" };

/** Where the sign-up confirmation email's button lands. */
export default function EmailConfirmedPage() {
  return (
    <Suspense>
      <EmailConfirmed />
    </Suspense>
  );
}
