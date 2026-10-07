import Link from "next/link";

import { AuthAside } from "@/components/auth/auth-aside";
import { Logo } from "@/components/shared/logo";

/**
 * Sign-in screens share the landing page's masthead and the app's desk:
 * the form sits on the paper, set under a headline, with the product's
 * four steps beside it on wide screens.
 */
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-svh flex-col bg-background text-foreground">
      <header className="dark border-b border-border bg-background text-foreground">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 sm:px-6">
          <Link
            href="/"
            aria-label="ContentPulse home"
            className="rounded-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/60"
          >
            <Logo className="text-xl" />
          </Link>
          <Link
            href="/"
            className="ml-auto inline-flex h-11 items-center rounded-sm px-3 text-sm font-medium outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/60"
          >
            What is ContentPulse?
          </Link>
        </div>
      </header>
      <main className="mx-auto grid w-full max-w-7xl flex-1 gap-16 px-4 py-10 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:py-16">
        <div className="auth-desk w-full max-w-md self-start justify-self-center lg:self-center lg:justify-self-start">
          {children}
          <p className="mt-10 border-t border-border pt-4 text-sm leading-relaxed text-muted-foreground lg:hidden">
            ContentPulse turns the trends that fit each client into approved
            social posts, for agencies running content for several clients.{" "}
            <Link
              href="/"
              className="font-medium text-foreground underline underline-offset-4"
            >
              See how it works
            </Link>
          </p>
        </div>
        <div className="hidden border-l border-border pl-12 lg:grid">
          <AuthAside />
        </div>
      </main>
    </div>
  );
}
