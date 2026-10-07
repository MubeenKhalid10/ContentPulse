"use client";

import {
  BookmarkIcon,
  ChartNoAxesColumnIcon,
  FileTextIcon,
  GlobeIcon,
  HeartIcon,
  MessageCircleIcon,
  Repeat2Icon,
  SendIcon,
  Share2Icon,
  ThumbsUpIcon,
} from "lucide-react";
import { useState } from "react";

import { useOrganization } from "@/hooks/use-organization";
import { cn } from "@/lib/utils";
import type { CreativeFile, Platform } from "@/types/api";

type Social = Exclude<Platform, "blog">;

const LINK_COLOR: Record<Social, string> = {
  linkedin: "text-[#0a66c2] dark:text-[#71b7fb]",
  x: "text-[#1d9bf0]",
  instagram: "text-[#00376b] dark:text-[#e0f1ff]",
  facebook: "text-[#1877f2] dark:text-[#4599ff]",
};
// Roughly where each feed folds a long post behind "more".
const FOLD_AT: Record<Social, number> = { linkedin: 210, x: 280, instagram: 125, facebook: 480 };

function initials(name: string) {
  return name
    .split(/\s+|_/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
}

function Avatar({ name, logo, round = true, size = "size-10" }: { name: string; logo: string | null; round?: boolean; size?: string }) {
  return logo ? (
    // Organization logos are arbitrary URLs: next/image can't optimize them.
    // eslint-disable-next-line @next/next/no-img-element
    <img src={logo} alt="" className={cn(size, "shrink-0 bg-white object-contain ring-1 ring-black/5", round ? "rounded-full" : "rounded-md")} />
  ) : (
    <span
      aria-hidden
      className={cn(
        size,
        "grid shrink-0 place-items-center bg-primary text-xs font-semibold text-primary-foreground",
        round ? "rounded-full" : "rounded-md",
      )}
    >
      {initials(name)}
    </span>
  );
}

/** Post text with hashtags in the platform's link color, folded like the feed. */
function Caption({ text, platform, lead }: { text: string; platform: Social; lead?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const fold = FOLD_AT[platform];
  const long = text.length > fold + 40;
  const shown = long && !open ? text.slice(0, fold).replace(/\s+\S*$/, "") : text;
  return (
    <p className="text-sm leading-snug whitespace-pre-wrap break-words">
      {lead}
      {shown.split(/(#[\p{L}\p{N}_]+)/u).map((part, i) =>
        part.startsWith("#") ? (
          <span key={i} className={cn("font-medium", LINK_COLOR[platform])}>
            {part}
          </span>
        ) : (
          part
        ),
      )}
      {long && (
        <button type="button" className="ml-1 text-muted-foreground hover:underline" onClick={() => setOpen(!open)}>
          {open ? " …less" : "…more"}
        </button>
      )}
    </p>
  );
}

/** The creative as the feed shows it: one image, or a swipeable carousel. */
function Media({ files, square = false }: { files: CreativeFile[]; square?: boolean }) {
  const [index, setIndex] = useState(0);
  if (!files.length) return null;
  const renderFile = (f: CreativeFile) =>
    f.file_type.startsWith("image/") ? (
      // Signed, short-lived URLs: next/image can't optimize them.
      // eslint-disable-next-line @next/next/no-img-element
      <img src={f.url} alt={f.file_name} className={cn("w-full bg-muted object-cover", square ? "aspect-square" : "max-h-[34rem] object-contain")} />
    ) : f.file_type.startsWith("video/") ? (
      <video src={f.url} controls className="max-h-[34rem] w-full bg-black" aria-label={f.file_name} />
    ) : (
      <a href={f.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 bg-muted p-6 text-sm">
        <FileTextIcon className="size-5" />
        {f.file_name}
      </a>
    );
  if (files.length === 1) return <div className="overflow-hidden bg-muted">{renderFile(files[0])}</div>;
  return (
    <div className="relative">
      <div
        className="flex snap-x snap-mandatory overflow-x-auto [scrollbar-width:none]"
        aria-label="Carousel"
        onScroll={(e) => {
          const el = e.currentTarget;
          setIndex(Math.round(el.scrollLeft / el.clientWidth));
        }}
      >
        {files.map((f) => (
          <div key={f.id} className="w-full shrink-0 snap-center">
            {renderFile(f)}
          </div>
        ))}
      </div>
      <span className="absolute top-2 right-2 rounded-full bg-black/60 px-2 py-0.5 text-xs text-white">
        {index + 1}/{files.length}
      </span>
      <div className="flex justify-center gap-1 py-2" aria-hidden>
        {files.map((f, i) => (
          <span key={f.id} className={cn("size-1.5 rounded-full", i === index ? "bg-primary" : "bg-muted-foreground/30")} />
        ))}
      </div>
    </div>
  );
}

function Action({ icon: Icon, label }: { icon: typeof HeartIcon; label?: string }) {
  return (
    <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
      <Icon className="size-4" />
      {label}
    </span>
  );
}

/**
 * The post as it will look in the feed, copy and creative in one frame, so
 * reviewers judge what the audience will actually see.
 */
export function SocialPostPreview({ platform, text, files }: { platform: Social; text: string; files: CreativeFile[] }) {
  const org = useOrganization();
  const name = org.data?.name ?? "Your organization";
  const logo = org.data?.logo_url ?? null;
  const handle = `@${name.toLowerCase().replace(/[^a-z0-9]+/g, "")}`;
  const frame = "mx-auto w-full max-w-[34rem] overflow-hidden rounded-xl border bg-card text-card-foreground shadow-sm";

  if (platform === "x") {
    return (
      <article className={cn(frame, "flex gap-3 p-4")} aria-label="X post preview">
        <Avatar name={name} logo={logo} />
        <div className="grid min-w-0 flex-1 gap-2">
          <p className="truncate text-sm">
            <span className="font-bold">{name}</span> <span className="text-muted-foreground">{handle} · now</span>
          </p>
          <Caption text={text} platform="x" />
          {files.length > 0 && (
            <div className="overflow-hidden rounded-2xl border">
              <Media files={files} />
            </div>
          )}
          <div className="flex justify-between pt-1 pr-6">
            <Action icon={MessageCircleIcon} />
            <Action icon={Repeat2Icon} />
            <Action icon={HeartIcon} />
            <Action icon={ChartNoAxesColumnIcon} />
            <Action icon={BookmarkIcon} />
          </div>
        </div>
      </article>
    );
  }

  if (platform === "instagram") {
    return (
      <article className={cn(frame, "max-w-[29rem]")} aria-label="Instagram post preview">
        <header className="flex items-center gap-2.5 px-3 py-2.5">
          <Avatar name={name} logo={logo} size="size-8" />
          <span className="text-sm font-semibold">{handle.slice(1)}</span>
        </header>
        <Media files={files} square />
        <div className="grid gap-2 px-3 py-2.5">
          <div className="flex items-center gap-4">
            <HeartIcon className="size-5" />
            <MessageCircleIcon className="size-5" />
            <SendIcon className="size-5" />
            <BookmarkIcon className="ml-auto size-5" />
          </div>
          <Caption text={text} platform="instagram" lead={<span className="mr-1.5 font-semibold">{handle.slice(1)}</span>} />
        </div>
      </article>
    );
  }

  // LinkedIn and Facebook: header, text, then the creative edge to edge.
  const linkedin = platform === "linkedin";
  return (
    <article className={frame} aria-label={`${linkedin ? "LinkedIn" : "Facebook"} post preview`}>
      <header className="flex items-start gap-2.5 px-4 pt-3">
        <Avatar name={name} logo={logo} round={!linkedin} size="size-11" />
        <div className="grid min-w-0 leading-tight">
          <span className="truncate text-sm font-semibold">{name}</span>
          {linkedin && <span className="truncate text-xs text-muted-foreground">Followers</span>}
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            now · <GlobeIcon className="size-3" />
          </span>
        </div>
      </header>
      <div className="px-4 py-3">
        <Caption text={text} platform={platform} />
      </div>
      <Media files={files} />
      <footer className="mx-4 flex justify-around border-t py-2">
        <Action icon={ThumbsUpIcon} label="Like" />
        <Action icon={MessageCircleIcon} label="Comment" />
        {linkedin ? <Action icon={Repeat2Icon} label="Repost" /> : <Action icon={Share2Icon} label="Share" />}
        {linkedin && <Action icon={SendIcon} label="Send" />}
      </footer>
    </article>
  );
}
