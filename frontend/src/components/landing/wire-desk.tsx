"use client";

import {
  GlobeIcon,
  MessageCircleIcon,
  PauseIcon,
  PlayIcon,
  Repeat2Icon,
  SendIcon,
  ThumbsUpIcon,
} from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import {
  EXAMPLE_CLIENT,
  FITTING,
  priorityOf,
  WIRE,
  type WireItem,
} from "@/components/landing/wire-data";
import { cn } from "@/lib/utils";

/** Teleprinter pace: one item reaches the read line every STEP_MS. */
const STEP_MS = 1800;
const STEP_EASE = "transform 260ms cubic-bezier(0.16, 1, 0.3, 1)";
const N = WIRE.length;

function subscribeReducedMotion(cb: () => void) {
  const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
}

function useReducedMotion() {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => true,
  );
}

const fits = (item: WireItem) => item.fit >= EXAMPLE_CLIENT.threshold;

/**
 * Priority flag, always a word; colour only reinforces it. Items the desk
 * hasn't read yet carry "NEW"; reading one stamps its priority on.
 */
export function PriorityFlag({
  item,
  read = true,
  inverted = false,
}: {
  item: WireItem;
  read?: boolean;
  inverted?: boolean;
}) {
  const p = read ? priorityOf(item) : "NEW";
  const quiet = p === "ROUTINE" || p === "NEW";
  return (
    <span
      className={cn(
        "slug inline-flex h-5 shrink-0 items-center rounded-[2px] px-1.5 font-semibold",
        quiet && "ring-1 ring-inset",
        quiet &&
          (inverted
            ? "text-background/80 ring-background/40"
            : "text-muted-foreground ring-border"),
        !quiet && "flag-stamp bg-flash text-flash-foreground",
        p === "FLASH" && "outline-2 outline-offset-1 outline-flash",
      )}
    >
      {p}
    </span>
  );
}

/**
 * The signature moment: the wire steps up the tape; as each item crosses the
 * read line the desk reads it, stamps its priority, and sets the latest item
 * that fits the example client as a finished post.
 */
export function WireDesk({ intro }: { intro?: React.ReactNode }) {
  const reduced = useReducedMotion();
  const [tick, setTick] = useState(0);
  const [stopped, setStopped] = useState(false);
  const [held, setHeld] = useState(false);
  const [pickedId, setPickedId] = useState<string | null>(null);

  const running = !reduced && !stopped && !held && pickedId === null;

  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(() => setTick((n) => n + 1), STEP_MS);
    return () => window.clearInterval(t);
  }, [running]);

  const atLine = tick % N;
  // Under reduced motion nothing moves, so every item counts as read.
  const isRead = (i: number) => reduced || tick >= N || i <= atLine;

  // The desk shows the visitor's pick, else the latest fitting item read.
  let selected: WireItem = FITTING[0]!;
  if (pickedId) {
    selected = WIRE.find((w) => w.id === pickedId)!;
  } else if (!reduced) {
    for (let k = 0; k < N; k++) {
      const i = (atLine - k + N) % N;
      if (isRead(i) && fits(WIRE[i]!)) {
        selected = WIRE[i]!;
        break;
      }
    }
  }

  return (
    <div className="grid min-w-0 gap-10 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:gap-12">
      <WireTape
        tick={tick}
        selectedId={selected.id}
        isRead={isRead}
        reduced={reduced}
        stopped={stopped || pickedId !== null}
        onToggle={() => {
          if (pickedId !== null) {
            setPickedId(null);
            setStopped(false);
          } else {
            setStopped((s) => !s);
          }
        }}
        onHold={setHeld}
        onPick={setPickedId}
      />
      <div className="order-1 grid min-w-0 content-start gap-12 lg:order-2">
        {intro}
        <Desk item={selected} announce={pickedId !== null} />
      </div>
    </div>
  );
}

function WireTape({
  tick,
  selectedId,
  isRead,
  reduced,
  stopped,
  onToggle,
  onHold,
  onPick,
}: {
  tick: number;
  selectedId: string;
  isRead: (i: number) => boolean;
  reduced: boolean;
  stopped: boolean;
  onToggle: () => void;
  onHold: (held: boolean) => void;
  onPick: (id: string) => void;
}) {
  const feedRef = useRef<HTMLDivElement>(null);
  const atLine = tick % N;

  // Step the feed so the row at the read line sits at the top of the tape.
  // The list is doubled: wrapping steps onto the copy's first row, then snaps
  // back to the original without a transition.
  useEffect(() => {
    const feed = feedRef.current;
    if (!feed || reduced) return;
    const rows = feed.querySelectorAll<HTMLElement>("[data-wire-row]");
    const wrapping = tick > 0 && atLine === 0;
    const target = rows[wrapping ? N : atLine];
    if (!target) return;
    feed.style.transition = STEP_EASE;
    feed.style.transform = `translateY(${-target.offsetTop}px)`;
    if (!wrapping) return;
    const snap = window.setTimeout(() => {
      feed.style.transition = "none";
      feed.style.transform = "translateY(0)";
    }, 300);
    return () => window.clearTimeout(snap);
  }, [tick, atLine, reduced]);

  return (
    <section
      aria-labelledby="wire-title"
      className="order-2 min-w-0 lg:sticky lg:top-6 lg:order-1 lg:self-start"
      onPointerEnter={() => onHold(true)}
      onPointerLeave={() => onHold(false)}
      onFocus={() => onHold(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) onHold(false);
      }}
    >
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-foreground pb-2">
        <h2 id="wire-title" className="slug font-semibold text-foreground">
          The wire · example
        </h2>
        <span className="slug text-muted-foreground">
          Client bar: fit {EXAMPLE_CLIENT.threshold}+
        </span>
        {!reduced && (
          <button
            type="button"
            onClick={onToggle}
            aria-pressed={stopped}
            className="slug -my-2 inline-flex h-11 items-center gap-1.5 rounded-sm px-2 font-semibold outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/60"
          >
            {stopped ? (
              <PlayIcon className="size-3.5" aria-hidden />
            ) : (
              <PauseIcon className="size-3.5" aria-hidden />
            )}
            {stopped ? "Run the wire" : "Stop the wire"}
          </button>
        )}
      </div>
      <div className="relative h-[26rem] overflow-hidden border-x border-b border-border bg-card lg:h-[calc(100svh-7.5rem)] lg:max-h-[56rem] lg:min-h-[36rem]">
        <span
          aria-hidden
          className="wire-perf absolute inset-y-0 left-0 z-10 w-4 border-r border-dashed border-border"
        />
        {!reduced && (
          <span
            aria-hidden
            className="absolute inset-x-0 top-0 z-10 border-t-2 border-flash"
          />
        )}
        <div
          ref={feedRef}
          className={cn("pl-4", reduced && "h-full overflow-y-auto")}
        >
          <WireList selectedId={selectedId} isRead={isRead} onPick={onPick} />
          {!reduced && (
            <WireList
              selectedId={selectedId}
              isRead={isRead}
              onPick={onPick}
              copy
            />
          )}
        </div>
        <span
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-linear-to-t from-card to-transparent"
        />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Example headlines for an invented client, {EXAMPLE_CLIENT.name},{" "}
        {EXAMPLE_CLIENT.what}.{" "}
        {reduced
          ? `Each item is flagged against the client's bar of ${EXAMPLE_CLIENT.threshold}.`
          : "Items are read as they cross the red line."}{" "}
        Pick any item to see what the desk does with it.
      </p>
    </section>
  );
}

function WireList({
  selectedId,
  isRead,
  onPick,
  copy = false,
}: {
  selectedId: string;
  isRead: (i: number) => boolean;
  onPick: (id: string) => void;
  copy?: boolean;
}) {
  return (
    <ul aria-hidden={copy || undefined} className="divide-y divide-border">
      {WIRE.map((item, i) => {
        const active = item.id === selectedId;
        const read = isRead(i);
        return (
          <li key={item.id} data-wire-row>
            <button
              type="button"
              tabIndex={copy ? -1 : undefined}
              aria-pressed={copy ? undefined : active}
              onClick={() => onPick(item.id)}
              className={cn(
                "grid w-full gap-1.5 px-4 py-3 text-left outline-none transition-colors focus-visible:bg-muted",
                active ? "bg-foreground text-background" : "hover:bg-muted",
                read && !fits(item) && !active && "text-muted-foreground",
              )}
            >
              <span className="flex min-w-0 items-start gap-2">
                <PriorityFlag
                  key={read ? "read" : "new"}
                  item={item}
                  read={read}
                  inverted={active}
                />
                <span
                  className={cn(
                    "slug min-w-0 flex-1",
                    active ? "text-background/80" : "text-muted-foreground",
                  )}
                >
                  {item.source} · {item.time}
                </span>
                <span className="slug shrink-0 font-semibold whitespace-nowrap tabular-nums">
                  Fit {item.fit}
                </span>
              </span>
              <span
                className={cn(
                  "text-sm leading-snug",
                  !read || fits(item)
                    ? "font-medium"
                    : "line-through decoration-1",
                )}
              >
                {item.headline}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/** A copy spike: the desk's spindle for stories that don't run. */
function SpikeMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 40"
      aria-hidden
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path d="M16 3v29" strokeLinecap="round" />
      <path d="M6 36h20" strokeLinecap="round" strokeWidth={3} />
      <path
        d="M5 18.5 27 13l-1.5 8L4 26.5z"
        strokeLinejoin="round"
        fill="var(--card)"
      />
      <path d="M16 13.5v12" strokeLinecap="round" />
    </svg>
  );
}

function Desk({ item, announce }: { item: WireItem; announce: boolean }) {
  return (
    <section
      aria-labelledby="desk-title"
      // Announce only what the visitor picked, never the automatic feed.
      aria-live={announce ? "polite" : "off"}
      className="min-w-0"
    >
      <div className="flex items-baseline justify-between gap-3 border-b border-foreground pb-2">
        <h2 id="desk-title" className="slug font-semibold text-foreground">
          The desk
        </h2>
        <p className="slug text-muted-foreground">
          LinkedIn · {EXAMPLE_CLIENT.name}
        </p>
      </div>

      <div key={item.id} className="desk-set mt-4">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <PriorityFlag item={item} />
          <span className="slug tabular-nums">Fit {item.fit} / 100</span>
          <span className="slug text-muted-foreground">{item.source}</span>
        </div>
        <p className="headline mt-2 text-2xl sm:text-3xl">{item.headline}</p>

        {fits(item) && item.post ? (
          <>
            <p className="mt-2 text-sm text-muted-foreground">
              Matches: {item.matched?.join(", ")}. Written from the
              client&apos;s own service notes.
            </p>
            <PostProof item={item} />
          </>
        ) : (
          <div className="mt-4 flex items-center gap-4 border-y border-dashed border-foreground/40 py-4">
            <SpikeMark className="h-12 w-10 shrink-0 text-foreground" />
            <div className="grid gap-1">
              <p className="headline text-xl uppercase">Spiked</p>
              <p className="text-sm text-muted-foreground">
                Fit {item.fit} is under this client&apos;s bar of{" "}
                {EXAMPLE_CLIENT.threshold}. Popular isn&apos;t the same as
                relevant, so nothing gets written.
              </p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function PostProof({ item }: { item: WireItem }) {
  return (
    <article
      aria-label={`Example LinkedIn post for ${EXAMPLE_CLIENT.name}`}
      className="mt-4 rounded-sm border border-border bg-card text-card-foreground shadow-[0_1px_0_var(--paper-4),0_12px_28px_-18px_oklch(0.2_0_0/0.45)]"
    >
      <header className="flex items-center gap-3 px-4 pt-4">
        <span
          aria-hidden
          className="grid size-10 place-items-center rounded-sm bg-foreground text-sm font-semibold text-background"
        >
          {EXAMPLE_CLIENT.initials}
        </span>
        <span className="grid min-w-0 leading-tight">
          <span className="text-sm font-semibold">{EXAMPLE_CLIENT.name}</span>
          <span className="flex min-w-0 items-center gap-1 text-xs text-muted-foreground">
            <span className="truncate">Cybersecurity consultancy · now</span>
            <GlobeIcon className="size-3 shrink-0" aria-label="Public" />
          </span>
        </span>
        <span className="ok-stamp ml-auto grid shrink-0 -rotate-6 place-items-center rounded-sm border-2 border-flash px-2 py-1 text-center text-flash">
          <span className="headline text-lg leading-none uppercase">
            OK · Run
          </span>
          <span className="slug text-[9px] leading-tight">
            Approved to publish
          </span>
        </span>
      </header>
      <p className="px-4 pt-3 text-sm leading-relaxed whitespace-pre-line">
        {item.post}
      </p>
      <p className="px-4 pt-2 text-sm font-medium text-wire">{item.hashtags}</p>
      <footer className="mt-3 flex justify-around border-t border-border px-2 py-1.5 text-xs font-medium text-muted-foreground">
        {(
          [
            [ThumbsUpIcon, "Like"],
            [MessageCircleIcon, "Comment"],
            [Repeat2Icon, "Repost"],
            [SendIcon, "Send"],
          ] as const
        ).map(([Icon, label]) => (
          <span key={label} className="flex items-center gap-1.5 px-2 py-1.5">
            <Icon className="size-4" aria-hidden />
            {label}
          </span>
        ))}
      </footer>
    </article>
  );
}
