import type { Metadata } from "next";

import { SourcesManager } from "@/components/trends/sources-manager";

export const metadata: Metadata = { title: "Discovery Sources" };

export default function TrendSourcesPage() {
  return <SourcesManager />;
}
