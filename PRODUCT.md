# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: marketing agencies producing social content for several client organizations. One person can belong to many organizations and switches between them (one organization per client). Inside each organization there are three roles:

- **Admin**: sets up the client (profile, services, brand, platforms, knowledge base), invites the team, and approves posts.
- **Creator**: shortlists topics, plans and writes posts, adds the design and submits for approval.
- **Viewer**: reads everything and shares finished posts (for example a client contact).

Their situation: a small team with many clients, each needing a steady flow of on-brand, relevant posts, and little time to watch trends or chase approvals.

## Product Purpose

ContentPulse finds what is trending in a client's markets, keeps only what fits that client's services and knowledge base, and carries each chosen topic to an approved, ready-to-publish post: plan, AI-written copy, design (uploaded or AI-generated) and approval, in one flow.

Success: a post goes from a trend to "Ready to publish" in about seven clicks, and every claim in it is backed by the client's own material.

## Positioning

Trends that fit you, to approved posts. Generic trend tools stop at "what is popular"; generic AI writers start from a blank prompt. ContentPulse scores every trend against the client's own services, audience and knowledge base, then writes grounded posts and runs them through design and approval in the same place.

## Operating Context

- Workflow: Trends → Topics (shortlist) → Post plan → Content studio (write) → Design (upload or AI image) → Approvals (approve = ready to publish).
- Platforms: LinkedIn, X, Instagram, Facebook and Blog (with SEO and Markdown export).
- Publishing today is manual: "Ready to publish" posts are shared through the device share sheet or copied (blog: Markdown export).
- Trend sources: Google Trends, Google News, Hacker News, Reddit and RSS without keys; NewsAPI-style sources and X with keys.
- AI is optional and switchable: text models (Gemini, Groq, Cerebras, Anthropic, OpenAI, OpenRouter), Gemini embeddings, image models (Kie AI Seedream, Cloudflare, Gemini, OpenAI). Without AI, rule-based analysis and template drafts keep every step working.

## Capabilities and Constraints

- Multi-tenant: every record belongs to one organization; people only see organizations they belong to.
- Nothing is published automatically; a person approves every post.
- Posts only make claims the client's knowledge base supports (grounding and corrections are recorded).
- Optional integrations or missing keys must never crash or stop the app.
- Runs locally with only Postgres; Redis, Celery and AWS deployment are optional.
- Undecided: direct publishing and scheduling to social platforms; pricing; public sign-up policy.

## Brand Commitments

- Name: ContentPulse. The current pulse mark and teal colour are not binding and may change.

## Evidence on Hand

- The working product itself: real trend discovery, scoring, post plans, studio, design tasks, approvals and feed previews can be shown with demonstration data.
- No customers, testimonials, logos, usage numbers or benchmarks exist yet. Do not invent any; demonstration content must be labelled as an example.

## Product Principles

1. Fit before volume: a relevant trend beats a popular one.
2. Every claim grounded: the client's own material is the source of truth.
3. Fewest steps to an approved post; no step without a decision in it.
4. Humans decide: AI drafts, people approve.
5. Never break on a missing integration: degrade to a working, labelled fallback.

## Accessibility & Inclusion

Target WCAG 2.2 AA across the app: labelled controls, visible focus, 4.5:1 text contrast, 44 px touch targets on phones, and usable in light and dark mode.
