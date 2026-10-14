"use client";

import { useQuery } from "@tanstack/react-query";

import type { AuthConfig } from "@/lib/supabase";

export function useAuthConfig() {
  return useQuery({
    queryKey: ["auth", "config"],
    queryFn: async () => {
      const response = await fetch("/api/v1/auth/config", {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`auth config ${response.status}`);
      return (await response.json()) as AuthConfig;
    },
    staleTime: Infinity,
  });
}
