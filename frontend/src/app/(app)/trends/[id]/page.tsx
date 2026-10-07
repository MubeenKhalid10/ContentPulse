import type { Metadata } from "next";

import { TrendDetailView } from "@/components/trends/trend-detail";

export const metadata: Metadata = { title: "Trend" };

export default async function TrendPage({ params }: PageProps<"/trends/[id]">) {
  const { id } = await params;
  return <TrendDetailView id={id} />;
}
