"use client";

import { CopyIcon, DownloadIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { fetchHandoff } from "@/hooks/use-design";
import { errorMessage } from "@/lib/api";

/**
 * Copy or download the design brief as one document, to send to a designer
 * who works outside the app. `id` is the design task (brief) id.
 */
export function HandoffButtons({ id, size = "sm" }: { id: string; size?: "sm" | "default" }) {
  const [busy, setBusy] = useState(false);
  const run = async (mode: "copy" | "download") => {
    setBusy(true);
    try {
      const doc = await fetchHandoff(id);
      if (mode === "copy") {
        await navigator.clipboard.writeText(doc.markdown);
        toast.success("Design brief copied");
      } else {
        const url = URL.createObjectURL(new Blob([doc.markdown], { type: "text/markdown;charset=utf-8" }));
        const link = document.createElement("a");
        link.href = url;
        link.download = doc.file_name;
        link.click();
        URL.revokeObjectURL(url);
      }
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Button size={size} variant="outline" onClick={() => run("copy")} disabled={busy}>
        <CopyIcon />
        Copy
      </Button>
      <Button size={size} variant="outline" onClick={() => run("download")} disabled={busy}>
        <DownloadIcon />
        Export brief
      </Button>
    </>
  );
}
