import type { Metadata } from "next";

import { PlatformPlaybook } from "@/components/organization/platform-playbook";

export const metadata: Metadata = { title: "Platform playbook" };

export default function PlatformPlaybookPage() {
  return <PlatformPlaybook />;
}
