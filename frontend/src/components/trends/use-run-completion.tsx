"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { useOrgId } from "@/hooks/use-organization";
import { ApiError, errorMessage } from "@/lib/api";
import { timeOfDay, timeUntil } from "@/lib/format";
import type { RunStarted } from "@/types/api";

/** Inside the discovery window nothing is collected: the page reloads the
 * stored trends and says when the next discovery is due. Trends count as new
 * only if that discovery finished after the list on screen was loaded. */
export function onDiscoverStarted(result: RunStarted, shownAt: number) {
  if (result.started) {
    toast.success("Discovery started. Results appear here in a minute.");
    return;
  }
  const info = result.window;
  const next = info.next_discovery_at;
  const wait = next ? `in ${timeUntil(next)} (${timeOfDay(next)})` : "soon";
  const last = info.last_discovery_at;
  if (info.new_trends > 0 && last && Date.parse(last) > shownAt) {
    toast.success(
      `Showing the latest trends: ${info.new_trends} new from the ${timeOfDay(last)} discovery.`,
      { description: `The next discovery runs ${wait}.` },
    );
  } else {
    toast.message("No new trends found since the last discovery.", {
      description: `New discovery will be available ${wait}.`,
    });
  }
}

export function onDiscoverError(error: unknown) {
  if (error instanceof ApiError && error.status === 409) {
    toast.message(
      "Discovery is already running. Results will appear here shortly.",
    );
  } else {
    toast.error(errorMessage(error));
  }
}

/** Refresh trends and notify when a discovery run finishes. */
export function useRunCompletion(
  runId: string | undefined,
  status: string | undefined,
) {
  const queryClient = useQueryClient();
  const orgId = useOrgId();
  const previous = useRef<{ id?: string; status?: string }>({});

  useEffect(() => {
    const before = previous.current;
    previous.current = { id: runId, status };
    const wasActive = before.status === "queued" || before.status === "running";
    if (!runId || before.id !== runId || !wasActive || status === before.status)
      return;
    if (status === "succeeded") {
      toast.success("New trends are in");
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "trends"] });
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "dashboard"] });
    } else if (status === "failed") {
      toast.error(
        "Trend discovery failed. See the run details for each source.",
      );
    }
  }, [runId, status, queryClient, orgId]);
}
