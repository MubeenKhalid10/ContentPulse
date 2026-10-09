"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useOrgId } from "@/hooks/use-organization";
import { api, ApiError } from "@/lib/api";
import type { LogoPosition } from "@/lib/logo";
import type { DesignTaskDetail, DesignTaskFilter, DesignTaskPage, Platform, UploadTicket } from "@/types/api";
import { pollOrRefresh, signedLinkQuery } from "@/lib/signed-links";

// Design routes use the active organization (X-Organization-Id header).
const root = (orgId: string) => ["org", orgId, "design"] as const;

export interface DesignFilters {
  status: DesignTaskFilter;
  mine: boolean;
  platform: "" | Platform;
  q: string;
}

export function useDesignTasks(filters: DesignFilters, limit = 30) {
  const orgId = useOrgId();
  const params = new URLSearchParams({ status: filters.status, limit: String(limit) });
  if (filters.mine) params.set("mine", "true");
  if (filters.platform) params.set("platform", filters.platform);
  if (filters.q.trim()) params.set("q", filters.q.trim());
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "list", params.toString()],
    queryFn: () => api<DesignTaskPage>(`/design/tasks?${params}`),
    enabled: !!orgId,
    placeholderData: keepPreviousData,
  });
}

export function useDesignTask(id: string) {
  const orgId = useOrgId();
  return useQuery({
    queryKey: [...root(orgId ?? "none"), "detail", id],
    queryFn: () => api<DesignTaskDetail>(`/design/tasks/${id}`),
    enabled: !!orgId,
    // Poll while the AI is still writing the brief or drawing an image.
    refetchInterval: (query) => {
      const task = query.state.data;
      const drawing = task?.image_job && ["queued", "running"].includes(task.image_job.status);
      return pollOrRefresh(task?.ai_brief_pending || drawing ? 2000 : false);
    },
    ...signedLinkQuery,
  });
}

function useTaskMutation<TVars>(request: (vars: TVars) => Promise<DesignTaskDetail>) {
  const orgId = useOrgId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: (task) => {
      queryClient.setQueryData([...root(orgId!), "detail", task.id], task);
      queryClient.invalidateQueries({ queryKey: root(orgId!) });
      // The post's status moves with the task.
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "content"] });
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "dashboard"] });
      // Submitting opens an approval round.
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "approvals"] });
    },
  });
}

export const useAssignTask = () =>
  useTaskMutation(({ id, assigneeId }: { id: string; assigneeId: string | null }) =>
    api<DesignTaskDetail>(`/design/tasks/${id}/assign`, { method: "POST", body: { assignee_id: assigneeId } }),
  );

export const useStartTask = () =>
  useTaskMutation((id: string) => api<DesignTaskDetail>(`/design/tasks/${id}/start`, { method: "POST" }));

export const useGenerateImage = () =>
  useTaskMutation((id: string) => api<DesignTaskDetail>(`/design/tasks/${id}/generate-image`, { method: "POST" }));

export const useSubmitTask = () =>
  useTaskMutation((id: string) => api<DesignTaskDetail>(`/design/tasks/${id}/submit`, { method: "POST" }));

export type BriefEdit = Partial<
  Pick<
    DesignTaskDetail,
    "format" | "dimensions" | "visual_concept" | "headline" | "supporting_text" | "slide_structure" | "visual_elements" | "cta" | "designer_notes"
  >
> & {
  /** This post's colours; null goes back to the brand's. */
  colors?: string[] | null;
  /** This post's logo spot; null goes back to the brand default. */
  logo_position?: LogoPosition | null;
};

export const useUpdateBrief = () =>
  useTaskMutation(({ id, ...body }: BriefEdit & { id: string }) =>
    api<DesignTaskDetail>(`/design/tasks/${id}`, { method: "PATCH", body }),
  );

/** Send one file to its signed URL, reporting progress (fetch can't). */
function putFile(ticket: UploadTicket, file: File, onProgress: (loaded: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(ticket.method, ticket.url);
    for (const [name, value] of Object.entries(ticket.headers)) xhr.setRequestHeader(name, value);
    xhr.upload.onprogress = (e) => onProgress(e.loaded);
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) return resolve();
      let message = `Upload failed (${xhr.status}).`;
      try {
        message = JSON.parse(xhr.responseText)?.error?.message ?? message;
      } catch {
        // S3 answers in XML; keep the generic message.
      }
      reject(new ApiError(xhr.status, "FILE_UPLOAD_FAILED", message));
    };
    xhr.onerror = () =>
      reject(new ApiError(0, "FILE_UPLOAD_FAILED", "The upload was interrupted. Check your connection and try again."));
    xhr.send(file);
  });
}

/**
 * Spec §41: request a signed URL per file, upload straight to storage, then
 * register the files with the API as one new creative version.
 */
export function useUploadCreatives() {
  const orgId = useOrgId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      taskId,
      files,
      note,
      onProgress,
    }: {
      taskId: string;
      files: File[];
      note?: string;
      onProgress?: (fraction: number) => void;
    }) => {
      const total = files.reduce((sum, f) => sum + f.size, 0) || 1;
      const loaded = new Array(files.length).fill(0);
      const uploaded: { storage_key: string; file_name: string }[] = [];
      for (const [i, file] of files.entries()) {
        const ticket = await api<UploadTicket>(`/design/tasks/${taskId}/uploads`, {
          method: "POST",
          body: { file_name: file.name, file_type: file.type, file_size: file.size },
        });
        await putFile(ticket, file, (bytes) => {
          loaded[i] = bytes;
          onProgress?.(loaded.reduce((a, b) => a + b, 0) / total);
        });
        uploaded.push({ storage_key: ticket.storage_key, file_name: file.name });
      }
      return api<DesignTaskDetail>(`/design/tasks/${taskId}/assets`, {
        method: "POST",
        body: { files: uploaded, note: note || null },
      });
    },
    onSuccess: (task) => {
      queryClient.setQueryData([...root(orgId!), "detail", task.id], task);
      queryClient.invalidateQueries({ queryKey: root(orgId!) });
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "content"] });
    },
  });
}
