"use client";

import { useSyncExternalStore } from "react";

const MINUTE = 60_000;

function subscribe(cb: () => void) {
  const t = window.setInterval(cb, 10_000);
  return () => window.clearInterval(t);
}

/** The desk clock in the masthead: today's date and the minute, in the visitor's time zone. */
export function MastheadClock() {
  // Snapshot is the current minute, so it only re-renders when the clock face changes.
  const minute = useSyncExternalStore(
    subscribe,
    () => Math.floor(Date.now() / MINUTE),
    () => null,
  );

  if (minute === null) return <span className="slug invisible">00:00</span>;
  const now = new Date(minute * MINUTE);
  const date = now.toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
  const time = now.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
  return (
    <time dateTime={now.toISOString()} className="slug tabular-nums">
      {date} · {time}
    </time>
  );
}
