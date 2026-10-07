import {
  CheckIcon,
  FileTextIcon,
  GlobeIcon,
  ImageIcon,
  SparklesIcon,
  UploadIcon,
} from "lucide-react";

import { EXAMPLE_CLIENT } from "@/components/landing/wire-data";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { cn } from "@/lib/utils";

/**
 * The product, screen by screen. Each step pairs a plain explanation with a
 * small, faithful rendering of the real screen, filled with example data.
 */

type Step = {
  id: string;
  title: string;
  who: string;
  body: string;
  points: string[];
  screen: React.ReactNode;
};

const STEPS: Step[] = [
  {
    id: "setup",
    title: "Set up each client once",
    who: "Admin · about 10 minutes",
    body: "Each client gets its own workspace. Describe what they do, list their services, and add their website: ContentPulse reads it into a knowledge base that every post is written from.",
    points: [
      "Services and audience",
      "Brand voice and words to avoid",
      "Markets and platforms",
    ],
    screen: <SetupScreen />,
  },
  {
    id: "trends",
    title: "Trends arrive, scored for fit",
    who: "Automatic · hourly to daily",
    body: "ContentPulse collects what's trending in the client's markets and scores every trend from 0 to 100 against their services and material. Popular but irrelevant trends never reach your team.",
    points: [
      "Google Trends, Google News, Hacker News, Reddit, RSS",
      "A reason for every score",
      "Only Relevant or better gets post ideas",
    ],
    screen: <TrendsScreen />,
  },
  {
    id: "plan",
    title: "Pick a topic and plan the post",
    who: "Creator",
    body: "Shortlist the trends worth running, then choose the platform. The plan suggests an angle, a format and a goal, based on the platform's playbook.",
    points: [
      "LinkedIn, X, Instagram, Facebook, blog",
      "One click from plan to draft",
    ],
    screen: <PlanScreen />,
  },
  {
    id: "write",
    title: "The post is written from the client's material",
    who: "Creator · AI or templates",
    body: "The draft uses only what the client's own documents support, in their voice, sized for the platform. Edit it, ask for another version, or restore an earlier one.",
    points: [
      "Grounded in the knowledge base",
      "Versions you can compare and restore",
    ],
    screen: <WriteScreen />,
  },
  {
    id: "design",
    title: "Add the design",
    who: "Creator",
    body: "Upload the image or video your designer made, or generate one with AI from the design brief and the post.",
    points: ["Upload any size", "Or generate an image from the brief"],
    screen: <DesignScreen />,
  },
  {
    id: "approve",
    title: "Approve it, then publish",
    who: "Admin",
    body: "The admin sees the post exactly as it will look in the feed, and approves it or sends it back with a note. Approved posts are ready to share or copy to the platform.",
    points: [
      "Nothing goes out without approval",
      "Comments stay with each version",
    ],
    screen: <ApproveScreen />,
  },
];

export function ProductTour() {
  return (
    <ol className="mt-10 grid gap-16 lg:gap-24">
      {STEPS.map((step, i) => (
        <li
          key={step.id}
          className="grid items-center gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-14"
        >
          <div className={cn("min-w-0", i % 2 === 1 && "lg:order-2")}>
            <h3 className="headline text-3xl uppercase sm:text-4xl">
              {step.title}
            </h3>
            <p className="slug mt-2 flex flex-wrap gap-x-3 text-muted-foreground">
              <span className="font-semibold text-foreground tabular-nums">
                Step {i + 1} of {STEPS.length}
              </span>
              <span>{step.who}</span>
            </p>
            <p className="mt-3 max-w-[56ch] text-base leading-relaxed text-muted-foreground">
              {step.body}
            </p>
            <ul className="mt-4 grid gap-1.5">
              {step.points.map((p) => (
                <li key={p} className="flex items-start gap-2 text-sm">
                  <CheckIcon
                    className="mt-0.5 size-4 shrink-0 text-flash"
                    aria-hidden
                  />
                  {p}
                </li>
              ))}
            </ul>
          </div>
          <figure className={cn("min-w-0", i % 2 === 1 && "lg:order-1")}>
            <Screen>{step.screen}</Screen>
            <figcaption className="slug mt-2 text-muted-foreground">
              Example screen · invented client
            </figcaption>
          </figure>
        </li>
      ))}
    </ol>
  );
}

/** A window onto the app: same tokens, same components, example data. */
function Screen({ children }: { children: React.ReactNode }) {
  return (
    <div
      aria-hidden
      className="pointer-events-none overflow-hidden rounded-sm border border-border bg-background shadow-[0_1px_0_var(--paper-4),0_18px_40px_-24px_oklch(0.2_0_0/0.5)] select-none"
    >
      <div className="flex h-8 items-center gap-2 border-b border-border bg-sidebar px-3">
        <span className="headline text-sm uppercase">
          Content<span className="font-semibold">Pulse</span>
        </span>
        <span className="slug ml-auto truncate text-muted-foreground">
          {EXAMPLE_CLIENT.name}
        </span>
      </div>
      <div className="p-4 sm:p-5">{children}</div>
    </div>
  );
}

function ScreenTitle({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-4 border-b-[3px] border-double border-foreground pb-2">
      <p className="headline text-2xl">{title}</p>
      {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-1">
      <span className="text-xs font-medium">{label}</span>
      <div className="rounded-sm border border-input bg-card px-2.5 py-1.5 text-xs leading-relaxed">
        {children}
      </div>
    </div>
  );
}

function SetupScreen() {
  return (
    <>
      <ScreenTitle
        title="Profile"
        sub="Used to decide which trends matter and to write in your voice."
      />
      <div className="grid gap-3">
        <Field label="What you do">
          {EXAMPLE_CLIENT.name} helps small and mid-size firms stay compliant
          and recover fast from security incidents.
        </Field>
        <div className="grid gap-1">
          <span className="text-xs font-medium">Services</span>
          <div className="flex flex-wrap gap-1.5">
            {EXAMPLE_CLIENT.services.map((s) => (
              <Tag key={s} tone="neutral">
                {s}
              </Tag>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2 rounded-sm border border-border bg-card px-2.5 py-2 text-xs">
          <GlobeIcon className="size-3.5 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate">harborandpine.example</span>
          <Tag tone="green" dot>
            42 pages read
          </Tag>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <PlatformTag platform="linkedin" />
          <PlatformTag platform="x" />
          <PlatformTag platform="blog" />
        </div>
      </div>
    </>
  );
}

const TRENDS = [
  {
    score: 91,
    title: "EU draft guidance on AI incident reporting",
    source: "Google News",
    level: ["green", "Highly relevant"],
  },
  {
    score: 84,
    title: "Insurers tighten cyber cover for 2027",
    source: "RSS",
    level: ["green", "Highly relevant"],
  },
  {
    score: 72,
    title: "Parcel phishing texts surge",
    source: "Google Trends",
    level: ["teal", "Relevant"],
  },
  {
    score: 4,
    title: "Pumpkin spice searches peak early",
    source: "Google Trends",
    level: ["neutral", "Not relevant"],
  },
] as const;

function TrendsScreen() {
  return (
    <>
      <ScreenTitle
        title="Trends"
        sub="Today · scored against your services and knowledge base"
      />
      <ul className="divide-y divide-border border-y border-border">
        {TRENDS.map((t) => (
          <li
            key={t.title}
            className={cn(
              "flex items-center gap-3 py-2.5",
              t.score < 45 && "text-muted-foreground",
            )}
          >
            <span
              className={cn(
                "slug grid size-9 shrink-0 place-items-center rounded-sm text-xs font-semibold tabular-nums",
                t.score >= 45
                  ? "bg-foreground text-background"
                  : "ring-1 ring-border ring-inset",
              )}
            >
              {t.score}
            </span>
            <span className="grid min-w-0 flex-1">
              <span
                className={cn(
                  "truncate text-xs font-medium",
                  t.score < 45 && "line-through",
                )}
              >
                {t.title}
              </span>
              <span className="slug text-[10px] text-muted-foreground">
                {t.source}
              </span>
            </span>
            <Tag tone={t.level[0]} className="hidden sm:inline-flex">
              {t.level[1]}
            </Tag>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Why 91:</span> matches
        Compliance advisory and Incident response; your site covers incident
        reporting.
      </p>
    </>
  );
}

function PlanScreen() {
  return (
    <>
      <ScreenTitle title="EU AI incident reporting" sub="Topic · shortlisted" />
      <div className="grid gap-3 rounded-sm border border-border bg-card p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold">New plan</span>
          <Tag tone="green" dot>
            Shortlisted
          </Tag>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Platform">
            <PlatformTag platform="linkedin" />
          </Field>
          <Field label="Format">Text post with a checklist</Field>
        </div>
        <Field label="Angle">
          Three questions small firms should answer this week.
        </Field>
        <Field label="Goal">Book compliance reviews</Field>
        <div className="flex justify-end gap-2">
          <span className="inline-flex h-7 items-center rounded-sm border border-border px-2.5 text-xs font-medium">
            Save plan
          </span>
          <span className="inline-flex h-7 items-center rounded-sm bg-foreground px-2.5 text-xs font-medium text-background">
            Save &amp; write post
          </span>
        </div>
      </div>
    </>
  );
}

function WriteScreen() {
  return (
    <>
      <ScreenTitle title="Content studio" sub="LinkedIn · version 2 of 2" />
      <div className="grid gap-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <PlatformTag platform="linkedin" />
          <Tag tone="neutral">Draft</Tag>
          <span className="slug ml-auto text-[10px] text-muted-foreground tabular-nums">
            612 / 3,000
          </span>
        </div>
        <div className="rounded-sm border border-input bg-card p-3 text-xs leading-relaxed whitespace-pre-line">
          {
            "The EU's draft guidance on AI incident reporting landed this morning, and small firms are in scope.\n\nThree things to check this week:\n1. Do you know which of your tools use AI?\n2. Who decides whether an incident is reportable?\n3. Can you produce a timeline within 72 hours?"
          }
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <FileTextIcon className="size-3.5 text-muted-foreground" />
          <span className="text-muted-foreground">Backed by:</span>
          <span className="rounded-sm bg-muted px-1.5 py-0.5">
            Incident response service page
          </span>
          <span className="rounded-sm bg-muted px-1.5 py-0.5">
            Compliance checklist (PDF)
          </span>
        </div>
      </div>
    </>
  );
}

function DesignScreen() {
  return (
    <>
      <ScreenTitle title="Design" sub="LinkedIn image · 1200 × 1200" />
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="relative grid aspect-square place-items-center overflow-hidden rounded-sm bg-[oklch(0.22_0.03_255)] p-4 text-[oklch(0.96_0.01_95)]">
          <span className="headline text-center text-2xl leading-none uppercase">
            3 questions
            <br />
            before the
            <br />
            <span className="text-[oklch(0.75_0.17_29)]">EU deadline</span>
          </span>
          <span className="slug absolute bottom-2 left-2 text-[10px]">
            Harbor &amp; Pine
          </span>
        </div>
        <div className="grid content-start gap-2">
          <p className="text-xs leading-relaxed text-muted-foreground">
            <span className="font-medium text-foreground">Brief:</span> bold
            headline, navy ground, one red accent. Square for the feed.
          </p>
          <span className="inline-flex h-8 items-center justify-center gap-1.5 rounded-sm border border-border text-xs font-medium">
            <UploadIcon className="size-3.5" /> Upload a design
          </span>
          <span className="inline-flex h-8 items-center justify-center gap-1.5 rounded-sm border border-border text-xs font-medium">
            <SparklesIcon className="size-3.5" /> Generate image with AI
          </span>
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <ImageIcon className="size-3.5" /> Version 1 · uploaded
          </span>
        </div>
      </div>
    </>
  );
}

function ApproveScreen() {
  return (
    <>
      <ScreenTitle
        title="Approvals"
        sub="Copy v2 · design v1 · sent by a creator"
      />
      <div className="grid gap-3 sm:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="rounded-sm border border-border bg-card p-3">
          <div className="flex items-center gap-2">
            <span className="grid size-7 place-items-center rounded-sm bg-foreground text-[10px] font-semibold text-background">
              {EXAMPLE_CLIENT.initials}
            </span>
            <span className="text-xs font-semibold">{EXAMPLE_CLIENT.name}</span>
          </div>
          <p className="mt-2 line-clamp-3 text-xs leading-relaxed">
            The EU&apos;s draft guidance on AI incident reporting landed this
            morning, and small firms are in scope. Three things to check this
            week…
          </p>
          <div className="mt-2 grid aspect-[2/1] place-items-center rounded-sm bg-[oklch(0.22_0.03_255)] text-[oklch(0.96_0.01_95)]">
            <span className="headline text-lg uppercase">3 questions</span>
          </div>
        </div>
        <div className="grid content-start gap-2">
          <Tag tone="violet" dot className="justify-self-start">
            Waiting for approval
          </Tag>
          <span className="inline-flex h-8 items-center justify-center gap-1.5 rounded-sm bg-foreground text-xs font-medium text-background">
            <CheckIcon className="size-3.5" /> Approve
          </span>
          <span className="inline-flex h-8 items-center justify-center rounded-sm border border-border text-xs font-medium">
            Request changes
          </span>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            Approved posts move to{" "}
            <span className="font-medium text-foreground">
              Ready to publish
            </span>
            .
          </p>
        </div>
      </div>
    </>
  );
}
