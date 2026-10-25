import type { Metadata } from "next";

import { TopicsExplorer } from "@/components/topics/topics-explorer";

export const metadata: Metadata = { title: "Shortlist & plans" };

export default function TopicsPage() {
  return <TopicsExplorer />;
}
