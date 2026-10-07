import type { Metadata } from "next";

import { ActivityLog } from "@/components/activity/activity-log";

export const metadata: Metadata = { title: "Activity log" };

export default function ActivityPage() {
  return <ActivityLog />;
}
