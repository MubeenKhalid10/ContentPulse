"use client";

import Link from "next/link";

import { useCan } from "@/lib/auth";
import { WORKFLOW } from "@/lib/workflow";

/** The whole product in one row: five steps, each a link, in plain words. */
export function HowItWorks() {
  const can = useCan();
  const steps = WORKFLOW.filter((s) => can(s.permission));
  return (
    <section aria-labelledby="how-title" className="grid gap-3">
      <div className="grid gap-0.5">
        <h2 id="how-title" className="text-base font-semibold">
          How ContentPulse works
        </h2>
        <p className="text-sm text-muted-foreground">
          Every post goes through the same five steps. Nothing is published
          until a person approves it.
        </p>
      </div>
      <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {steps.map((s) => (
          <li key={s.href}>
            <Link
              href={s.href}
              className="group grid h-full gap-1.5 rounded-xl border bg-card p-4 transition-colors hover:bg-muted"
            >
              <span className="grid size-6 place-items-center rounded-full bg-muted text-xs font-semibold tabular-nums group-hover:bg-background">
                {s.n}
              </span>
              <span className="text-sm font-medium">{s.label}</span>
              <span className="text-xs text-muted-foreground">{s.summary}</span>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}

// --- Header search -------------------------------------------------------------------
