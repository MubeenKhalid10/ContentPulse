import { MailCheck } from "lucide-react";
import Link from "next/link";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/** Shown after Supabase sends a confirmation or password-reset email. */
export function CheckEmail({ title, email, body }: { title: string; email: string; body: string }) {
  return (
    <Card>
      <CardHeader>
        <MailCheck className="mb-2 size-6 text-primary" aria-hidden />
        <CardTitle role="heading" aria-level={1} className="text-xl">{title}</CardTitle>
        <CardDescription>
          We sent an email to <span className="font-medium text-foreground">{email}</span>. {body}
        </CardDescription>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        Open the link in this browser. Nothing arrived after a few minutes? Check your spam folder, or{" "}
        <Link href="/login" className="font-medium text-foreground underline-offset-4 hover:underline">
          go back to sign in
        </Link>
        .
      </CardContent>
    </Card>
  );
}
