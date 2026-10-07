/**
 * Design files are served through signed links that expire after 15 minutes
 * (SIGNED_URL_TTL_SECONDS). Queries that return them refetch every 10 minutes
 * and when the tab regains focus, so a link on screen always still works.
 */
export const SIGNED_LINK_REFRESH_MS = 10 * 60_000;

export const signedLinkQuery = {
  staleTime: 5 * 60_000,
  refetchOnWindowFocus: true,
} as const;

/** For a refetchInterval callback: poll fast while busy, else refresh links. */
export function pollOrRefresh(busyMs: number | false): number {
  return busyMs === false ? SIGNED_LINK_REFRESH_MS : busyMs;
}
