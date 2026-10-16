import type { Metadata } from "next";

import { ApprovalList } from "@/components/approvals/approval-list";

export const metadata: Metadata = { title: "Approve posts" };

export default function ApprovalsPage() {
  return <ApprovalList />;
}
