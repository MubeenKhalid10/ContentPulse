import { cn } from "@/lib/utils";
import { SIGNALS, scoreTone } from "@/lib/trends";
import type { Signal, SignalKey } from "@/types/api";

const SIZES = {
  sm: "size-10 text-sm",
  md: "size-12 text-base",
  lg: "size-16 text-xl",
} as const;

/** Light teal behind the score, deeper for better opportunities, so the
 * strongest trends catch the eye first. */
function scoreSurface(score: number | null): string {
  if (score == null) return "bg-card";
  if (score >= 70) return "border-primary/30 bg-primary/15";
  if (score >= 45) return "border-primary/20 bg-primary/8";
  return "bg-card";
}

/** Opportunity score (0-100) as a number on a light teal tile. */
export function Score({ score, size = "md" }: { score: number | null; size?: keyof typeof SIZES }) {
  const value = score == null ? null : Math.round(score);
  return (
    <div
      className={cn(
        "grid shrink-0 place-content-center rounded-lg border text-center leading-none",
        scoreSurface(score),
        SIZES[size],
      )}
      role="img"
      aria-label={value == null ? "Not scored yet" : `Opportunity score ${value} of 100`}
      title="Opportunity score, out of 100"
    >
      <span aria-hidden className={cn("font-semibold tabular-nums", scoreTone(score))}>
        {value ?? "—"}
      </span>
    </div>
  );
}

/** Full signal breakdown for the detail page (spec §13: expose the factors). */
export function SignalBreakdown({ signals }: { signals: Partial<Record<SignalKey, Signal>> }) {
  return (
    <dl className="grid gap-4">
      {SIGNALS.map(({ key, label, help }) => {
        const signal = signals[key];
        const pendingAi = !signal && (key === "organization_fit" || key === "audience_relevance");
        return (
          <div key={key} className="grid gap-1.5">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-sm font-medium" title={help}>
                {label}
              </dt>
              <dd className="font-mono text-sm tabular-nums">{signal ? signal.score : "—"}</dd>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-foreground/60 transition-[width] duration-500"
                style={{ width: `${signal?.score ?? 0}%` }}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              {signal
                ? signal.detail
                : key === "organization_fit"
                  ? "Filled in when the trend is analyzed"
                  : pendingAi
                    ? "Requires AI analysis (not part of the rule-based estimate)"
                    : help}
            </p>
          </div>
        );
      })}
    </dl>
  );
}
