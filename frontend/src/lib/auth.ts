"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { api, ApiError, setActiveOrgId } from "@/lib/api";
import { authRedirect, getAuthConfig, getSupabase, supabaseErrorMessage } from "@/lib/supabase";
import type { Me, Permission, Session } from "@/types/api";

export const meQueryKey = ["auth", "me"] as const;

export function useMe() {
  return useQuery({
    queryKey: meQueryKey,
    queryFn: () => api<Me>("/auth/me"),
    retry: false,
    staleTime: 60_000,
  });
}

/** "local" (email/password with our API) or "supabase" (Supabase Auth). */
export function useAuthConfig() {
  return useQuery({ queryKey: ["auth", "config"], queryFn: getAuthConfig, staleTime: Infinity });
}

/** Permission check for hiding controls. The backend still enforces it. */
export function useCan() {
  const { data } = useMe();
  return (permission: Permission) => data?.permissions.includes(permission) ?? false;
}

function authFailure(message: string, status = 401): ApiError {
  return new ApiError(status, status === 401 ? "UNAUTHORIZED" : "VALIDATION_ERROR", supabaseErrorMessage(message));
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { email: string; password: string }): Promise<{ user: Me }> => {
      const supabase = await getSupabase();
      if (!supabase) return api<Session>("/auth/login", { method: "POST", body });
      const { error } = await supabase.auth.signInWithPassword(body);
      if (error) throw authFailure(error.message);
      // First request provisions/links the ContentPulse user for this identity.
      return { user: await api<Me>("/auth/me") };
    },
    onSuccess: ({ user }) => {
      setActiveOrgId(user.organization_id);
      queryClient.setQueryData(meQueryKey, user);
    },
  });
}

export interface RegisterResult {
  user: Me | null;
  /** Supabase sent a confirmation email; no session until it is clicked. */
  needsConfirmation: boolean;
}

export function useRegister() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { email: string; password: string; full_name: string }): Promise<RegisterResult> => {
      const supabase = await getSupabase();
      if (!supabase) {
        const session = await api<Session>("/auth/register", { method: "POST", body });
        return { user: session.user, needsConfirmation: false };
      }
      const { data, error } = await supabase.auth.signUp({
        email: body.email,
        password: body.password,
        options: {
          data: { full_name: body.full_name },
          emailRedirectTo: authRedirect("/auth/callback", "/onboarding"),
        },
      });
      if (error) throw authFailure(error.message, 400);
      if (!data.session) return { user: null, needsConfirmation: true };
      return { user: await api<Me>("/auth/me"), needsConfirmation: false };
    },
    onSuccess: ({ user }) => {
      setActiveOrgId(null);
      if (user) queryClient.setQueryData(meQueryKey, user);
    },
  });
}

/** Sign out everywhere this browser is signed in (Supabase + API cookie). */
export async function signOutEverywhere() {
  const supabase = await getSupabase().catch(() => null);
  await Promise.allSettled([
    supabase?.auth.signOut(),
    api<void>("/auth/logout", { method: "POST" }),
  ]);
  setActiveOrgId(null);
}

export function useLogout() {
  const queryClient = useQueryClient();
  const router = useRouter();
  return useMutation({
    mutationFn: signOutEverywhere,
    onSettled: () => {
      queryClient.clear();
      router.replace("/login");
    },
  });
}

/** Switch the active organization and refetch everything for it. */
export function useSwitchOrganization() {
  const queryClient = useQueryClient();
  return (organizationId: string) => {
    setActiveOrgId(organizationId);
    queryClient.invalidateQueries();
  };
}
