---
name: ContentPulse
description: The Wire Desk. Trends arrive as wire copy; the desk spikes what doesn't fit the client and runs what does.
colors:
  flash-red: "oklch(0.495 0.2 29)"
  wire-blue: "oklch(0.42 0.14 264)"
  paper-0: "oklch(0.982 0.003 95)"
  paper-1: "oklch(0.962 0.005 95)"
  paper-2: "oklch(0.938 0.007 95)"
  paper-3: "oklch(0.905 0.008 95)"
  paper-4: "oklch(0.86 0.008 95)"
  paper-5: "oklch(0.76 0.008 95)"
  paper-6: "oklch(0.62 0.008 95)"
  paper-7: "oklch(0.455 0.008 95)"
  paper-8: "oklch(0.36 0.006 95)"
  paper-9: "oklch(0.26 0.004 95)"
  paper-10: "oklch(0.18 0.002 95)"
  destructive: "oklch(0.5 0.19 27)"
  success: "oklch(0.52 0.12 150)"
  warning: "oklch(0.68 0.14 70)"
typography:
  display:
    fontFamily: "Archivo, Geist, ui-sans-serif, sans-serif"
    fontSize: "clamp(3.25rem, 8vw, 6rem)"
    fontWeight: 800
    lineHeight: 0.95
    letterSpacing: "-0.01em"
    fontVariation: "'wdth' 72"
  headline:
    fontFamily: "Archivo, Geist, ui-sans-serif, sans-serif"
    fontSize: "2.25rem"
    fontWeight: 800
    lineHeight: 0.95
    letterSpacing: "-0.01em"
    fontVariation: "'wdth' 72"
  title:
    fontFamily: "Archivo, Geist, ui-sans-serif, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 800
    lineHeight: 0.95
    letterSpacing: "-0.01em"
    fontVariation: "'wdth' 72"
  body:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.625
  body-lead:
    fontFamily: "Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 400
    lineHeight: 1.625
  label:
    fontFamily: "Martian Mono, ui-monospace, monospace"
    fontSize: "0.6875rem"
    fontWeight: 400
    lineHeight: "1rem"
    letterSpacing: "0.04em"
    fontVariation: "'wdth' 88"
    fontFeature: "'tnum' 1"
rounded:
  flag: "2px"
  sm: "0.18rem"
  md: "0.24rem"
  lg: "0.3rem"
  xl: "0.42rem"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "32px"
  xl: "64px"
components:
  button-primary:
    backgroundColor: "{colors.paper-10}"
    textColor: "{colors.paper-0}"
    rounded: "{rounded.lg}"
    height: "32px"
    padding: "0 10px"
  button-outline:
    backgroundColor: "{colors.paper-2}"
    textColor: "{colors.paper-10}"
    rounded: "{rounded.lg}"
    height: "32px"
    padding: "0 10px"
  button-ghost:
    textColor: "{colors.paper-10}"
    rounded: "{rounded.lg}"
    height: "32px"
    padding: "0 10px"
  button-ink-landing:
    backgroundColor: "{colors.paper-10}"
    textColor: "{colors.paper-0}"
    rounded: "{rounded.sm}"
    height: "44px"
    padding: "0 20px"
  button-line-landing:
    textColor: "{colors.paper-10}"
    rounded: "{rounded.sm}"
    height: "44px"
    padding: "0 20px"
  button-flash:
    backgroundColor: "{colors.flash-red}"
    textColor: "{colors.paper-0}"
    rounded: "{rounded.sm}"
    height: "44px"
    padding: "0 16px"
  input:
    textColor: "{colors.paper-10}"
    rounded: "{rounded.lg}"
    height: "32px"
    padding: "4px 10px"
  card:
    backgroundColor: "{colors.paper-0}"
    textColor: "{colors.paper-10}"
    rounded: "{rounded.xl}"
    padding: "16px"
  nav-item:
    textColor: "{colors.paper-10}"
    rounded: "{rounded.sm}"
    height: "36px"
    padding: "0 10px"
  nav-item-active:
    backgroundColor: "{colors.paper-10}"
    textColor: "{colors.paper-0}"
    rounded: "{rounded.sm}"
    height: "36px"
    padding: "0 10px"
  priority-flag:
    backgroundColor: "{colors.flash-red}"
    textColor: "{colors.paper-0}"
    typography: "{typography.label}"
    rounded: "{rounded.flag}"
    height: "20px"
    padding: "0 6px"
  priority-flag-routine:
    textColor: "{colors.paper-7}"
    typography: "{typography.label}"
    rounded: "{rounded.flag}"
    height: "20px"
    padding: "0 6px"
  status-tag:
    rounded: "{rounded.full}"
    height: "20px"
    padding: "0 8px"
---

# Design System: ContentPulse

## Overview

**Creative North Star: "The Wire Desk"**

ContentPulse is set like a newsroom wire desk. The ground is warm-grey newsprint, the type is black ink, and the furniture is the furniture of a copy desk: slug lines in a teleprinter mono, headlines in a condensed news grotesk, hairline and double rules instead of boxes, a perforated tape edge on the wire, a red priority flag on what matters, a spike for what doesn't run, and an OK stamp for what does. One world serves both the public landing page and the signed-in app; the landing page performs it, the app works inside it.

Density is a working desk's density: compact controls (32px app buttons, 36px nav rows) on pointer devices, every control 44px on touch. Colour is almost absent. Every neutral comes from one eleven-step paper-to-ink ramp, and the night desk (dark mode) reads the same ramp from the ink end rather than introducing a second palette. Red is the one loud thing, and it means "fits / urgent / run this". Blue is the wire's working colour: links, selection, focus.

The world explicitly refuses the content-SaaS default: gradient hero, floating dashboard screenshot, three feature cards.

**Key Characteristics:**
- Warm-grey newsprint ground (hue 95, near-zero chroma) with black ink.
- One neutral ramp, paper-0 to paper-10, inverted for the night desk.
- Flash red reserved for fit, urgency and the main run action.
- Three type voices: condensed headline, mono slug, plain UI sans.
- Rules, not boxes: hairlines, dashed perforations and a 3px double rule under every page head.
- Flat surfaces; one soft lift for a post set on the desk.
- Status is always a word; colour only reinforces it.

## Colors

A newsprint palette: one warm-grey ramp from paper to ink, one red for priority, one blue for the wire.

### Primary
- **Flash Red** (`flash-red`): the priority colour. Priority flags (URGENT, FLASH), fit ticks that clear the client's bar, the read line on the wire tape, the OK stamp, the "fits." word in the hero, and the landing page's Start free button. In the app it appears only as the active nav icon, the text caret and the wordmark's live dot. Night desk: `oklch(0.68 0.19 29)` with ink-dark text on it.

### Secondary
- **Wire Blue** (`wire-blue`): the working colour. Focus rings (`--ring`), text selection (26% mix), links and coloured inline text (`--primary-strong`), hashtags in a set post. Night desk: `oklch(0.74 0.12 262)`.

### Neutral
- **Newsprint** (`paper-2`): page background on the light desk.
- **Clean Sheet** (`paper-0`): cards, popovers and the wire tape; also text on ink and flash fills.
- **Sidebar Stock** (`paper-1`): the app sidebar.
- **Proof Grey** (`paper-3`): muted, secondary and accent fills; hover rows.
- **Hairline** (`paper-4`): borders, dividers, sidebar border.
- **Field Rule** (`paper-5`): input strokes, scrollbar thumb.
- **Spiked Grey** (`paper-6`): fit ticks under the bar, dotted leaders.
- **Slug Grey** (`paper-7`): muted text, slug metadata, ROUTINE flags.
- **Ink** (`paper-10`): body text, primary buttons, active nav, double rules.
- `paper-8` and `paper-9` fill the chart ramp (`chart-1` to `chart-5` run paper-4 to paper-9); charts are monochrome.

### Feedback
- **Destructive** (`destructive`), **Success** (`success`), **Warning** (`warning`): semantic states only, each re-tuned lighter on the night desk.

### Status tags (sanctioned exception)
Coloured status tags (`lib/tones.ts`) are kept at the user's request: soft tint, readable 800-weight text and an inset hairline ring, each tag carrying its word. One tone always means one thing (green done, blue new, sky under way, amber needs a decision, orange sent back, violet waiting on someone, red rejected, neutral archived); platforms use their own recognizable hues. These hues live only inside tags and platform tabs.

### Named Rules
**The One Ramp Rule.** Every neutral is a `paper-*` step. Never add a stray grey; the night desk swaps the ramp's values, not its names.

**The Flash Is Priority Rule.** Red means "fits, urgent, run". It is never decoration, never a background wash larger than the 10% tint marking the fit zone, and in the app never a button fill.

**The Wire Is Blue Rule.** Focus, selection and links are wire blue, everywhere, in both modes.

## Typography

**Display Font:** Archivo at 72% width (with Geist, ui-sans-serif)
**Body Font:** Geist (with ui-sans-serif, system-ui)
**Label/Mono Font:** Martian Mono at 88% width (with ui-monospace)

**Character:** A condensed, heavy news grotesk for headlines over a neutral UI sans, with a narrow teleprinter mono carrying every piece of wire metadata. Three voices, each with one job.

### Hierarchy
- **Display** (800, clamp(3.25rem, 8vw, 6rem), 0.95): the landing hero, uppercase. Closing banner uses the same face at clamp(2.5rem, 6vw, 4.5rem).
- **Headline** (800, 2.25rem, 0.95): app page titles (sentence case); landing section heads at 2.25rem to 3rem, uppercase.
- **Title** (800, 1.5rem, 0.95): desk names, roles, the headline set on the desk (up to 1.875rem), the wordmark (900, uppercase).
- **Body** (400, 0.875rem, 1.625): all app text and landing list copy, capped at 62ch. Lead paragraphs step to 1rem to 1.125rem, capped at 60ch.
- **Label** (400 or 600, 0.6875rem, 0.04em, uppercase): the slug line. Sources, timestamps, fit scores, the masthead clock, priority flags, sidebar group labels, column headings on the landing.

Numbers in tables, counts and scores are tabular. `h1` and `h2` balance their wrap. Links underline at a 0.2em offset.

### Named Rules
**The Three Voices Rule.** Headlines are condensed Archivo, metadata is Martian Mono slug, everything a person reads or operates is Geist. Don't set running text in the mono or the condensed face.

**The Uppercase Belongs To Slugs Rule.** Uppercase is for slug lines, the wordmark and landing headlines. App page titles and UI text stay in sentence case.

## Layout

Content sits in a 80rem (max-w-7xl) column with 16px gutters, 24px from the small breakpoint. Landing sections run on a 64px vertical rhythm, each opened by a 3px double rule with the heading in a 2:3 split against its explanation from the large breakpoint. The first viewport is the same 2:3 split: the wire tape left (sticky, full viewport height, 36rem to 56rem), headline, CTAs and desk right; on small screens the headline leads and the tape follows.

The app is a fixed sidebar (paper-1, hairline right border) with a page column; each page opens with a page head (title, one-line description, actions right) ruled off by the double rule, 32px above content. Lists are hairline-divided rows rather than stacked cards wherever possible. Spacing steps are 4, 8, 16, 32 and 64px.

**The Coarse Pointer Rule.** On touch screens every button, input, select, tab and menu item is at least 44px tall, and buttons at least 44px wide. Desktop density is a pointer privilege.

## Elevation & Depth

Flat by default. Depth comes from tone (paper-2 ground, paper-0 sheets, paper-1 sidebar), hairlines and a 1px inset ring of ink at 10% on cards and dialogs. The one deliberate lift is a post set on the desk: a 1px paper-4 baseline plus a long, soft, low-opacity drop beneath, like a proof lying on the desk. Sheets keep the stock large shadow for their overlay.

### Shadow Vocabulary
- **Set proof** (`box-shadow: 0 1px 0 var(--paper-4), 0 12px 28px -18px oklch(0.2 0 0 / 0.45)`): a finished post shown as it will run.

### Named Rules
**The Rules Not Boxes Rule.** Separate with hairlines, dashed perforations and the double rule before reaching for a container or a shadow.

## Shapes

Corners are tight, set from a 0.3rem base: 2px for priority flags, 0.18rem for landing buttons, nav rows and the OK stamp, 0.3rem for app buttons and inputs, 0.42rem for cards and dialogs. Pills are reserved for status tags, avatars and the wordmark's live dot. Recurring line forms: the 3px double rule under heads, 1px hairlines between rows, a dashed perforation column (3px holes on a 16 by 18px grid) on the tape's left edge, a 2px flash rule as the wire's read line, dotted leaders between a role and its duty, and a dashed border for spiked items and read-only notices. The OK stamp is the only rotated form (-6deg).

## Components

### Buttons
Ink on paper, compact and plain.
- **Shape:** 0.3rem in the app, 0.18rem on the landing.
- **Primary:** ink fill, paper text, 32px tall, 10px side padding, 500 weight; hover drops to 80% ink.
- **Outline / Ghost / Secondary:** background with a hairline, or bare; hover fills with proof grey. Destructive is a 10% red tint with red text.
- **Landing:** 44px ink button and 44px line button (1px ink stroke that floods to ink on hover), 600 weight. The masthead and closing banner carry Start free as the flash button (44px and 48px); the hero pairs the ink and line buttons.
- **Focus:** 3px wire-blue ring at 50 to 60%. Pressed buttons drop 1px.

### Priority flags
The signature mark. A 20px slug word (FLASH, URGENT, ROUTINE, NEW) on a 2px-cornered tab. URGENT and FLASH are flash-filled; FLASH adds a 2px flash outline offset 1px; ROUTINE and NEW are an inset hairline with slug-grey text. A flag stamps on (200ms scale-in) when the desk reads the item.

### Status tags
20px pills, 11px medium text, soft tint and inset ring from the tone vocabulary, optional 6px leading dot. Always carry the word.

### Cards / Containers
- **Corner Style:** 0.42rem.
- **Background:** clean sheet (paper-0) on newsprint.
- **Shadow Strategy:** none; a 1px ring of ink at 10%.
- **Internal Padding:** 16px (12px small).

### Inputs / Fields
- **Style:** transparent, 1px field-rule stroke, 0.3rem corners, 32px tall; the caret is flash red.
- **Focus:** wire-blue border and 3px wire ring at 50%.
- **Error / Disabled:** destructive border and 20% ring; disabled at 50% opacity.

### Navigation
Sidebar rows are 36px (44px on touch), 14px Geist with a 16px icon, 0.18rem corners. Active row is ink-filled with paper text and a flash-red icon; hover fills with proof grey. Groups are headed by slug labels. The landing masthead is always the night desk: ink strip, 56px tall, wordmark left, slug clock and account actions right.

### The wire tape (landing)
A clean-sheet column with a perforated left edge, hairline-divided rows of flag, slug (source · time), right-aligned fit score and a one-line headline. Items under the client's bar go slug grey and are struck through; the selected row inverts to ink. The feed steps up one row every 1800ms (260ms, cubic-bezier(0.16, 1, 0.3, 1)), pauses on hover and focus, can be stopped, and stands still under reduced motion.

### The desk (landing)
The chosen item's flag, fit and source as a slug line, its headline in the title face, then either the set post (set-proof shadow, OK stamp landing at -6deg after a 520ms top-down reveal) or the spike mark with a dashed rule and the word "Spiked".

## Do's and Don'ts

### Do:
- **Do** take every neutral from `paper-0` to `paper-10` and let the night desk re-map the ramp.
- **Do** reserve flash red for fit, urgency, the read line, the OK stamp and the landing's main run action.
- **Do** use wire blue for focus rings, selection and links in both modes.
- **Do** set sources, timestamps, scores and section labels as uppercase Martian Mono slugs with tabular numbers.
- **Do** rule off every page head with the 3px double ink rule.
- **Do** make every status a word; colour, tint and ring only reinforce it.
- **Do** keep touch targets at 44px and respect reduced motion on every animation.

### Don't:
- **Don't** add greys outside the paper ramp.
- **Don't** fill app buttons with flash red or use red for decoration.
- **Don't** build a gradient hero, a floating dashboard screenshot or a row of three feature cards.
- **Don't** set running text in the condensed headline face or the mono.
- **Don't** let a status rely on colour alone.
- **Don't** reach for a shadow to separate content; the set proof is the only lift.

## Known Gaps

Shipped state, not system rules. Carried forward from the finish review; the world's devices exist on the landing page but have not yet reached the app.
- The app does not yet use priority flags, datelines, the OK stamp or the spike.
- Trend scores in the app are not yet set as mono slugs.
- Login is a stock card.
- The trends list does not yet lead with the post each trend could become.
