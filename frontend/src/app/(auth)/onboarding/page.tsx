import type { Metadata } from "next";

import { CreateOrganization } from "@/components/organization/create-organization";

export const metadata: Metadata = { title: "Set up your organization" };

export default function OnboardingPage() {
  return <CreateOrganization />;
}
