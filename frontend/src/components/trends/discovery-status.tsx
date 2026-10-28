"use client";

import { useDiscoveryWindow } from "@/hooks/use-trends";
import { formatDateTime, timeOfDay } from "@/lib/format";

const isFuture = (iso: string) => Date.parse(iso) > Date.now();

/** Time of day for today, date and time otherwise. */
function stamp(iso: string): string {
  const d = new Date(iso);
  return d.toDateString() === new Date().toDateString() ? timeOfDay(iso) : formatDateTime(iso);
}

/** When the stored trends were last refreshed and roughly when the next
 * refresh is due. Reads the discovery window the page already loads; shows
 * only the times the server returned. The next time is an estimate. */
export function DiscoveryStatus() {
  const info = useDiscoveryWindow().data;
  const last = info?.last_discovery_at;
  if (!info || !last) return null;
  const next = info.next_discovery_at;
  const upcoming = !!next && isFuture(next);
  return (
    <p className="text-sm text-muted-foreground">
      <span title={formatDateTime(last)}>Last updated {stamp(last)}</span>
      {upcoming && next && (
        <>
          {" · "}
          <span title={formatDateTime(next)}>
            {info.background
              ? `Next update about ${stamp(next)}`
              : `You can check again after ${stamp(next)}`}
          </span>
        </>
      )}
    </p>
  );
}
