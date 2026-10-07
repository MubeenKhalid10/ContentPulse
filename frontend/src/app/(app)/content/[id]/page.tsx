import type { Metadata } from "next";

import { ContentStudio } from "@/components/content/studio";

export const metadata: Metadata = { title: "Post" };

export default async function PostPage({ params }: PageProps<"/content/[id]">) {
  const { id } = await params;
  return <ContentStudio id={id} />;
}
