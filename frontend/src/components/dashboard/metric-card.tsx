"use client";

import { ArrowDownIcon, ArrowUpIcon, ChevronRightIcon, TrendingUpIcon } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";
import type { DashboardMetric } from "@/types/api";

function Change({ metric }: { metric: DashboardMetric }) {
  const { value, previous } = metric;
  if (previous === 0) {
    return value > 0 ? (
      <span className="text-xs font-medium text-success">New</span>
    ) : (
      <span className="text-xs text-muted-foreground">No data yet</span>
    );
  }
  const pct = Math.round(((value - previous) / previous) * 100);
  const up = pct >= 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 text-xs font-medium tabular-nums",
        up ? "text-success" : "text-destructive",
      )}
    >
      {up ? (
        <ArrowUpIcon className="size-3" aria-hidden />
      ) : (
        <ArrowDownIcon className="size-3" aria-hidden />
      )}
      <span aria-hidden>{Math.abs(pct)}%</span>
      <span className="sr-only">
        {up ? "up" : "down"} {Math.abs(pct)}% from {previous}
      </span>
    </span>
  );
}

/** A small line of the daily counts: the shape of the period, not decoration. */
function Sparkline({ series, color }: { series: number[]; color: string }) {
  const max = Math.max(...series, 1);
  const w = 100;
  const h = 32;
  const step = series.length > 1 ? w / (series.length - 1) : w;
  const points = series.map(
    (v, i) =>
      `${(i * step).toFixed(1)},${(h - 2 - (v / max) * (h - 4)).toFixed(1)}`,
  );
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      aria-hidden
      className="h-10 w-full"
    >
      <polyline
        points={`0,${h} ${points.join(" ")} ${w},${h}`}
        fill={color}
        fillOpacity={0.1}
        stroke="none"
      />
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={color}
        strokeWidth={2}
        vectorEffect="non-scaling-stroke"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function MetricCard({
  label,
  icon: Icon,
  metric,
  days,
  href,
  color,
}: {
  label: string;
  icon: typeof TrendingUpIcon;
  metric: DashboardMetric;
  days: number;
  href: string;
  color: string;
}) {
  const { value, previous } = metric;
  const changeText =
    previous === 0
      ? value > 0
        ? "new this period"
        : "no data yet"
      : `${value >= previous ? "up" : "down"} ${Math.abs(Math.round(((value - previous) / previous) * 100))}% from ${previous}`;
  return (
    <Link
      href={href}
      aria-label={`${label}: ${value.toLocaleString()}, ${changeText}. View ${label.toLowerCase()}`}
      className="group grid gap-3 rounded-xl border bg-card p-4 transition-colors outline-none hover:bg-muted/40 focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      <span className="flex items-center gap-2.5">
        <span className="grid size-8 place-items-center rounded-lg bg-muted">
          <Icon className="size-4" aria-hidden />
        </span>
        <span className="flex-1 text-sm font-medium">{label}</span>
        <ChevronRightIcon
          className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5"
          aria-hidden
        />
      </span>
      <span className="grid gap-1">
        <span className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-3xl leading-none font-semibold tabular-nums">
            {metric.value.toLocaleString()}
          </span>
          <Change metric={metric} />
        </span>
        <span className="text-xs text-muted-foreground">
          vs. previous {days} days
        </span>
      </span>
      <Sparkline series={metric.series} color={color} />
    </Link>
  );
}

// --- Trending topics -------------------------------------------------------------------
