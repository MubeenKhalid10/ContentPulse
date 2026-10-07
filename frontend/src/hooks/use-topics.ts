"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useOrgId } from "@/hooks/use-organization";
import { api } from "@/lib/api";
import type {
  Platform,
  PlatformRule,
  Strategy,
  StrategyFields,
  StrategySuggestion,
  TopicDetail,
  TopicPage,
} from "@/types/api";

// Topic routes use the active organization (X-Organization-Id header).
const root = (orgId: string) => ["org", orgId, "topics"] as const;

export type TopicStatusFilter = "open" | "shortlisted" | "rejected" | "archived" | "all";

export interface TopicFilters {
  status: TopicStatusFilter;
  relevance: "" | "relevant" | "highly_relevant" | "weakly_relevant" | "not_relevant";
  platform: "" | Platform;
  sort: "score" | "recent" | "relevance";
  q: string;
}

export function useTopics(filters: TopicFilters, limit: number) {
  const orgId = useOrgId();
  const params = new URLSearchParams({ status: filters.status, sort: filters.sort, limit: String(limit) });
  if (filters.relevance) params.set("relevance", filters.relevance);
  if (filters.platform) params.set("platform", filters.platform);
  if (filters.q.trim()) params.set("q", filters.q.trim());
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "list", params.toString()],
    queryFn: () => api<TopicPage>(`/topics?${params}`),
    enabled: !!orgId,
    placeholderData: keepPreviousData,
  });
}

export function useTopic(id: string) {
  const orgId = useOrgId();
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "detail", id],
    queryFn: () => api<TopicDetail>(`/topics/${id}`),
    enabled: !!orgId,
    // Poll while the underlying trend is being (re)analyzed.
    refetchInterval: (query) => {
      const status = query.state.data?.trend?.analysis?.status;
      return status === "queued" || status === "running" ? 2000 : false;
    },
  });
}

function useTopicMutation<TVars, TResult>(request: (vars: TVars) => Promise<TResult>) {
  const orgId = useOrgId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: root(orgId!) });
      // Topic decisions are mirrored on the trend.
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "trends"] });
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "dashboard"] });
    },
  });
}

export type TopicAction = "shortlist" | "reject" | "review" | "restore" | "archive";

export const useTopicAction = () =>
  useTopicMutation(({ id, action }: { id: string; action: TopicAction }) =>
    api<TopicDetail>(`/topics/${id}/${action}`, { method: "POST" }),
  );

export const useUpdateTopic = () =>
  useTopicMutation(
    ({ id, ...body }: { id: string; title?: string; summary?: string | null; target_audience?: string | null }) =>
      api<TopicDetail>(`/topics/${id}`, { method: "PATCH", body }),
  );

export type StrategyInput = StrategyFields & { platform: Platform; source?: "ai" | "rules" | "manual" };

export const useCreateStrategy = () =>
  useTopicMutation(({ topicId, ...body }: StrategyInput & { topicId: string }) =>
    api<Strategy>(`/topics/${topicId}/strategies`, { method: "POST", body }),
  );

export const useUpdateStrategy = () =>
  useTopicMutation(
    ({ topicId, id, ...body }: Partial<StrategyInput> & { topicId: string; id: string }) =>
      api<Strategy>(`/topics/${topicId}/strategies/${id}`, { method: "PATCH", body }),
  );

export const useStrategyAction = () =>
  useTopicMutation(
    ({ topicId, id, action }: { topicId: string; id: string; action: "approve" | "reopen" | "archive" }) =>
      api<Strategy>(`/topics/${topicId}/strategies/${id}/${action}`, { method: "POST" }),
  );

/** Draft a strategy with AI (or rules); nothing is saved. */
export function useSuggestStrategy() {
  return useMutation({
    mutationFn: ({ topicId, platform }: { topicId: string; platform: Platform }) =>
      api<StrategySuggestion>(`/topics/${topicId}/strategies/suggest`, {
        method: "POST",
        body: { platform },
      }),
  });
}

// --- Platform playbooks ---------------------------------------------------------

const rulesKey = (orgId: string) => ["org", orgId, "platform-rules"] as const;

export function usePlatformRules() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: rulesKey(orgId ?? "none"),
    queryFn: () => api<PlatformRule[]>("/platform-rules"),
    enabled: !!orgId,
  });
}

function useRuleMutation<TVars>(request: (vars: TVars) => Promise<PlatformRule>) {
  const orgId = useOrgId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: (rule) => {
      queryClient.setQueryData<PlatformRule[]>(rulesKey(orgId!), (rules) =>
        rules?.map((r) => (r.platform === rule.platform ? rule : r)),
      );
    },
  });
}

export const useUpdatePlatformRule = () =>
  useRuleMutation(({ platform, ...body }: Partial<Omit<PlatformRule, "updated_at">> & { platform: Platform }) =>
    api<PlatformRule>(`/platform-rules/${platform}`, { method: "PATCH", body }),
  );

export const useResetPlatformRule = () =>
  useRuleMutation((platform: Platform) =>
    api<PlatformRule>(`/platform-rules/${platform}/reset`, { method: "POST" }),
  );
