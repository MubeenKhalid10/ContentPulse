"use client";

import { CopyIcon, DownloadIcon, LoaderCircleIcon, Share2Icon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { CreativeVersion, Platform, PostVersion } from "@/types/api";

/** The article as Markdown with its SEO details as front matter, ready for a CMS. */
function articleMarkdown(title: string | null, copy: PostVersion | null) {
  const seo = copy?.meta.blog ?? {};
  const quote = (v: string) => JSON.stringify(v);
  const front = [
    seo.meta_title && `meta_title: ${quote(seo.meta_title)}`,
    seo.meta_description && `meta_description: ${quote(seo.meta_description)}`,
    seo.slug && `slug: ${seo.slug}`,
    seo.keywords?.length && `keywords: [${seo.keywords.map(quote).join(", ")}]`,
  ].filter(Boolean);
  const heading = seo.seo_title || title;
  return [
    front.length ? `---\n${front.join("\n")}\n---` : null,
    heading ? `# ${heading}` : null,
    copy?.hook,
    copy?.body,
    copy?.cta,
  ]
    .map((p) => p?.trim())
    .filter(Boolean)
    .join("\n\n");
}

/** Blog is a content-creation platform: export the article, never auto-publish. */
function ArticleExport({ title, copy }: { title: string | null; copy: PostVersion | null }) {
  const markdown = articleMarkdown(title, copy);
  const copyArticle = async () => {
    try {
      await navigator.clipboard.writeText(markdown);
      toast.success("Article copied as Markdown. Paste it into your CMS.");
    } catch {
      toast.error("Couldn't copy the article.");
    }
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${copy?.meta.blog?.slug || "article"}.md`;
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="flex gap-1.5">
      <Button size="sm" disabled={!markdown} onClick={copyArticle}>
        <CopyIcon />
        Copy article
      </Button>
      <Button size="sm" variant="outline" disabled={!markdown} onClick={download}>
        <DownloadIcon />
        Download .md
      </Button>
    </div>
  );
}

export function SharePostButton(props: {
  title: string | null;
  platform: Platform;
  copy: PostVersion | null;
  creative: CreativeVersion | null;
}) {
  if (props.platform === "blog") return <ArticleExport title={props.title} copy={props.copy} />;
  return <SocialShareButton {...props} />;
}

function SocialShareButton({
  title,
  platform,
  copy,
  creative,
}: {
  title: string | null;
  platform: Platform;
  copy: PostVersion | null;
  creative: CreativeVersion | null;
}) {
  const [sharing, setSharing] = useState(false);
  const caption = [copy?.hook, copy?.body, copy?.cta, ...(copy?.hashtags ?? []).map((tag) => `#${tag.replace(/^#/, "")}`)]
    .filter(Boolean)
    .join("\n\n");
  const files = creative?.files ?? [];

  const platformUrl = () => {
    const encoded = encodeURIComponent(caption);
    switch (platform) {
      case "x":
        return `https://twitter.com/intent/post?text=${encoded}`;
      case "linkedin":
        return "https://www.linkedin.com/feed/?shareActive=true";
      case "facebook":
        return `https://www.facebook.com/sharer/sharer.php?quote=${encoded}`;
      case "instagram":
      default:
        return "https://www.instagram.com/";
    }
  };

  const share = async () => {
    if (!caption && files.length === 0) {
      toast.error("This final post has no copy or media to share.");
      return;
    }
    setSharing(true);
    try {
      if (files.length > 0 && navigator.share && navigator.canShare) {
        const sharedFiles = await Promise.all(
          files.map(async (file) => {
            const response = await fetch(file.url);
            if (!response.ok) throw new Error(`Unable to download ${file.file_name}`);
            return new File([await response.blob()], file.file_name, { type: file.file_type });
          }),
        );
        const shareData = { title: title ?? "ContentPulse post", text: caption, files: sharedFiles };
        if (navigator.canShare({ files: sharedFiles })) {
          await navigator.share(shareData);
          return;
        }
      }

      window.open(platformUrl(), "_blank", "noopener,noreferrer");
      if (caption && navigator.clipboard) {
        await navigator.clipboard.writeText(caption);
      }
      toast.success(
        files.length
          ? "Caption copied. Attach the approved media in the platform composer."
          : "Caption copied and platform composer opened.",
      );
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      toast.error("Could not prepare this post for sharing.");
    } finally {
      setSharing(false);
    }
  };

  return (
    <Button size="sm" variant="default" disabled={sharing} onClick={share}>
      {sharing ? <LoaderCircleIcon className="animate-spin" /> : <Share2Icon />}
      Share
    </Button>
  );
}
