import type { Metadata } from "next";

import { ApprovalList } from "@/components/approvals/approval-list";

export const metadata: Metadata = { title: "Approvals" };

export default function ApprovalsPage() {
  return <ApprovalList />;
}
