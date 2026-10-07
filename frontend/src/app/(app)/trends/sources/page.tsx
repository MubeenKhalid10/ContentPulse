import type { Metadata } from "next";

import { SourcesManager } from "@/components/trends/sources-manager";

export const metadata: Metadata = { title: "Trend sources" };

export default function TrendSourcesPage() {
  return <SourcesManager />;
}
