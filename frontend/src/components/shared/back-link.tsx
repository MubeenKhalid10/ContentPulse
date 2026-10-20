"use client";

import { ArrowLeftIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useCallback } from "react";

import { backLabel, safeFrom, withFrom } from "@/lib/back";

/** Back to the page this one was opened from, or to the section's list. */
export function BackLink({ href, label }: { href: string; label: string }) {
  const from = safeFrom(useSearchParams().get("from"));
  return (
    <Link
      href={from ?? href}
      className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeftIcon className="size-4" />
      {from ? backLabel(from) : label}
    </Link>
  );
}

/** Adds the current page as `from` to links that leave a detail page. */
export function useFromHere(): (href: string) => string {
  const pathname = usePathname();
  const search = useSearchParams().toString();
  return useCallback(
    (href: string) => withFrom(href, search ? `${pathname}?${search}` : pathname),
    [pathname, search],
  );
}
