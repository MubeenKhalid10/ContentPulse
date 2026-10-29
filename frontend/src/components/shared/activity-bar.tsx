"use client";

import { useIsMutating } from "@tanstack/react-query";
import { useEffect, useState } from "react";

/**
 * A thin bar along the top of the window while any save or action is still running, so a
 * click that takes a while always shows that something is happening, even where the button
 * itself has no spinner. It waits a moment before showing so quick actions don't flash it.
 */
export function ActivityBar() {
  const running = useIsMutating() > 0;
  const [delayed, setDelayed] = useState(false);
  useEffect(() => {
    if (!running) return;
    const timer = setTimeout(() => setDelayed(true), 300);
    return () => {
      clearTimeout(timer);
      setDelayed(false);
    };
  }, [running]);
  const shown = running && delayed;

  return (
    <>
      <div
        aria-hidden
        className={`pointer-events-none fixed inset-x-0 top-0 z-[100] h-0.5 overflow-hidden transition-opacity duration-200 ${shown ? "opacity-100" : "opacity-0"}`}
      >
        <div className="activity-bar h-full w-1/3 bg-primary" />
      </div>
      <span role="status" className="sr-only">
        {shown ? "Working…" : ""}
      </span>
    </>
  );
}
