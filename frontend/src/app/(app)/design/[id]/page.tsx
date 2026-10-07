import type { Metadata } from "next";

import { DesignTaskPage } from "@/components/design/task-page";

export const metadata: Metadata = { title: "Design task" };

export default async function TaskPage({ params }: PageProps<"/design/[id]">) {
  const { id } = await params;
  return <DesignTaskPage id={id} />;
}
