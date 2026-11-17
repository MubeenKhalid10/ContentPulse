"use client";

import { type LucideIcon } from "lucide-react";

import { CardDescription, CardTitle } from "@/components/ui/card";

/** Icon tile, title, one-line purpose and a count: the header of the plan and post cards. */
export function SectionHeader({
  icon: Icon,
  title,
  description,
  badge,
  actions,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  badge?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start gap-3">
      <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-muted" aria-hidden>
        <Icon className="size-5 text-foreground" />
      </span>
      <div className="grid min-w-0 flex-1 gap-0.5">
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </div>
      {badge && (
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{badge}</span>
      )}
      {actions && (
        <div className="flex basis-full flex-wrap justify-end gap-2 sm:basis-auto">{actions}</div>
      )}
    </div>
  );
}
