import type { Metadata } from "next";

import { TopicDetailView } from "@/components/topics/topic-detail";

export const metadata: Metadata = { title: "Topic" };

export default async function TopicPage({ params }: PageProps<"/topics/[id]">) {
  const { id } = await params;
  return <TopicDetailView id={id} />;
}
