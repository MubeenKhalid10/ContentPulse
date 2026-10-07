import type { Metadata } from "next";

import { TrendsExplorer } from "@/components/trends/trends-explorer";

export const metadata: Metadata = { title: "Trends" };

export default function TrendsPage() {
  return <TrendsExplorer />;
}
