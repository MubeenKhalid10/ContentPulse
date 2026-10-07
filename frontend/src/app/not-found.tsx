import { ArrowLeftIcon, CompassIcon } from "lucide-react";
import Link from "next/link";

import { Logo } from "@/components/shared/logo";
import { buttonVariants } from "@/components/ui/button";

export const metadata = { title: "Page not found · ContentPulse" };

/** Any unknown URL: say so plainly and offer the two ways back. */
export default function NotFound() {
  return (
    <main className="grid min-h-svh place-items-center bg-muted/40 px-4">
      <div className="grid w-full max-w-md justify-items-center gap-6 text-center">
        <Logo />
        <div className="grid w-full justify-items-center gap-3 rounded-xl border bg-card p-8 shadow-sm">
          <span className="grid size-12 place-items-center rounded-full bg-muted text-muted-foreground" aria-hidden>
            <CompassIcon className="size-6" />
          </span>
          <h1 className="text-xl font-semibold tracking-tight">This page doesn&apos;t exist</h1>
          <p className="text-sm text-muted-foreground">
            The link may be mistyped, or the page was moved. Everything you&apos;re working on is still in your
            dashboard.
          </p>
          <div className="mt-2 flex flex-wrap justify-center gap-2">
            <Link href="/dashboard" className={buttonVariants()}>
              Go to dashboard
            </Link>
            <Link href="/login" className={buttonVariants({ variant: "outline" })}>
              <ArrowLeftIcon />
              Sign in
            </Link>
          </div>
        </div>
      </div>
    </main>
  );
}
