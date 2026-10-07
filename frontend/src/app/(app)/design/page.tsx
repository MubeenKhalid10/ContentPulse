import type { Metadata } from "next";

import { DesignTaskList } from "@/components/design/task-list";

export const metadata: Metadata = { title: "Design" };

export default function DesignPage() {
  return <DesignTaskList />;
}
