"use client";

import { LockIcon } from "lucide-react";
import Link from "next/link";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { useCan } from "@/lib/auth";

/** Approvals are the admin's desk: an old link lands here, with the way to the post's status. */
export function AdminOnly({ children }: { children: React.ReactNode }) {
  if (useCan()("approval.read")) return children;
  return (
    <Alert>
      <LockIcon />
      <AlertTitle>Approvals are for admins</AlertTitle>
      <AlertDescription className="grid gap-2">
        <span>You can follow each post&apos;s status and the admin&apos;s feedback on Write posts and Add designs.</span>
        <Link href="/content" className={buttonVariants({ size: "sm", variant: "outline" }) + " w-fit"}>
          Go to Write posts
        </Link>
      </AlertDescription>
    </Alert>
  );
}
