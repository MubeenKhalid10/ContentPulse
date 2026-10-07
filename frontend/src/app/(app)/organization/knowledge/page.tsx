import type { Metadata } from "next";

import { KnowledgeBase } from "@/components/knowledge/knowledge-base";

export const metadata: Metadata = { title: "Knowledge base" };

export default function KnowledgePage() {
  return <KnowledgeBase />;
}
