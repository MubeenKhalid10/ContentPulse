"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useOrgId } from "@/hooks/use-organization";
import { api } from "@/lib/api";
import type { NotificationPage } from "@/types/api";

const key = (orgId: string | null | undefined) => ["org", orgId ?? "none", "notifications"] as const;

/** The signed-in person's own notifications in the active organization. */
export function useNotifications() {
  const orgId = useOrgId();
  return useQuery({
    queryKey: key(orgId),
    queryFn: () => api<NotificationPage>("/notifications?limit=30"),
    enabled: !!orgId,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
}

export function useMarkNotificationsRead() {
  const orgId = useOrgId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string | "all") =>
      api<void>(id === "all" ? "/notifications/read-all" : `/notifications/${id}/read`, { method: "POST" }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: key(orgId) }),
  });
}
