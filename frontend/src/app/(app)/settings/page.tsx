import type { Metadata } from "next";

import { SettingsEditor } from "@/components/organization/settings-editor";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return <SettingsEditor />;
}
