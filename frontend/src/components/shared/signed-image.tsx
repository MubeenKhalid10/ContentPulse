"use client";

import { ImageOffIcon } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/utils";

/**
 * An image from a signed storage link. When the file can't be loaded (removed
 * from storage, link expired) it says so instead of showing a broken icon.
 */
export function SignedImage({
  src,
  alt,
  className,
}: {
  src: string;
  alt: string;
  className?: string;
}) {
  // Keyed by `src`, so a new link gets a fresh try.
  return <Inner key={src} src={src} alt={alt} className={className} />;
}

function Inner({ src, alt, className }: { src: string; alt: string; className?: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <span
        role="img"
        aria-label={`${alt}: preview unavailable`}
        className={cn(
          "grid place-items-center gap-1 bg-muted/60 p-3 text-center text-xs text-muted-foreground",
          className,
        )}
      >
        <ImageOffIcon className="size-5" aria-hidden />
        Preview unavailable
      </span>
    );
  }
  return (
    // Signed, short-lived URLs from S3 or the API: next/image can't optimize them.
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} className={className} loading="lazy" onError={() => setFailed(true)} />
  );
}
