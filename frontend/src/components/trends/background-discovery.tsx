"use client";

import { useId } from "react";
import { toast } from "sonner";

import { LoadingNotice } from "@/components/shared/loading";
import { Switch } from "@/components/ui/switch";
import { useOrgSettings, useUpdateSettings } from "@/hooks/use-organization";
import { useDiscoveryWindow } from "@/hooks/use-trends";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { timeUntil } from "@/lib/format";
import { FREQUENCY_OPTIONS } from "@/lib/options";
import { cn } from "@/lib/utils";
import type { TrendFrequency } from "@/types/api";

/** "every 3 hours": the schedule the backend runs this organization on. */
export function scheduleLabel(frequency: TrendFrequency): string | null {
  if (frequency === "manual") return null;
  const label = FREQUENCY_OPTIONS.find((o) => o.value === frequency)?.label;
  return label ? label.toLowerCase() : null;
}

export function backgroundHint(
  on: boolean,
  frequency: TrendFrequency,
  nextDiscoveryAt?: string | null,
): string {
  if (!on) return "Trends update only when you select Check for new trends.";
  const schedule = scheduleLabel(frequency);
  const next =
    nextDiscoveryAt && Date.parse(nextDiscoveryAt) > Date.now()
      ? ` Next update in about ${timeUntil(nextDiscoveryAt)}.`
      : "";
  return `New trends arrive automatically${schedule ? ` (${schedule})` : ""}.${next || " ContentPulse manages the schedule."}`;
}

/**
 * The organization's only scheduling choice: keep trends updated in the
 * background or only on request. Collection itself runs in the backend.
 */
export function BackgroundDiscoveryToggle({ className }: { className?: string }) {
  const settings = useOrgSettings();
  const update = useUpdateSettings();
  const canEdit = useCan()("organization.write");
  const discovery = useDiscoveryWindow();
  const labelId = useId();
  const hintId = useId();
  if (!settings.data) return settings.isPending ? <LoadingNotice label="Loading settings…" /> : null;
  const on = settings.data.background_discovery;

  return (
    <div className={cn("flex flex-wrap items-center gap-3", className)}>
      <div className="grid gap-0.5 text-left">
        <span id={labelId} className="text-sm font-medium sm:whitespace-nowrap">
          Update trends in the background
        </span>
        <span id={hintId} className="max-w-72 text-xs text-muted-foreground">
          {update.isPending ? "Saving…" : backgroundHint(
                on,
                settings.data.trend_frequency,
                discovery.data?.next_discovery_at,
              )}
          {!canEdit && !update.isPending && " Only admins can change this."}
        </span>
      </div>
      <Switch
        checked={on}
        disabled={!canEdit || update.isPending}
        aria-labelledby={labelId}
        aria-describedby={hintId}
        onCheckedChange={(background_discovery) =>
          update.mutate(
            { background_discovery },
            {
              onSuccess: () =>
                toast.success(
                  background_discovery
                    ? "Trends will update in the background"
                    : "Trends will update only when you ask",
                ),
              onError: (e) => toast.error(errorMessage(e)),
            },
          )
        }
      />
    </div>
  );
}
