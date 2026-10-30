import type { Metadata } from "next";

import { AdminOnly } from "@/components/approvals/admin-only";
import { ReviewPage } from "@/components/approvals/review-page";

export const metadata: Metadata = { title: "Review" };

export default async function ApprovalPage({ params }: PageProps<"/approvals/[id]">) {
  const { id } = await params;
  return (
    <AdminOnly>
      <ReviewPage id={id} />
    </AdminOnly>
  );
}
