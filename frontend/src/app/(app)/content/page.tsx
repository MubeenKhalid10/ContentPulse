import type { Metadata } from "next";

import { ContentList } from "@/components/content/content-list";

export const metadata: Metadata = { title: "Content studio" };

export default function ContentPage() {
  return <ContentList />;
}
