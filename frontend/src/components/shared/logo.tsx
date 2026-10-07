import { cn } from "@/lib/utils";

/** Wordmark: the name set as a headline, with the red "live" mark of a running wire. */
export function Logo({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "headline inline-flex items-baseline text-[1.35em] leading-none font-black tracking-normal uppercase",
        className,
      )}
    >
      Content<span className="font-semibold">Pulse</span>
      <span aria-hidden className="ml-1 size-[0.32em] translate-y-[-0.05em] rounded-full bg-flash" />
    </span>
  );
}
