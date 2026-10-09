import type { Metadata } from "next";

import { ContentSetup } from "@/components/organization/workspace-settings";

export const metadata: Metadata = { title: "Content setup" };

export default function ContentSetupPage() {
  return <ContentSetup />;
}
