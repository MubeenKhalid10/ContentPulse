import type { Metadata } from "next";

import { AdminOnly } from "@/components/approvals/admin-only";
import { ApprovalList } from "@/components/approvals/approval-list";

export const metadata: Metadata = { title: "Approvals" };

export default function ApprovalsPage() {
  return <AdminOnly><ApprovalList /></AdminOnly>;
}
