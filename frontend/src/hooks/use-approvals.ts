"use client";

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { useOrgId } from "@/hooks/use-organization";
import { api, apiList } from "@/lib/api";
import type {
  ApprovalComment,
  ChangeRequest,
  ChangeRequestPage,
  ChangeScope,
  ApprovalDetail,
  ApprovalFilter,
  ApprovalPage,
  ApprovalStage,
  Platform,
  PostDetail,
} from "@/types/api";
import { SIGNED_LINK_REFRESH_MS, signedLinkQuery } from "@/lib/signed-links";

// Approval routes use the active organization (X-Organization-Id header).
const root = (orgId: string) => ["org", orgId, "approvals"] as const;

export function useApprovals(
  stage: ApprovalStage,
  status: ApprovalFilter,
  platform: "" | Platform,
  limit = 30,
) {
  const orgId = useOrgId();
  const params = new URLSearchParams({ stage, status, limit: String(limit) });
  if (platform) params.set("platform", platform);
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "list", params.toString()],
    queryFn: () => apiList<ApprovalPage>("/approvals", params),
    enabled: !!orgId,
    placeholderData: keepPreviousData,
    refetchInterval: SIGNED_LINK_REFRESH_MS,
    ...signedLinkQuery,
  });
}

export function useApproval(id: string) {
  const orgId = useOrgId();
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "detail", id],
    queryFn: () => api<ApprovalDetail>(`/approvals/${id}`),
    enabled: !!orgId,
    refetchInterval: SIGNED_LINK_REFRESH_MS,
    ...signedLinkQuery,
  });
}

function useApprovalMutation<TVars>(
  request: (vars: TVars) => Promise<ApprovalDetail>,
) {
  const orgId = useOrgId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: (approval) => {
      queryClient.setQueryData(
        [...root(orgId!), "detail", approval.id],
        approval,
      );
      queryClient.invalidateQueries({ queryKey: root(orgId!) });
      // A decision moves the post and its design task.
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "content"] });
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "design"] });
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "dashboard"] });
    },
  });
}

export const useApprove = () =>
  useApprovalMutation(({ id, comment }: { id: string; comment?: string }) =>
    api<ApprovalDetail>(`/approvals/${id}/approve`, {
      method: "POST",
      body: { comment: comment || null },
    }),
  );

/** Approve several submissions at once (ids are approval ids); reports how many worked. */
export function useApproveAll() {
  const orgId = useOrgId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (ids: string[]) => {
      const result: { ok: number; failed: number; error?: unknown } = {
        ok: 0,
        failed: 0,
      };
      for (const id of ids) {
        try {
          await api<ApprovalDetail>(`/approvals/${id}/approve`, {
            method: "POST",
            body: { comment: null },
          });
          result.ok += 1;
        } catch (e) {
          result.failed += 1;
          result.error ??= e;
        }
      }
      return result;
    },
    onSettled: () => {
      for (const key of ["approvals", "content", "design", "dashboard"]) {
        queryClient.invalidateQueries({ queryKey: ["org", orgId, key] });
      }
    },
  });
}

export const useRequestChanges = () =>
  useApprovalMutation(
    ({
      id,
      comment,
      scope,
    }: {
      id: string;
      comment: string;
      scope: "design" | "copy" | "both";
    }) =>
      api<ApprovalDetail>(`/approvals/${id}/request-changes`, {
        method: "POST",
        body: { comment, scope },
      }),
  );

/** Admin: request changes to already-approved (locked) work. */
export const useReopen = () =>
  useApprovalMutation(
    ({
      id,
      comment,
      scope,
    }: {
      id: string;
      comment: string;
      scope: "design" | "copy" | "both";
    }) =>
      api<ApprovalDetail>(`/approvals/${id}/reopen`, {
        method: "POST",
        body: { comment, scope },
      }),
  );

export const useReject = () =>
  useApprovalMutation(({ id, comment }: { id: string; comment?: string }) =>
    api<ApprovalDetail>(`/approvals/${id}/reject`, {
      method: "POST",
      body: { comment: comment || null },
    }),
  );

export const useFinalize = () =>
  useApprovalMutation((id: string) =>
    api<ApprovalDetail>(`/approvals/${id}/finalize`, { method: "POST" }),
  );

export const useAddComment = () =>
  useApprovalMutation(({ id, body }: { id: string; body: string }) =>
    api<ApprovalDetail>(`/approvals/${id}/comments`, {
      method: "POST",
      body: { body },
    }),
  );

/** Everything a change request or a comment can move. */
function useReviewRefresh() {
  const orgId = useOrgId();
  const queryClient = useQueryClient();
  return () => {
    for (const key of ["approvals", "content", "design", "dashboard"]) {
      queryClient.invalidateQueries({ queryKey: ["org", orgId, key] });
    }
  };
}

/** Admin: creators' requests to reopen locked work. */
export function useChangeRequests() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "change-requests"],
    queryFn: () => api<ChangeRequestPage>("/approvals/change-requests?limit=100"),
    enabled: !!orgId,
  });
}

/** Creator: ask an admin to reopen locked work. */
export function useCreateChangeRequest() {
  const refresh = useReviewRefresh();
  return useMutation({
    mutationFn: ({ postId, scope, note }: { postId: string; scope: ChangeScope; note: string }) =>
      api<ChangeRequest>(`/content/${postId}/change-requests`, { method: "POST", body: { scope, note } }),
    onSuccess: refresh,
  });
}

export function useAcceptChangeRequest() {
  const refresh = useReviewRefresh();
  return useMutation({
    mutationFn: (id: string) => api<ChangeRequest>(`/approvals/change-requests/${id}/accept`, { method: "POST" }),
    onSuccess: refresh,
  });
}

export function useDeclineChangeRequest() {
  const refresh = useReviewRefresh();
  return useMutation({
    mutationFn: ({ id, comment }: { id: string; comment: string }) =>
      api<ChangeRequest>(`/approvals/change-requests/${id}/decline`, {
        method: "POST",
        body: { comment: comment || null },
      }),
    onSuccess: refresh,
  });
}

/** The review conversation on a post, for everyone who works on it. */
export function usePostComments(postId: string) {
  const orgId = useOrgId();
  return useQuery({
    queryKey: ["org", orgId ?? "none", "content", "comments", postId],
    queryFn: () => api<ApprovalComment[]>(`/content/${postId}/comments`),
    enabled: !!orgId,
  });
}

export function useAddPostComment() {
  const refresh = useReviewRefresh();
  return useMutation({
    mutationFn: ({ postId, body }: { postId: string; body: string }) =>
      api<ApprovalComment[]>(`/content/${postId}/comments`, { method: "POST", body: { body } }),
    onSuccess: refresh,
  });
}

/** Studio: send the post back for approval after copy-only changes. */
export function useResubmitPost() {
  const orgId = useOrgId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) =>
      api<PostDetail>(`/content/${id}/resubmit`, {
        method: "POST",
        body: { note: note || null },
      }),
    onSuccess: (post) => {
      queryClient.setQueryData(
        ["org", orgId, "content", "detail", post.id],
        post,
      );
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "content"] });
      queryClient.invalidateQueries({ queryKey: root(orgId!) });
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "design"] });
    },
  });
}
