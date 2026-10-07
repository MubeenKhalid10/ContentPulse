"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { meQueryKey, useMe } from "@/lib/auth";
import type {
  AuditLogEntry,
  BrandProfile,
  DashboardSummary,
  InviteResponse,
  Member,
  Organization,
  OrganizationService,
  OrganizationSettings,
} from "@/types/api";

/** Active organization id; all org-scoped query keys start with ["org", id]. */
export function useOrgId(): string | undefined {
  return useMe().data?.organization_id ?? undefined;
}

const keys = {
  org: (id: string) => ["org", id] as const,
  settings: (id: string) => ["org", id, "settings"] as const,
  brand: (id: string) => ["org", id, "brand"] as const,
  services: (id: string) => ["org", id, "services"] as const,
  members: (id: string) => ["org", id, "members"] as const,
  dashboard: (id: string) => ["org", id, "dashboard"] as const,
  audit: (id: string) => ["org", id, "audit"] as const,
};

function useOrgQuery<T>(
  key: (id: string) => readonly unknown[],
  path: (id: string) => string,
  enabled = true,
) {
  const orgId = useOrgId();
  return useQuery({
    queryKey: key(orgId ?? "none"),
    queryFn: () => api<T>(path(orgId!)),
    enabled: !!orgId && enabled,
  });
}

export const useOrganization = () =>
  useOrgQuery<Organization>((id) => [...keys.org(id), "profile"], (id) => `/organizations/${id}`);
export const useOrgSettings = () =>
  useOrgQuery<OrganizationSettings>(keys.settings, (id) => `/organizations/${id}/settings`);
export const useBrand = () => useOrgQuery<BrandProfile>(keys.brand, (id) => `/organizations/${id}/brand`);
export const useServices = () =>
  useOrgQuery<OrganizationService[]>(keys.services, (id) => `/organizations/${id}/services`);
export const useMembers = () => useOrgQuery<Member[]>(keys.members, (id) => `/organizations/${id}/members`);
export const useDashboard = () => useOrgQuery<DashboardSummary>(keys.dashboard, () => "/dashboard/summary");
export const useAuditLogs = (enabled = true) =>
  useOrgQuery<AuditLogEntry[]>(keys.audit, (id) => `/organizations/${id}/audit-logs?limit=100`, enabled);

/**
 * Mutation against the active org. On success, refreshes that org's queries
 * (dashboard activity and audit log change with every write).
 */
function useOrgMutation<TVars, TResult>(
  request: (orgId: string, vars: TVars) => Promise<TResult>,
  { refreshMe = false }: { refreshMe?: boolean } = {},
) {
  const orgId = useOrgId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: TVars) => request(orgId!, vars),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.org(orgId!) });
      if (refreshMe) queryClient.invalidateQueries({ queryKey: meQueryKey });
    },
  });
}

export const useUpdateOrganization = () =>
  useOrgMutation(
    (id, body: Partial<Organization>) => api<Organization>(`/organizations/${id}`, { method: "PATCH", body }),
    { refreshMe: true }, // name appears in the org switcher
  );

export const useDeleteOrganization = () =>
  useOrgMutation(
    (id) => api<void>(`/organizations/${id}`, { method: "DELETE" }),
    { refreshMe: true },
  );

export const useUpdateSettings = () =>
  useOrgMutation((id, body: Partial<OrganizationSettings>) =>
    api<OrganizationSettings>(`/organizations/${id}/settings`, { method: "PATCH", body }),
  );

export const useUpdateBrand = () =>
  useOrgMutation((id, body: Partial<BrandProfile>) =>
    api<BrandProfile>(`/organizations/${id}/brand`, { method: "PATCH", body }),
  );

export const useCreateService = () =>
  useOrgMutation((id, body: Omit<OrganizationService, "id" | "created_at">) =>
    api<OrganizationService>(`/organizations/${id}/services`, { method: "POST", body }),
  );

export const useUpdateService = () =>
  useOrgMutation((id, { serviceId, ...body }: Partial<OrganizationService> & { serviceId: string }) =>
    api<OrganizationService>(`/organizations/${id}/services/${serviceId}`, { method: "PATCH", body }),
  );

export const useDeleteService = () =>
  useOrgMutation((id, serviceId: string) =>
    api<void>(`/organizations/${id}/services/${serviceId}`, { method: "DELETE" }),
  );

export const useInviteMember = () =>
  useOrgMutation((id, body: { email: string; role: Member["role"] }) =>
    api<InviteResponse>(`/organizations/${id}/invitations`, { method: "POST", body }),
  );

export const useUpdateMember = () =>
  useOrgMutation(
    (id, { memberId, ...body }: { memberId: string; role?: Member["role"]; status?: Member["status"] }) =>
      api<Member>(`/organizations/${id}/members/${memberId}`, { method: "PATCH", body }),
    { refreshMe: true }, // an admin may change their own role
  );

export const useRemoveMember = () =>
  useOrgMutation(
    (id, memberId: string) => api<void>(`/organizations/${id}/members/${memberId}`, { method: "DELETE" }),
    { refreshMe: true },
  );
