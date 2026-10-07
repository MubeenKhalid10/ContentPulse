import type { Metadata } from "next";

import { AcceptInvite } from "@/components/auth/accept-invite";

export const metadata: Metadata = { title: "Join your team" };

export default async function InvitePage({ params }: PageProps<"/invite/[token]">) {
  const { token } = await params;
  return <AcceptInvite token={token} />;
}
