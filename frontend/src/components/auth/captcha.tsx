"use client";

import { Turnstile } from "@marsidev/react-turnstile";

import { useAuthConfig } from "@/lib/supabase-config";
import { Alert, AlertDescription } from "@/components/ui/alert";

export function AuthCaptcha({
  onToken,
}: {
  onToken: (token: string | null) => void;
}) {
  const { data: config } = useAuthConfig();
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
    <Turnstile
      siteKey={config.turnstile_site_key}
      onSuccess={onToken}
      onExpire={() => onToken(null)}
      onError={() => onToken(null)}
    />
  );
}
