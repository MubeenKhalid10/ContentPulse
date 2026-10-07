import { CheckIcon } from "lucide-react";

const STEPS = [
  [
    "Set up a client",
    "Their services, audience and website. About ten minutes.",
  ],
  [
    "Trends arrive, scored for relevance",
    "Every trend in their market gets a score from 0 to 100. Only what is relevant reaches you.",
  ],
  [
    "Write from their material",
    "Pick a trend, choose the platform, and the post is drafted from the client's own documents.",
  ],
  [
    "Design, approve, publish",
    "Add or generate the image. An admin approves it, then it's ready to post.",
  ],
] as const;

/** Side panel on sign-in screens: what the product does, in four steps. */
export function AuthAside() {
  return (
    <aside aria-labelledby="aside-title" className="grid content-center gap-8">
      <div className="grid gap-3">
        <p id="aside-title" className="headline text-2xl uppercase">
          From trend to approved post.
        </p>
        <p className="max-w-[46ch] text-sm leading-relaxed text-muted-foreground">
          ContentPulse is a content workspace for agencies: one workspace per
          client, from trend to ready-to-publish post.
        </p>
      </div>
      <ol className="border-t border-foreground">
        {STEPS.map(([title, body], i) => (
          <li
            key={title}
            className="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-x-3 border-b border-border py-4"
          >
            <span
              className="slug pt-0.5 text-muted-foreground tabular-nums"
              aria-hidden
            >
              {String(i + 1).padStart(2, "0")}
            </span>
            <span className="grid gap-1">
              <span className="text-sm font-semibold">{title}</span>
              <span className="text-sm leading-relaxed text-muted-foreground">
                {body}
              </span>
            </span>
          </li>
        ))}
      </ol>
      <p className="flex items-center gap-2 text-sm">
        <CheckIcon className="size-4 shrink-0 text-flash" aria-hidden />
        Nothing is posted without a person approving it.
      </p>
    </aside>
  );
}
