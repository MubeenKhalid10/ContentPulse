"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useOrgId } from "@/hooks/use-organization";
import { api } from "@/lib/api";
import type { ApprovalDetail, ApprovalFilter, ApprovalPage, Platform, PostDetail } from "@/types/api";
import { SIGNED_LINK_REFRESH_MS, signedLinkQuery } from "@/lib/signed-links";

// Approval routes use the active organization (X-Organization-Id header).
const root = (orgId: string) => ["org", orgId, "approvals"] as const;

export function useApprovals(status: ApprovalFilter, platform: "" | Platform, limit = 30) {
  const orgId = useOrgId();
  const params = new URLSearchParams({ status, limit: String(limit) });
  if (platform) params.set("platform", platform);
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "list", params.toString()],
    queryFn: () => api<ApprovalPage>(`/approvals?${params}`),
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

function useApprovalMutation<TVars>(request: (vars: TVars) => Promise<ApprovalDetail>) {
  const orgId = useOrgId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: (approval) => {
      queryClient.setQueryData([...root(orgId!), "detail", approval.id], approval);
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
    api<ApprovalDetail>(`/approvals/${id}/approve`, { method: "POST", body: { comment: comment || null } }),
  );

export const useRequestChanges = () =>
  useApprovalMutation(({ id, comment, scope }: { id: string; comment: string; scope: "design" | "copy" | "both" }) =>
    api<ApprovalDetail>(`/approvals/${id}/request-changes`, { method: "POST", body: { comment, scope } }),
  );

export const useReject = () =>
  useApprovalMutation(({ id, comment }: { id: string; comment?: string }) =>
    api<ApprovalDetail>(`/approvals/${id}/reject`, { method: "POST", body: { comment: comment || null } }),
  );

export const useFinalize = () =>
  useApprovalMutation((id: string) => api<ApprovalDetail>(`/approvals/${id}/finalize`, { method: "POST" }));

export const useAddComment = () =>
  useApprovalMutation(({ id, body }: { id: string; body: string }) =>
    api<ApprovalDetail>(`/approvals/${id}/comments`, { method: "POST", body: { body } }),
  );

/** Studio: send the post back for approval after copy-only changes. */
export function useResubmitPost() {
  const orgId = useOrgId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) =>
      api<PostDetail>(`/content/${id}/resubmit`, { method: "POST", body: { note: note || null } }),
    onSuccess: (post) => {
      queryClient.setQueryData(["org", orgId, "content", "detail", post.id], post);
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "content"] });
      queryClient.invalidateQueries({ queryKey: root(orgId!) });
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "design"] });
    },
  });
}
