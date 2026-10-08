"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useOrgId } from "@/hooks/use-organization";
import { api } from "@/lib/api";
import type {
  DiscoveryRun,
  AIStatus,
  MarketOption,
  RelevanceLevel,
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

export function useTrends(filters: TrendFilters, limit: number) {
  const orgId = useOrgId();
  const params = new URLSearchParams({ status: filters.status, sort: filters.sort, limit: String(limit) });
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
    // so the page shows the active run and starts polling it.
    onSettled: () => queryClient.invalidateQueries({ queryKey: [...root(orgId!), "runs"] }),
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

export const useOverrideRelevance = () =>
  useTrendMutation(({ id, level }: { id: string; level: RelevanceLevel | null }) =>
    api<TrendDetail>(`/trends/${id}/relevance`, { method: "PATCH", body: { relevance_level: level } }),
  );
