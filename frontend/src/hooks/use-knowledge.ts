"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useOrgId } from "@/hooks/use-organization";
import { api } from "@/lib/api";
import type {
  DocumentPage,
  JobStarted,
  KnowledgeDocumentDetail,
  KnowledgeJob,
  KnowledgeSearchResponse,
  KnowledgeSummary,
} from "@/types/api";

const base = (orgId: string) => `/organizations/${orgId}/knowledge`;
const root = (orgId: string) => ["org", orgId, "knowledge"] as const;

/** Summary refreshes every 2s while a crawl/re-index is running. */
export function useKnowledgeSummary({ enabled = true }: { enabled?: boolean } = {}) {
  const orgId = useOrgId();
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "summary"],
    queryFn: () => api<KnowledgeSummary>(`${base(orgId!)}/summary`),
    enabled: enabled && !!orgId,
    refetchInterval: (query) => (query.state.data?.active_job ? 2000 : false),
  });
}

export type DocumentFilter = "all" | "indexed" | "failed" | "excluded";

export function useKnowledgeDocuments(filter: DocumentFilter, q: string, page: number, pageSize = 25) {
  const orgId = useOrgId();
  const params = new URLSearchParams({ limit: String(pageSize), offset: String(page * pageSize) });
  if (filter !== "all") params.set("status", filter);
  if (q.trim()) params.set("q", q.trim());
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "documents", filter, q.trim(), page],
    queryFn: () => api<DocumentPage>(`${base(orgId!)}/documents?${params}`),
    enabled: !!orgId,
    placeholderData: keepPreviousData,
  });
}

export function useKnowledgeDocument(documentId: string | null) {
  const orgId = useOrgId();
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "document", documentId],
    queryFn: () => api<KnowledgeDocumentDetail>(`${base(orgId!)}/documents/${documentId}`),
    enabled: !!orgId && !!documentId,
  });
}

function useKnowledgeMutation<TVars, TResult>(request: (orgId: string, vars: TVars) => Promise<TResult>) {
  const orgId = useOrgId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: TVars) => request(orgId!, vars),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: root(orgId!) });
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "dashboard"] });
    },
  });
}

export const useStartCrawl = () =>
  useKnowledgeMutation((orgId, body: { url?: string; max_pages?: number }) =>
    api<JobStarted>(`${base(orgId)}/crawl`, { method: "POST", body }),
  );

export const useReindex = () =>
  useKnowledgeMutation<void, JobStarted>((orgId) =>
    api<JobStarted>(`${base(orgId)}/reindex`, { method: "POST" }),
  );

export const useCancelJob = () =>
  useKnowledgeMutation((orgId, jobId: string) =>
    api<KnowledgeJob>(`${base(orgId)}/jobs/${jobId}/cancel`, { method: "POST" }),
  );

export const useCreateDocument = () =>
  useKnowledgeMutation((orgId, body: { title: string; content: string }) =>
    api<KnowledgeDocumentDetail>(`${base(orgId)}/documents`, { method: "POST", body }),
  );

export const useUpdateDocument = () =>
  useKnowledgeMutation(
    (orgId, { id, ...body }: { id: string; excluded?: boolean; title?: string; content?: string }) =>
      api<KnowledgeDocumentDetail>(`${base(orgId)}/documents/${id}`, { method: "PATCH", body }),
  );

export const useDeleteDocument = () =>
  useKnowledgeMutation((orgId, id: string) =>
    api<void>(`${base(orgId)}/documents/${id}`, { method: "DELETE" }),
  );

export function useKnowledgeSearch() {
  const orgId = useOrgId();
  return useMutation({
    mutationFn: (query: string) =>
      api<KnowledgeSearchResponse>(`${base(orgId!)}/search`, { method: "POST", body: { query, limit: 8 } }),
  });
}
