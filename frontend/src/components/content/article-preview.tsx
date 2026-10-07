import { Fragment, type ReactNode } from "react";

import type { BlogMeta } from "@/types/api";

/** `**bold**` inside a line; everything else stays plain text (no HTML). */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
      <strong key={i}>{part.slice(2, -2)}</strong>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

/** The small Markdown subset blog bodies use: ##/### headings, lists, paragraphs. */
export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();
    if (!line) {
      i++;
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      blocks.push(
        level <= 2 ? (
          <h2 key={i} className="mt-5 text-lg font-semibold first:mt-0">
            {inline(heading[2])}
          </h2>
        ) : (
          <h3 key={i} className="mt-4 font-semibold">
            {inline(heading[2])}
          </h3>
        ),
      );
      i++;
      continue;
    }
    const bullet = /^([-*]|\d+[.)])\s+/;
    if (bullet.test(line)) {
      const ordered = /^\d/.test(line);
      const items: string[] = [];
      while (i < lines.length && bullet.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(bullet, ""));
        i++;
      }
      const List = ordered ? "ol" : "ul";
      blocks.push(
        <List key={i} className={ordered ? "list-decimal space-y-1 pl-5" : "list-disc space-y-1 pl-5"}>
          {items.map((item, n) => (
            <li key={n}>{inline(item)}</li>
          ))}
        </List>,
      );
      continue;
    }
    const paragraph: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^#{1,4}\s/.test(lines[i].trim()) && !bullet.test(lines[i].trim())) {
      paragraph.push(lines[i].trim());
      i++;
    }
    blocks.push(<p key={i}>{inline(paragraph.join(" "))}</p>);
  }
  return <>{blocks}</>;
}

/** How a blog article reads: search snippet, then the article itself. */
export function ArticlePreview({
  title,
  seo,
  intro,
  body,
  cta,
}: {
  title: string | null;
  seo: BlogMeta | null | undefined;
  intro: string | null;
  body: string | null;
  cta: string | null;
}) {
  const headline = seo?.seo_title || title;
  return (
    <div className="grid gap-4">
      {(seo?.meta_title || seo?.meta_description) && (
        <figure aria-label="Search result preview" className="grid gap-0.5 rounded-lg border p-3 text-sm">
          <span className="truncate text-xs text-muted-foreground">yourwebsite.com › blog › {seo?.slug || "…"}</span>
          <span className="truncate text-base text-blue-700 dark:text-blue-400">{seo?.meta_title || headline}</span>
          <span className="line-clamp-2 text-muted-foreground">{seo?.meta_description}</span>
        </figure>
      )}
      <article className="grid gap-3 rounded-lg bg-muted/50 p-4 text-sm leading-relaxed">
        {headline && <h1 className="text-xl font-semibold text-balance">{headline}</h1>}
        {intro && <Markdown text={intro} />}
        {body && <Markdown text={body} />}
        {cta && <p className="border-l-2 border-primary pl-3 font-medium">{cta}</p>}
        {!!seo?.keywords?.length && (
          <p className="text-xs text-muted-foreground">Keywords: {seo.keywords.join(", ")}</p>
        )}
      </article>
    </div>
  );
}
