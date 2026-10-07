import type { Metadata } from "next";

import { BrandEditor } from "@/components/organization/brand-editor";

export const metadata: Metadata = { title: "Brand" };

export default function BrandPage() {
  return <BrandEditor />;
}
