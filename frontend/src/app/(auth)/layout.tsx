import Link from "next/link";

import { Logo } from "@/components/shared/logo";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-8 bg-background px-4 py-12">
      <Link href="/" aria-label="ContentPulse home" className="rounded-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
        <Logo className="text-2xl" />
      </Link>
      <div className="w-full max-w-sm">{children}</div>
    </main>
  );
}
