import { cookies } from "next/headers";

import { LandingPage } from "@/components/landing/landing-page";

// Supabase mode stores the session as sb-<ref>-auth-token (possibly chunked).
const SUPABASE_COOKIE = /^sb-[^-]+-auth-token(\.\d+)?$/;

export default async function Home() {
  const jar = await cookies();
  const signedIn = jar.has("cp_session") || jar.getAll().some((c) => SUPABASE_COOKIE.test(c.name));
  return <LandingPage signedIn={signedIn} />;
}
