import { PLATFORM_LABEL } from "@/lib/topics";
import { PLATFORM_TONE, TONE_CLASS, TONE_DOT, type Tone } from "@/lib/tones";
import { cn } from "@/lib/utils";
import type { Platform } from "@/types/api";

/** A colored label. Pick the tone from lib/tones so colors keep one meaning. */
export function Tag({
  tone,
  dot = false,
  className,
  children,
  ...props
}: { tone: Tone; dot?: boolean } & React.ComponentProps<"span">) {
  return (
    <span
      className={cn(
        "inline-flex h-5 shrink-0 items-center gap-1.5 rounded-full px-2 text-[11px] font-medium whitespace-nowrap ring-1 ring-inset",
        TONE_CLASS[tone],
        className,
      )}
      {...props}
    >
      {dot && <span aria-hidden className={cn("size-1.5 rounded-full", TONE_DOT[tone])} />}
      {children}
    </span>
  );
}

export function PlatformTag({ platform, className }: { platform: Platform; className?: string }) {
  return (
    <Tag tone={PLATFORM_TONE[platform]} className={className}>
      {PLATFORM_LABEL[platform]}
    </Tag>
  );
}
