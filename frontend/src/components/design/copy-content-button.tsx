"use client";

import { CopyIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { CreativeFile } from "@/types/api";

const escapeHtml = (value: string) =>
  value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/** A file as a data URL, so the image travels inside the clipboard instead of as a link. */
async function dataUrl(file: CreativeFile): Promise<string> {
  const response = await fetch(file.url);
  if (!response.ok) throw new Error(`Unable to read ${file.file_name}`);
  const blob = await response.blob();
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

/**
 * Copies the post's text together with its design images. Pasted into a rich editor (an email,
 * a document, a CMS) it arrives as text followed by the pictures; pasted as plain text it is
 * just the text.
 */
export function CopyContentButton({ text, images }: { text: string; images: CreativeFile[] }) {
  const [busy, setBusy] = useState(false);
  const pictures = images.filter((f) => f.file_type.startsWith("image/"));

  const copy = async () => {
    setBusy(true);
    try {
      if (!pictures.length || typeof ClipboardItem === "undefined") {
        await navigator.clipboard.writeText(text);
        toast.success(pictures.length ? "Content copied. This browser can't copy images with it." : "Content copied.");
        return;
      }
      const sources = await Promise.all(pictures.map(dataUrl));
      const html =
        text
          .split(/\n{2,}/)
          .map((p) => `<p>${escapeHtml(p).replace(/\n/g, "<br>")}</p>`)
          .join("") +
        sources.map((src, i) => `<p><img src="${src}" alt="${escapeHtml(pictures[i].file_name)}"></p>`).join("");
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/html": new Blob([html], { type: "text/html" }),
          "text/plain": new Blob([text], { type: "text/plain" }),
        }),
      ]);
      toast.success(`Content copied with ${pictures.length} ${pictures.length === 1 ? "image" : "images"}.`);
    } catch {
      toast.error("Couldn't copy to your clipboard. Allow clipboard access for this site and try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button size="sm" variant="outline" disabled={!text || busy} pending={busy} onClick={copy}>
      <CopyIcon />
      {pictures.length ? "Copy with images" : "Copy content"}
    </Button>
  );
}
