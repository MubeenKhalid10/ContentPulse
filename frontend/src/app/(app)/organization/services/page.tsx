import type { Metadata } from "next";

import { ServicesManager } from "@/components/organization/services-manager";

export const metadata: Metadata = { title: "Services & products" };

export default function ServicesPage() {
  return <ServicesManager />;
}
