"use client";

import { CheckCircle2Icon, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PLATFORM_LABEL } from "@/lib/topics";
import { cn } from "@/lib/utils";
import type { Platform, PlatformFit } from "@/types/api";

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

export function PlatformFitCard({
  fit,
  recommended,
  canPlan,
  onPlan,
}: {
  fit: PlatformFit[];
  recommended: Platform[];
  canPlan: boolean;
  onPlan: (platform: Platform) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recommended platforms</CardTitle>
        <CardDescription>
          Scored against your audience, goals, the suggested post ideas and
          where it&apos;s trending.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {fit.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Recommendations appear after analysis.
          </p>
        )}
        {fit.map((f) => {
          const isRecommended = recommended.includes(f.platform);
          return (
            <section
              key={f.platform}
              aria-label={PLATFORM_LABEL[f.platform]}
              className="grid gap-1.5"
            >
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-medium">
                  {PLATFORM_LABEL[f.platform]}
                </h3>
                {isRecommended && (
                  <span
                    className="inline-flex items-center gap-1 text-xs text-primary-strong"
                    title="One of the best-scoring platforms for this trend."
                  >
                    <CheckCircle2Icon className="size-3.5" />
                    Recommended
                  </span>
                )}
                <span className="ml-auto text-xs tabular-nums text-muted-foreground">
                  {f.score}/100
                </span>
              </div>
              <div
                className="h-1.5 overflow-hidden rounded-full bg-muted"
                role="meter"
                aria-label={`${PLATFORM_LABEL[f.platform]} fit`}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={f.score}
              >
                <div
                  className={cn(
                    "h-full rounded-full",
                    isRecommended
                      ? "bg-foreground/60"
                      : "bg-muted-foreground/25",
                  )}
                  style={{ width: `${f.score}%` }}
                />
              </div>
              <ul className="grid gap-0.5 text-xs text-muted-foreground">
                {f.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              {f.formats.length > 0 && (
                <p className="text-xs">
                  <span className="text-muted-foreground">Formats: </span>
                  {f.formats.join(", ")}
                </p>
              )}
              {canPlan && (
                <Button
                  size="sm"
                  variant="outline"
                  className="justify-self-start"
                  onClick={() => onPlan(f.platform)}
                >
                  Plan for {PLATFORM_LABEL[f.platform]}
                </Button>
              )}
            </section>
          );
        })}
      </CardContent>
    </Card>
  );
}
