import type { Metadata } from "next";

import { ContentSetup } from "@/components/organization/workspace-settings";

export const metadata: Metadata = { title: "Audience & platforms" };

export default function ContentSetupPage() {
  return <ContentSetup />;
}
