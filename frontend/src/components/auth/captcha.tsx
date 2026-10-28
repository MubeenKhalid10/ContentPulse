"use client";

import { useState } from "react";
import { Turnstile } from "@marsidev/react-turnstile";

import { useAuthConfig } from "@/lib/auth";
import { Alert, AlertDescription } from "@/components/ui/alert";

export function AuthCaptcha({
  onToken,
}: {
  onToken: (token: string | null) => void;
}) {
  const { data: config } = useAuthConfig();
  const [status, setStatus] = useState<"pending" | "ready" | "failed">("pending");
  if (!config) return null;
  if (config.provider !== "supabase") return null;
  if (!config.turnstile_site_key) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          CAPTCHA is enabled in Supabase, but the Turnstile site key is not
          configured for this frontend. Add <code>TURNSTILE_SITE_KEY</code> to
          the backend environment and restart it.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="grid gap-1.5">
      <Turnstile
        siteKey={config.turnstile_site_key}
        onSuccess={(token) => {
          setStatus("ready");
          onToken(token);
        }}
        onExpire={() => {
          setStatus("pending");
          onToken(null);
        }}
        onError={() => {
          setStatus("failed");
          onToken(null);
        }}
      />
      {status === "pending" && (
        <p role="status" className="text-xs text-muted-foreground">
          Verifying you&apos;re human…
        </p>
      )}
      {status === "failed" && (
        <p role="alert" className="text-xs text-destructive">
          We couldn&apos;t verify you&apos;re human. Reload the page and try again.
        </p>
      )}
    </div>
  );
}
