"use client";

import { ChevronLeftIcon, ChevronRightIcon, FileTextIcon, FilmIcon } from "lucide-react";
import { useRef, useState } from "react";

import { SignedImage } from "@/components/shared/signed-image";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { CreativeFile } from "@/types/api";

/**
 * Several files of one design, one at a time at full size. Swipe or scroll it, use the
 * arrows, or pick a thumbnail: every file stays one click away, however many there are.
 */
export function FileSlider({
  files,
  label,
  renderSlide,
}: {
  files: CreativeFile[];
  label: string;
  renderSlide: (file: CreativeFile, index: number) => React.ReactNode;
}) {
  const track = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);
  const shown = Math.min(index, files.length - 1);
  const go = (next: number) => {
    const el = track.current;
    if (el) el.scrollTo({ left: next * el.clientWidth });
  };
  return (
    <div className="grid min-w-0 grid-cols-1 gap-2">
      <div
        ref={track}
        className="flex min-w-0 snap-x snap-mandatory items-center overflow-x-auto [scrollbar-width:none] motion-safe:scroll-smooth focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        role="group"
        aria-roledescription="carousel"
        aria-label={`${label}, use the arrow keys to move between files`}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight" && shown < files.length - 1) go(shown + 1);
          else if (e.key === "ArrowLeft" && shown > 0) go(shown - 1);
          else return;
          e.preventDefault();
        }}
        onScroll={(e) => {
          const el = e.currentTarget;
          setIndex(Math.round(el.scrollLeft / el.clientWidth));
        }}
      >
        {files.map((f, i) => (
          <div key={f.id} className="w-full min-w-0 shrink-0 snap-center">
            {renderSlide(f, i)}
          </div>
        ))}
      </div>
      <div className="flex items-center justify-center gap-2">
        <Button size="icon-sm" variant="outline" aria-label="Previous file" disabled={shown === 0} onClick={() => go(shown - 1)}>
          <ChevronLeftIcon />
        </Button>
        <span className="min-w-14 text-center text-xs tabular-nums text-muted-foreground" aria-live="polite">
          {shown + 1} of {files.length}
        </span>
        <Button
          size="icon-sm"
          variant="outline"
          aria-label="Next file"
          disabled={shown === files.length - 1}
          onClick={() => go(shown + 1)}
        >
          <ChevronRightIcon />
        </Button>
      </div>
      <ul className="flex flex-wrap justify-center gap-1.5" aria-label="Files">
        {files.map((f, i) => (
          <li key={f.id}>
            <button
              type="button"
              aria-label={`Show file ${i + 1}: ${f.file_name}`}
              aria-current={i === shown}
              title={f.file_name}
              onClick={() => go(i)}
              className={cn(
                "block size-11 overflow-hidden rounded-md border bg-muted/50 outline-none focus-visible:ring-2 focus-visible:ring-ring",
                i === shown ? "ring-2 ring-primary" : "opacity-70 hover:opacity-100",
              )}
            >
              <FileThumb file={f} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function FileThumb({ file }: { file: CreativeFile }) {
  if (file.file_type.startsWith("image/")) {
    return <SignedImage src={file.url} alt="" className="size-full object-cover" />;
  }
  const Icon = file.file_type.startsWith("video/") ? FilmIcon : FileTextIcon;
  return (
    <span className="grid size-full place-items-center text-muted-foreground">
      <Icon className="size-4" aria-hidden />
    </span>
  );
}
