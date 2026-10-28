/**
 * An external link from a feed, a crawled page or a user is only rendered as a
 * link when it is plain http(s): `javascript:`, `data:` and the like become text.
 */
export function safeUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const { protocol } = new URL(url);
    return protocol === "http:" || protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}
