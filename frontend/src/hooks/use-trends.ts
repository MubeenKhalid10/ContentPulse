"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useOrgId } from "@/hooks/use-organization";
import { api, apiDownload } from "@/lib/api";
import type {
  DiscoveryRun,
  DiscoveryWindow,
  AIStatus,
  ExportWindow,
  MarketOption,
  RunStarted,
  TrendDetail,
  TrendPage,
  TrendSourceInfo,
} from "@/types/api";

// Trend routes use the active organization (X-Organization-Id header).
const root = (orgId: string) => ["org", orgId, "trends"] as const;

export type RelevanceFilter = "" | "relevant" | "highly_relevant" | "weakly_relevant" | "not_relevant" | "unanalyzed";

export interface TrendFilters {
  status: "active" | "shortlisted" | "rejected";
  relevance: RelevanceFilter;
  sort: "score" | "recent" | "mentions" | "new";
  source: string;
  location: string;
  q: string;
}

/** The trends page shows only trends seen in the last 7 days (older ones
 * stay in the database, hidden). Same window as the CSV export. */
export const TREND_WINDOW_DAYS = 7;

export function useTrends(filters: TrendFilters, limit: number) {
  const orgId = useOrgId();
  const params = new URLSearchParams({
    status: filters.status,
    sort: filters.sort,
    limit: String(limit),
    seen_within_days: String(TREND_WINDOW_DAYS),
  });
  if (filters.source) params.set("source", filters.source);
  if (filters.location) params.set("location", filters.location);
  if (filters.relevance) params.set("relevance", filters.relevance);
  if (filters.q.trim()) params.set("q", filters.q.trim());
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "list", params.toString()],
    queryFn: () => api<TrendPage>(`/trends?${params}`),
    enabled: !!orgId,
    placeholderData: keepPreviousData,
  });
}

export function useTrend(id: string) {
  const orgId = useOrgId();
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "detail", id],
    queryFn: () => api<TrendDetail>(`/trends/${id}`),
    enabled: !!orgId,
    // Poll while an analysis is queued or running.
    refetchInterval: (query) => {
      const status = query.state.data?.analysis?.status;
      return status === "queued" || status === "running" ? 2000 : false;
    },
  });
}

/** Latest runs; polls while one is in progress. */
export function useDiscoveryRuns() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "runs"],
    queryFn: () => api<DiscoveryRun[]>(`/trends/runs?limit=5`),
    enabled: !!orgId,
    // Fast while a run is active; otherwise check now and then so scheduled
    // runs (started by the server) show up without a reload.
    refetchInterval: (query) =>
      query.state.data?.some((r) => r.status === "queued" || r.status === "running") ? 2000 : 30_000,
  });
}

/** When the stored trends were last refreshed and when the next discovery is due. */
export function useDiscoveryWindow() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "discovery"],
    queryFn: () => api<DiscoveryWindow>(`/trends/discovery`),
    enabled: !!orgId,
    refetchInterval: 60_000,
  });
}

export function useTrendSources() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "sources"],
    queryFn: () => api<TrendSourceInfo[]>(`/trends/sources`),
    enabled: !!orgId,
  });
}

export function useMarkets() {
  return useQuery({
    queryKey: ["trends", "markets"],
    queryFn: () => api<MarketOption[]>(`/trends/markets`),
    staleTime: Infinity,
  });
}

function useTrendMutation<TVars, TResult>(request: (vars: TVars) => Promise<TResult>) {
  const orgId = useOrgId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: root(orgId!) });
      // Trend decisions and analysis create or update topic candidates.
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "topics"] });
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "dashboard"] });
    },
  });
}

export function useDiscover() {
  const orgId = useOrgId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { sources?: string[] } = {}) =>
      api<RunStarted>(`/trends/discover`, { method: "POST", body }),
    // Refresh runs on success *and* on 409 (a scheduled run is already going),
    // so the page shows the active run and starts polling it. Inside the
    // discovery window nothing is collected: reload the stored trends.
    onSettled: (result) => {
      queryClient.invalidateQueries({ queryKey: [...root(orgId!), "runs"] });
      queryClient.invalidateQueries({ queryKey: [...root(orgId!), "discovery"] });
      if (result && !result.started) {
        queryClient.invalidateQueries({ queryKey: root(orgId!) });
        queryClient.invalidateQueries({ queryKey: ["org", orgId, "dashboard"] });
      }
    },
  });
}

export const useToggleSource = () =>
  useTrendMutation(({ key, enabled }: { key: string; enabled: boolean }) =>
    api<TrendSourceInfo[]>(`/trends/sources/${key}`, { method: "PATCH", body: { enabled } }),
  );

export const useTrendAction = () =>
  useTrendMutation(({ id, action }: { id: string; action: "shortlist" | "reject" | "restore" }) =>
    api<TrendDetail>(`/trends/${id}/${action}`, { method: "POST" }),
  );

export const useDeleteTrend = () =>
  useTrendMutation((id: string) => api<void>(`/trends/${id}`, { method: "DELETE" }));

export function useAIStatus() {
  return useQuery({
    queryKey: ["ai", "status"],
    queryFn: () => api<AIStatus>("/ai/status"),
    staleTime: 5 * 60_000,
  });
}

export const useAnalyzeTrend = () =>
  useTrendMutation((id: string) =>
    api<{ job_id: string; status: string }>(`/trends/${id}/analyze`, { method: "POST" }),
  );

/** The seven-day range a CSV export would cover now (admins only). */
export function useExportWindow(enabled: boolean) {
  const orgId = useOrgId();
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "export-window"],
    queryFn: () => api<ExportWindow>("/trends/export/window"),
    enabled: !!orgId && enabled,
    refetchInterval: 60_000,
    retry: false,
  });
}

export interface TrendsExport {
  blob: Blob;
  filename: string;
  rows: number;
  start: string;
  end: string;
  timezone: string;
}

/** Download the CSV. The range comes back from the server, captured once. */
export function useExportTrends() {
  return useMutation({
    mutationFn: async (): Promise<TrendsExport> => {
      const file = await apiDownload("/trends/export.csv");
      return {
        blob: file.blob,
        filename: file.filename,
        rows: Number(file.headers.get("X-Export-Rows") ?? 0),
        start: file.headers.get("X-Export-Start") ?? "",
        end: file.headers.get("X-Export-End") ?? "",
        timezone: file.headers.get("X-Export-Timezone") ?? "",
      };
    },
  });
}
