import type { Metadata } from "next";

import { PostOpener } from "@/components/content/post-opener";

export const metadata: Metadata = { title: "Post" };

/** A post opened from outside its section (topic, dashboard) lands on its current step. */
export default async function OpenPostPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <PostOpener id={id} />;
}
