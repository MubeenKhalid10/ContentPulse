import type { Metadata } from "next";

import { TeamManager } from "@/components/team/team-manager";

export const metadata: Metadata = { title: "Team" };

export default function TeamPage() {
  return <TeamManager />;
}
