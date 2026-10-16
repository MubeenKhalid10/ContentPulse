import type { Metadata } from "next";

import { DesignTaskList } from "@/components/design/task-list";

export const metadata: Metadata = { title: "Add designs" };

export default function DesignPage() {
  return <DesignTaskList />;
}
