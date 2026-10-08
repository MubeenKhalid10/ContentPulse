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
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import {
  EXAMPLE_CLIENT,
  FITTING,
  relevanceOf,
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
 * Relevance flag, in the app's own words. Trends that fit (Relevant or
 * better) are set in red; the rest stay quiet. Unread items say "Scoring".
 */
export function RelevanceFlag({
  item,
  read = true,
  inverted = false,
}: {
  item: WireItem;
  read?: boolean;
  inverted?: boolean;
}) {
  const label = read ? relevanceOf(item) : "Scoring";
  const loud = read && fits(item);
  return (
    <span
      className={cn(
        "text-xs inline-flex h-5 shrink-0 items-center rounded-[2px] px-1.5 font-semibold whitespace-nowrap",
        !loud && "ring-1 ring-inset",
        !loud &&
          (inverted
            ? "text-background/80 ring-background/40"
            : "text-muted-foreground ring-border"),
        loud && "flag-stamp bg-flash text-flash-foreground",
        read && item.fit >= 75 && "outline-2 outline-offset-1 outline-flash",
      )}
    >
      {label}
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
    <div className="grid min-w-0 gap-12">
      {intro}
      <div className="grid min-w-0 items-start gap-10 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:gap-12">
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

  // One list, rotated so the item at the read line is on top. Each step,
  // the rows slide up by the height of the row that just left the top
  // (it moves to the bottom), so no item ever shows twice.
  const order = reduced
    ? WIRE.map((_, i) => i)
    : WIRE.map((_, k) => (atLine + k) % N);

  useLayoutEffect(() => {
    const feed = feedRef.current;
    if (!feed || reduced || tick === 0) return;
    const left = WIRE[(atLine - 1 + N) % N]!;
    const row = feed.querySelector<HTMLElement>(`[data-wire-row="${left.id}"]`);
    if (!row) return;
    feed.style.transition = "none";
    feed.style.transform = `translateY(${row.offsetHeight}px)`;
    void feed.offsetHeight; // commit the start position before animating
    feed.style.transition = STEP_EASE;
    feed.style.transform = "translateY(0)";
  }, [tick, atLine, reduced]);

  return (
    <section
      aria-labelledby="wire-title"
      className="min-w-0"
      onPointerEnter={() => onHold(true)}
      onPointerLeave={() => onHold(false)}
      onFocus={() => onHold(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) onHold(false);
      }}
    >
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-border pb-3">
        <h2 id="wire-title" className="text-xs font-semibold text-foreground">
          Incoming trends · example
        </h2>
        {/* Own line, so the header keeps one height with or without Pause. */}
        <span className="text-xs order-last basis-full text-muted-foreground">
          <span className="text-flash">Red</span>: Relevant or better ·{" "}
          <span className="line-through">struck</span>: filtered out
        </span>
        {!reduced && (
          <button
            type="button"
            onClick={onToggle}
            aria-pressed={stopped}
            className="text-xs -my-2 inline-flex h-11 items-center gap-1.5 rounded-lg px-2 font-semibold outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/60"
          >
            {stopped ? (
              <PlayIcon className="size-3.5" aria-hidden />
            ) : (
              <PauseIcon className="size-3.5" aria-hidden />
            )}
            {stopped ? "Resume" : "Pause"}
          </button>
        )}
      </div>
      <div className="relative h-[26rem] overflow-hidden rounded-xl border border-border bg-card lg:h-[38rem]">
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
          <WireList
            order={order}
            selectedId={selectedId}
            isRead={isRead}
            onPick={onPick}
          />
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
          ? "Each trend carries the relevance label the app gives it."
          : "Each trend gets its score as it crosses the red line."}{" "}
        Trends rated Relevant or better get post ideas. Pick any item to see
        what happens to it.
      </p>
    </section>
  );
}

function WireList({
  order,
  selectedId,
  isRead,
  onPick,
}: {
  order: number[];
  selectedId: string;
  isRead: (i: number) => boolean;
  onPick: (id: string) => void;
}) {
  return (
    <ul className="divide-y divide-border">
      {order.map((i) => {
        const item = WIRE[i]!;
        const active = item.id === selectedId;
        const read = isRead(i);
        return (
          <li key={item.id} data-wire-row={item.id}>
            <button
              type="button"
              aria-pressed={active}
              onClick={() => onPick(item.id)}
              className={cn(
                "grid w-full gap-1.5 px-4 py-3 text-left outline-none transition-colors focus-visible:bg-muted",
                active ? "bg-foreground text-background" : "hover:bg-muted",
                read && !fits(item) && !active && "text-muted-foreground",
              )}
            >
              <span className="flex min-w-0 items-start gap-2">
                <RelevanceFlag
                  key={read ? "read" : "new"}
                  item={item}
                  read={read}
                  inverted={active}
                />
                <span
                  className={cn(
                    "text-xs min-w-0 flex-1",
                    active ? "text-background/80" : "text-muted-foreground",
                  )}
                >
                  {item.source} · {item.time}
                </span>
                <span className="text-xs shrink-0 font-semibold whitespace-nowrap tabular-nums">
                  {/* No number until the item is scored. */}
                  Score {read ? item.fit : "—"}
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
      <div className="flex items-baseline justify-between gap-3 border-b border-border pb-3">
        <h2 id="desk-title" className="text-xs font-semibold text-foreground">
          The post it becomes
        </h2>
        <p className="text-xs text-muted-foreground">
          LinkedIn · {EXAMPLE_CLIENT.name}
        </p>
      </div>

      <div key={item.id} className="desk-set mt-4">
        {fits(item) && item.post ? (
          <>
            <p className="text-sm text-muted-foreground">
              Written for the highlighted trend from the client&apos;s own
              service notes. Matches: {item.matched?.join(", ")}.
            </p>
            <PostProof item={item} />
          </>
        ) : (
          <div className="flex items-center gap-4 border-y border-dashed border-foreground/40 py-4">
            <SpikeMark className="h-12 w-10 shrink-0 text-foreground" />
            <div className="grid gap-1">
              <p className="headline text-xl">Filtered out</p>
              <p className="text-sm text-muted-foreground">
                Score {item.fit}: {relevanceOf(item)}. Only trends rated
                Relevant or better get post ideas: popular isn&apos;t the same
                as relevant.
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
      className="mt-4 rounded-xl bg-card text-card-foreground ring-1 ring-foreground/10"
    >
      <header className="flex items-center gap-3 px-4 pt-4">
        <span
          aria-hidden
          className="grid size-10 place-items-center rounded-lg bg-foreground text-sm font-semibold text-background"
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
        <span className="ok-stamp ml-auto grid shrink-0 place-items-center rounded-lg border-2 border-flash px-2 py-1 text-center text-flash">
          <span className="headline text-lg leading-none">Approved</span>
          <span className="text-xs text-[11px] leading-tight">
            Ready to publish
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
