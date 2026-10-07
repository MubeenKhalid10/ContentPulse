import { ArrowRightIcon } from "lucide-react";
import Link from "next/link";

import { MastheadClock } from "@/components/landing/masthead-clock";
import {
  EXAMPLE_CLIENT,
  relevanceOf,
  WIRE,
} from "@/components/landing/wire-data";
import { ProductTour } from "@/components/landing/product-tour";
import { WireDesk } from "@/components/landing/wire-desk";
import { Logo } from "@/components/shared/logo";
import { cn } from "@/lib/utils";

const inkButton =
  "inline-flex h-11 items-center justify-center gap-2 rounded-sm bg-foreground px-5 text-sm font-semibold text-background outline-none transition-colors hover:bg-foreground/85 focus-visible:ring-3 focus-visible:ring-ring/60";
const lineButton =
  "inline-flex h-11 items-center justify-center gap-2 rounded-sm border border-foreground px-5 text-sm font-semibold outline-none transition-colors hover:bg-foreground hover:text-background focus-visible:ring-3 focus-visible:ring-ring/60";

const STAFF = [
  {
    role: "Admin",
    duty: "Sets up each client, invites the team, approves every post.",
  },
  {
    role: "Creator",
    duty: "Shortlists, writes, adds the design and sends it for approval.",
  },
  {
    role: "Viewer",
    duty: "Reads everything and shares finished posts. Good for a client contact.",
  },
];

export function LandingPage({ signedIn }: { signedIn: boolean }) {
  return (
    <div className="min-h-svh bg-background text-foreground">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-sm focus:bg-background focus:px-3 focus:py-2"
      >
        Skip to content
      </a>

      {/* The masthead is always set in the night-desk tokens: ink strip, light type. */}
      <header className="dark border-b border-border bg-background text-foreground">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 sm:px-6">
          <Link
            href="/"
            aria-label="ContentPulse home"
            className="rounded-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/60"
          >
            <Logo className="text-xl" />
          </Link>
          <nav
            aria-label="Page"
            className="ml-4 hidden items-center gap-1 md:flex"
          >
            {[
              ["#how-it-works", "How it works"],
              ["#faq", "FAQ"],
            ].map(([href, label]) => (
              <a
                key={href}
                href={href}
                className="inline-flex h-11 items-center rounded-sm px-3 text-sm font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/60"
              >
                {label}
              </a>
            ))}
          </nav>
          <nav aria-label="Account" className="ml-auto flex items-center gap-1">
            <span className="mr-2 hidden text-muted-foreground sm:inline">
              <MastheadClock />
            </span>
            {signedIn ? (
              <Link
                href="/dashboard"
                className="inline-flex h-11 items-center gap-2 rounded-sm px-3 text-sm font-semibold outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/60"
              >
                Go to dashboard{" "}
                <ArrowRightIcon className="size-4" aria-hidden />
              </Link>
            ) : (
              <>
                <Link
                  href="/login"
                  className="inline-flex h-11 items-center rounded-sm px-3 text-sm font-medium outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/60"
                >
                  Sign in
                </Link>
                <Link
                  href="/register"
                  className="inline-flex h-11 items-center rounded-sm bg-flash px-4 text-sm font-semibold text-flash-foreground outline-none hover:bg-flash/85 focus-visible:ring-3 focus-visible:ring-ring/60"
                >
                  Start free
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      <main id="main">
        {/* First viewport: headline, then the wire and the desk. */}
        <section className="mx-auto max-w-7xl px-4 pt-8 pb-16 sm:px-6 lg:pt-10">
          <WireDesk
            intro={
              <div>
                <h1 className="headline text-[clamp(2.75rem,6.4vw,5.25rem)] uppercase">
                  Turn the trends that <span className="text-flash">fit</span>{" "}
                  each client into approved posts.
                </h1>
                <p className="mt-5 max-w-[62ch] text-base leading-relaxed text-muted-foreground sm:text-lg">
                  ContentPulse is a social media workspace for marketing
                  agencies. It finds what&apos;s trending in each client&apos;s
                  market, keeps only what fits their business, writes the post
                  from their own material, and gets it approved by your team.
                </p>
                <div className="mt-6 flex flex-wrap gap-3">
                  {signedIn ? (
                    <Link href="/dashboard" className={inkButton}>
                      Go to dashboard{" "}
                      <ArrowRightIcon className="size-4" aria-hidden />
                    </Link>
                  ) : (
                    <>
                      <Link href="/register" className={inkButton}>
                        Start free{" "}
                        <ArrowRightIcon className="size-4" aria-hidden />
                      </Link>
                      <Link href="/login" className={lineButton}>
                        Sign in
                      </Link>
                    </>
                  )}
                </div>
              </div>
            }
          />
        </section>

        <section
          id="how-it-works"
          aria-labelledby="how-title"
          className="mx-auto max-w-7xl scroll-mt-6 px-4 py-16 sm:px-6"
        >
          <SectionHead id="how-title" title="How it works">
            <p>
              Six steps from a trend to a post that&apos;s ready to publish.
              Here is each screen with an invented client, {EXAMPLE_CLIENT.name}
              , {EXAMPLE_CLIENT.what}.
            </p>
          </SectionHead>
          <ProductTour />
        </section>

        <FitScale />
        <StaffBox />
        <WhatItRunsOn />
        <Faq />

        <section className="dark bg-background text-foreground">
          <div className="mx-auto flex max-w-7xl flex-wrap items-end justify-between gap-6 px-4 py-16 sm:px-6">
            <h2 className="headline max-w-3xl text-[clamp(2.5rem,6vw,4.5rem)] uppercase">
              Set up your first client in ten minutes.
            </h2>
            <Link
              href={signedIn ? "/dashboard" : "/register"}
              className="inline-flex h-12 items-center gap-2 rounded-sm bg-flash px-6 text-base font-semibold text-flash-foreground outline-none hover:bg-flash/85 focus-visible:ring-3 focus-visible:ring-ring/60"
            >
              {signedIn ? "Go to dashboard" : "Start free"}{" "}
              <ArrowRightIcon className="size-4" aria-hidden />
            </Link>
          </div>
        </section>
      </main>

      <footer className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-8 text-sm text-muted-foreground sm:px-6">
        <Logo className="text-base text-foreground" />
        <span>© {new Date().getFullYear()} ContentPulse</span>
        <span className="ml-auto flex gap-4">
          <Link
            href="/login"
            className="underline-offset-4 hover:text-foreground hover:underline"
          >
            Sign in
          </Link>
          <Link
            href="/register"
            className="underline-offset-4 hover:text-foreground hover:underline"
          >
            Create an account
          </Link>
        </span>
      </footer>
    </div>
  );
}

function SectionHead({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="grid gap-3 border-t-[3px] border-double border-foreground pt-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:gap-10">
      <h2 id={id} className="headline text-4xl uppercase sm:text-5xl">
        {title}
      </h2>
      {children && (
        <div className="max-w-[62ch] text-base leading-relaxed text-muted-foreground">
          {children}
        </div>
      )}
    </div>
  );
}

function FitScale() {
  const ticks = [...WIRE].sort((a, b) => a.fit - b.fit);
  return (
    <section
      aria-labelledby="fit-title"
      className="mx-auto max-w-7xl px-4 py-16 sm:px-6"
    >
      <SectionHead id="fit-title" title="One score for every trend">
        <p>
          Popular isn&apos;t the same as relevant. Every trend gets one score
          from 0 to 100 for each client, from how closely it matches their
          services, their audience and the material in their knowledge base. At
          45 a trend is Relevant and at 75 Highly relevant; only those get post
          ideas, so the rest never take up your team&apos;s time.
        </p>
        <p className="mt-3">
          Posts are written from the client&apos;s own documents, so every claim
          can be traced back to something they said.
        </p>
      </SectionHead>

      <figure className="mt-10">
        <div
          className="relative h-28"
          role="img"
          aria-label={`Example scores on a 0 to 100 scale. Relevant starts at ${EXAMPLE_CLIENT.threshold}; ${ticks.filter((t) => t.fit >= EXAMPLE_CLIENT.threshold).length} of ${ticks.length} items reach it.`}
        >
          <div
            aria-hidden
            className="absolute inset-y-0 right-0 bg-flash/10"
            style={{ left: `${EXAMPLE_CLIENT.threshold}%` }}
          />
          <div
            aria-hidden
            className="absolute inset-x-0 bottom-6 border-t-2 border-foreground"
          />
          {[0, 25, 50, 75, 100].map((n) => (
            <span
              key={n}
              aria-hidden
              className="slug absolute bottom-0 -translate-x-1/2 text-muted-foreground tabular-nums"
              style={{ left: `${n}%` }}
            >
              {n}
            </span>
          ))}
          <span
            aria-hidden
            className="absolute top-0 bottom-6 border-l-2 border-dashed border-flash"
            style={{ left: `${EXAMPLE_CLIENT.threshold}%` }}
          >
            <span className="slug absolute top-0 left-2 font-semibold whitespace-nowrap text-flash">
              Relevant {EXAMPLE_CLIENT.threshold}+
            </span>
          </span>
          {ticks.map((t, i) => {
            const fits = t.fit >= EXAMPLE_CLIENT.threshold;
            return (
              <span
                key={t.id}
                aria-hidden
                title={`${t.headline} (score ${t.fit}, ${relevanceOf(t).toLowerCase()})`}
                className={cn(
                  "absolute bottom-6 w-0.5 -translate-x-1/2",
                  fits ? "bg-flash" : "bg-paper-6",
                )}
                style={{
                  left: `${t.fit}%`,
                  height: `${2.25 + (i % 3) * 0.9}rem`,
                }}
              />
            );
          })}
        </div>
        <figcaption className="mt-3 text-xs text-muted-foreground">
          The example wire above, placed on the scale for {EXAMPLE_CLIENT.name}.
          Red ticks are Relevant or better.
        </figcaption>
      </figure>
    </section>
  );
}

function StaffBox() {
  return (
    <section
      aria-labelledby="staff-title"
      className="mx-auto max-w-7xl px-4 py-16 sm:px-6"
    >
      <SectionHead id="staff-title" title="Who does what">
        <p>
          One workspace per client, three roles inside it. One person can work
          for many clients and switch between them.
        </p>
      </SectionHead>
      <dl className="mt-8 grid gap-0 sm:max-w-3xl">
        {STAFF.map((s) => (
          <div
            key={s.role}
            className="flex flex-wrap items-baseline gap-x-3 border-b border-border py-4"
          >
            <dt className="headline text-2xl uppercase">{s.role}</dt>
            <span
              aria-hidden
              className="hidden flex-1 border-b border-dotted border-paper-6 sm:block"
            />
            <dd className="basis-full text-sm leading-relaxed sm:basis-auto sm:max-w-[42ch]">
              {s.duty}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function WhatItRunsOn() {
  return (
    <section
      aria-labelledby="runs-title"
      className="mx-auto max-w-7xl px-4 py-16 sm:px-6"
    >
      <SectionHead id="runs-title" title="What it works with">
        <p>
          Trend sources that need no keys work from day one. AI is optional and
          switchable: when a model hits its limit, the next one in your list
          takes over, and without any AI the rule-based scoring and templates
          keep every step working.
        </p>
      </SectionHead>
      <div className="mt-8 grid gap-8 sm:grid-cols-3">
        {[
          [
            "Trend sources",
            "Google Trends, Google News, Hacker News, Reddit, RSS. NewsAPI and X with your keys.",
          ],
          [
            "Platforms",
            "LinkedIn, X, Instagram, Facebook and blog posts with SEO fields and Markdown export.",
          ],
          [
            "Writing and images",
            "Gemini, Groq, Cerebras, Anthropic, OpenAI or OpenRouter for text; Seedream, Cloudflare, Gemini or OpenAI for images.",
          ],
        ].map(([title, body]) => (
          <div key={title} className="border-t border-foreground pt-3">
            <h3 className="slug font-semibold">{title}</h3>
            <p className="mt-2 text-sm leading-relaxed">{body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

const FAQ = [
  {
    q: "What does ContentPulse actually do?",
    a: "It watches the trends in each client's market, scores how well each one fits that client, and helps your team turn the good ones into finished posts: a plan, the copy, the image and an approval, all in one place.",
  },
  {
    q: "Does it post to LinkedIn, X, Instagram or Facebook for me?",
    a: "Not yet. Approved posts are marked ready to publish, and you share or copy them to the platform. Nothing is ever posted without a person approving it.",
  },
  {
    q: "Where do the trends come from?",
    a: "Google Trends, Google News, Hacker News, Reddit and any RSS feeds you add work straight away. NewsAPI-style sources and X can be added with their keys.",
  },
  {
    q: "How does it avoid making things up?",
    a: "Posts are written from the client's own material: their profile, services and the pages of their website you add to the knowledge base. Each draft shows which sources it used.",
  },
  {
    q: "Who on my team can do what?",
    a: "Admins set up clients, invite people and approve posts. Creators shortlist topics, write posts and add designs. Viewers can read everything and share finished posts, which suits a client contact.",
  },
  {
    q: "What if AI isn't set up?",
    a: "Everything still works: trends get a rule-based score and posts start from platform templates you can edit. With AI connected, you get written reasons, full drafts and generated images.",
  },
];

function Faq() {
  return (
    <section
      id="faq"
      aria-labelledby="faq-title"
      className="mx-auto max-w-7xl scroll-mt-6 px-4 py-16 sm:px-6"
    >
      <SectionHead id="faq-title" title="Questions" />
      <div className="mt-8 border-t border-foreground lg:ml-[calc(40%+1rem)]">
        {FAQ.map(({ q, a }) => (
          <details key={q} className="group border-b border-border">
            <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-4 py-3 text-base font-semibold outline-none focus-visible:ring-3 focus-visible:ring-ring/60 [&::-webkit-details-marker]:hidden">
              {q}
              <span
                aria-hidden
                className="slug shrink-0 text-muted-foreground group-open:hidden"
              >
                Open
              </span>
              <span
                aria-hidden
                className="slug hidden shrink-0 text-muted-foreground group-open:inline"
              >
                Close
              </span>
            </summary>
            <p className="max-w-[64ch] pb-5 text-sm leading-relaxed text-muted-foreground">
              {a}
            </p>
          </details>
        ))}
      </div>
    </section>
  );
}
