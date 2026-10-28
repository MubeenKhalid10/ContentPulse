"use client";

import { ArrowRightIcon, RadarIcon } from "lucide-react";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import type { TrendSourceInfo } from "@/types/api";

/** Which sources are being watched, one click from managing them. */
export function SourcesStrip({ sources }: { sources: TrendSourceInfo[] }) {
  const on = sources.filter((s) => s.enabled && s.configured);
  const needSetup = sources.filter(
    (s) => s.enabled && !s.configured && s.pricing !== "unavailable",
  );
  const shown = on.slice(0, 4).map((s) => s.name);
  return (
    <section
      aria-label="Discovery sources"
      className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border bg-card px-4 py-3"
    >
      <RadarIcon
        className="size-4 shrink-0 text-muted-foreground"
        aria-hidden
      />
      <p className="min-w-0 flex-1 text-sm">
        {on.length ? (
          <>
            Watching{" "}
            <span className="font-medium">
              {on.length} source{on.length === 1 ? "" : "s"}
            </span>
            <span className="text-muted-foreground">
              : {shown.join(", ")}
              {on.length > shown.length
                ? ` and ${on.length - shown.length} more`
                : ""}
              .
            </span>
          </>
        ) : (
          <span className="font-medium">No sources are on yet.</span>
        )}
        {needSetup.length > 0 && (
          <span className="text-muted-foreground">
            {" "}
            {needSetup.length} {needSetup.length === 1 ? "needs" : "need"}{" "}
            setup.
          </span>
        )}
      </p>
      <Link href="/trends/sources" className={buttonVariants({ size: "sm" })}>
        Discovery Sources <ArrowRightIcon />
      </Link>
    </section>
  );
}
