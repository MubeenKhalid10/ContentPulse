import type { SignalKey } from "@/types/api";

export const SOURCE_NAMES: Record<string, string> = {
  google_trends: "Google Trends",
  google_news: "Google News",
  hacker_news: "Hacker News",
  reddit: "Reddit",
  rss: "RSS feeds",
  newsapi: "NewsAPI",
  gnews: "GNews",
  x: "X",
  instagram: "Instagram",
  linkedin: "LinkedIn",
};

export const sourceName = (key: string) => SOURCE_NAMES[key] ?? key;

export const SIGNALS: { key: SignalKey; label: string; help: string }[] = [
  { key: "organization_fit", label: "Organization fit", help: "How well the trend matches your services and expertise (AI analysis)." },
  { key: "audience_relevance", label: "Audience relevance", help: "How much your target audience cares (AI analysis)." },
  { key: "keyword_match", label: "Keyword match", help: "Overlap with your tracked keywords and services." },
  { key: "popularity", label: "Popularity", help: "Search volume, votes, engagement or coverage volume." },
  { key: "growth", label: "Growth", help: "How fast attention is increasing." },
  { key: "freshness", label: "Freshness", help: "How recently it was mentioned." },
  { key: "location_relevance", label: "Location", help: "Whether it's trending in your target markets." },
  { key: "source_diversity", label: "Source diversity", help: "How many independent sources report it." },
];

export function scoreTone(score: number | null | undefined): string {
  if (score == null) return "text-muted-foreground";
  if (score >= 45) return "text-primary-strong";
  return "text-muted-foreground";
}

export function marketLabel(code: string, names: Map<string, string>): string {
  return code === "GLOBAL" ? "Global" : (names.get(code) ?? code);
}
