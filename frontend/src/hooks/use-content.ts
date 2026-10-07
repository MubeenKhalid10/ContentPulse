"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useOrgId } from "@/hooks/use-organization";
import { api } from "@/lib/api";
import type { BlogMeta, DesignFormat, Platform, PostDetail, PostGroup, PostPage, PostVersion } from "@/types/api";
import { pollOrRefresh, signedLinkQuery } from "@/lib/signed-links";

// Content routes use the active organization (X-Organization-Id header).
const root = (orgId: string) => ["org", orgId, "content"] as const;

const generating = (post?: { generation: { status: string } | null }) =>
  post?.generation?.status === "queued" || post?.generation?.status === "running";

export interface ContentFilters {
  status: PostGroup;
  platform: "" | Platform;
  topicId?: string;
  q: string;
}

export function usePosts(filters: ContentFilters, limit = 30) {
  const orgId = useOrgId();
  const params = new URLSearchParams({ status: filters.status, limit: String(limit) });
  if (filters.platform) params.set("platform", filters.platform);
  if (filters.topicId) params.set("topic_id", filters.topicId);
  if (filters.q.trim()) params.set("q", filters.q.trim());
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "list", params.toString()],
    queryFn: () => api<PostPage>(`/content?${params}`),
    enabled: !!orgId,
    placeholderData: keepPreviousData,
    // Poll while any listed post is still being written.
    refetchInterval: (query) => pollOrRefresh(query.state.data?.items.some(generating) ? 3000 : false),
    ...signedLinkQuery,
  });
}

export function usePost(id: string) {
  const orgId = useOrgId();
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "detail", id],
    queryFn: () => api<PostDetail>(`/content/${id}`),
    enabled: !!orgId,
    refetchInterval: (query) => pollOrRefresh(generating(query.state.data) ? 2000 : false),
    ...signedLinkQuery,
  });
}

export function usePostVersions(id: string, currentVersion: number | undefined) {
  const orgId = useOrgId();
  return useQuery({
    // Keyed on the current version so a new save or generation refreshes history.
    queryKey: [...root(orgId ?? "none"), "versions", id, currentVersion],
    queryFn: () => api<PostVersion[]>(`/content/${id}/versions`),
    enabled: !!orgId && currentVersion !== undefined,
  });
}

function useContentMutation<TVars>(request: (vars: TVars) => Promise<PostDetail>) {
  const orgId = useOrgId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: (post) => {
      queryClient.setQueryData([...root(orgId!), "detail", post.id], post);
      queryClient.invalidateQueries({ queryKey: root(orgId!) });
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "dashboard"] });
      // Writing a post approves its plan, shown on the topic page.
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "topics"] });
    },
  });
}

export const useGeneratePost = () =>
  useContentMutation((strategyId: string) =>
    api<PostDetail>("/content/generate", { method: "POST", body: { strategy_id: strategyId } }),
  );

export const useRegenerate = () =>
  useContentMutation(({ id, instructions }: { id: string; instructions?: string }) =>
    api<PostDetail>(`/content/${id}/regenerate`, { method: "POST", body: { instructions: instructions || null } }),
  );

export const useCreateVariant = () =>
  useContentMutation((id: string) => api<PostDetail>(`/content/${id}/variants`, { method: "POST" }));

export interface PostEdit {
  base_version: number;
  title?: string;
  hook?: string | null;
  body?: string | null;
  cta?: string | null;
  hashtags?: string[];
  visual_concept?: string | null;
  design_format?: DesignFormat | null;
  /** Blog posts only; fields sent replace the current ones. */
  blog?: BlogMeta;
  change_note?: string | null;
}

export const useUpdatePost = () =>
  useContentMutation(({ id, ...body }: PostEdit & { id: string }) =>
    api<PostDetail>(`/content/${id}`, { method: "PATCH", body }),
  );

export const useRestoreVersion = () =>
  useContentMutation(({ id, number, base }: { id: string; number: number; base: number }) =>
    api<PostDetail>(`/content/${id}/versions/${number}/restore`, { method: "POST", body: { base_version: base } }),
  );

export type PostAction = "back-to-draft" | "send-to-design" | "archive";

export const usePostAction = () =>
  useContentMutation(({ id, action }: { id: string; action: PostAction }) =>
    api<PostDetail>(`/content/${id}/${action}`, { method: "POST" }),
  );
