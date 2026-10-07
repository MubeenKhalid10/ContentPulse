import type { Metadata } from "next";

import { OrganizationProfile } from "@/components/organization/organization-profile";

export const metadata: Metadata = { title: "Organization profile" };

export default function OrganizationProfilePage() {
  return <OrganizationProfile />;
}
