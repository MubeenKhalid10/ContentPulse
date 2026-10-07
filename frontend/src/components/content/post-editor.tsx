"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { SaveIcon, WandSparklesIcon } from "lucide-react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { fieldAria, FormField } from "@/components/shared/form-field";
import { SimpleSelect } from "@/components/shared/simple-select";
import { TagInput } from "@/components/shared/tag-input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useUpdatePost } from "@/hooks/use-content";
import { ApiError, errorMessage } from "@/lib/api";
import {
  DESIGN_FORMAT_OPTIONS,
  fullText,
  META_DESCRIPTION_MAX,
  META_TITLE_MAX,
  SLUG_PATTERN,
  slugify,
  wordCount,
} from "@/lib/content";
import { PLATFORM_LABEL } from "@/lib/topics";
import { cn } from "@/lib/utils";
import type { DesignFormat, PostDetail } from "@/types/api";

const schema = z.object({
  hook: z.string().trim().max(5000),
  body: z.string().trim().min(1, "The post needs a body.").max(60_000),
  cta: z.string().trim().max(2000),
  hashtags: z.array(z.string()),
  visual_concept: z.string().trim().max(2000),
  design_format: z.string(),
  // Blog only.
  seo_title: z.string().trim().max(200),
  meta_title: z.string().trim().max(200),
  meta_description: z.string().trim().max(400),
  slug: z
    .string()
    .trim()
    .max(120)
    .refine((v) => !v || SLUG_PATTERN.test(v), "Lowercase letters, numbers and hyphens only."),
  keywords: z.array(z.string()).max(15, "Up to 15 keywords."),
  change_note: z.string().trim().max(300),
});
type Values = z.infer<typeof schema>;

/** Editing never overwrites: saving creates the next version (spec rule 4). */
export function PostEditor({ post, canEdit }: { post: PostDetail; canEdit: boolean }) {
  const update = useUpdatePost();
  const v = post.current;
  const isBlog = post.platform === "blog";
  const seo = v?.meta.blog ?? {};
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      hook: v?.hook ?? "",
      body: v?.body ?? "",
      cta: v?.cta ?? "",
      hashtags: v?.hashtags.map((h) => (h.startsWith("#") ? h : `#${h}`)) ?? [],
      visual_concept: v?.meta.visual_concept ?? "",
      design_format: v?.meta.design_format ?? "",
      seo_title: seo.seo_title ?? "",
      meta_title: seo.meta_title ?? "",
      meta_description: seo.meta_description ?? "",
      slug: seo.slug ?? "",
      keywords: seo.keywords ?? [],
      change_note: "",
    },
  });
  const { errors, isDirty } = form.formState;
  const [hook, body, cta, hashtags, seoTitle, metaTitle, metaDescription] = useWatch({
    control: form.control,
    name: ["hook", "body", "cta", "hashtags", "seo_title", "meta_title", "meta_description"],
  });
  const length = fullText(hook, body, cta, hashtags).length;
  const words = wordCount(hook, body, cta);
  const max = post.limits.max_length;
  const over = max != null && length > max;
  const locked = !canEdit || !post.editable;

  const onSubmit = form.handleSubmit((values) =>
    update.mutate(
      {
        id: post.id,
        base_version: post.current_version,
        hook: values.hook || null,
        body: values.body,
        cta: values.cta || null,
        hashtags: values.hashtags.map((h) => (h.startsWith("#") ? h : `#${h}`)),
        visual_concept: values.visual_concept || null,
        design_format: (values.design_format || null) as DesignFormat | null,
        ...(isBlog && {
          blog: {
            seo_title: values.seo_title || null,
            meta_title: values.meta_title || null,
            meta_description: values.meta_description || null,
            slug: values.slug || null,
            keywords: values.keywords,
          },
        }),
        change_note: values.change_note || null,
      },
      {
        onSuccess: (saved) =>
          toast.success(
            saved.current_version > post.current_version ? `Saved as version ${saved.current_version}` : "No changes to save",
          ),
        onError: (e) => {
          if (e instanceof ApiError) {
            for (const [field, message] of Object.entries(e.fieldErrors)) {
              const key = field.replace(/^blog\./, "").split(".")[0];
              if (key in values) form.setError(key as keyof Values, { message });
            }
          }
          toast.error(e instanceof ApiError && e.status === 409 ? e.message : errorMessage(e));
        },
      },
    ),
  );

  return (
    <form noValidate onSubmit={onSubmit} aria-label="Post editor" className="grid gap-6">
      <fieldset disabled={locked} className="grid gap-6">
        <Card>
          <CardHeader>
            <CardTitle>{isBlog ? "Blog article" : `${PLATFORM_LABEL[post.platform]} post`}</CardTitle>
            <CardDescription>
              {post.editable
                ? "Edit freely: saving keeps the previous version in the history."
                : "This post has moved on from drafting, so the copy is read-only."}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5">
            <FormField
              id="post-hook"
              label={isBlog ? "Introduction" : "Hook"}
              hint={isBlog ? "The hook: what the reader gets from the article." : undefined}
              error={errors.hook?.message}
            >
              <Textarea {...fieldAria("post-hook", errors.hook?.message)} rows={isBlog ? 4 : 2} {...form.register("hook")} />
            </FormField>
            <FormField
              id="post-body"
              label="Body"
              hint={isBlog ? "Markdown: '## ' for sections, '### ' for subheadings, ending with a conclusion." : undefined}
              error={errors.body?.message}
            >
              <Textarea
                {...fieldAria("post-body", errors.body?.message)}
                rows={post.platform === "x" ? 5 : isBlog ? 24 : 10}
                className={cn(isBlog && "font-mono text-[13px]")}
                {...form.register("body")}
              />
            </FormField>
            <FormField id="post-cta" label="Call to action" error={errors.cta?.message}>
              <Textarea {...fieldAria("post-cta", errors.cta?.message)} rows={2} {...form.register("cta")} />
            </FormField>
            {(!isBlog || hashtags.length > 0) && (
              <FormField
                id="post-hashtags"
                label="Hashtags"
                hint={post.limits.hashtag_limit != null ? `Up to ${post.limits.hashtag_limit} for ${PLATFORM_LABEL[post.platform]}.` : undefined}
              >
                <Controller
                  control={form.control}
                  name="hashtags"
                  render={({ field }) => (
                    <TagInput id="post-hashtags" value={field.value} onChange={field.onChange} placeholder="#Hashtag" disabled={locked} />
                  )}
                />
              </FormField>
            )}
            <p className={cn("text-xs tabular-nums", over ? "font-medium text-destructive" : "text-muted-foreground")} aria-live="polite">
              {isBlog && `${words.toLocaleString()} words · `}
              {length.toLocaleString()}
              {max != null && ` / ${max.toLocaleString()}`} characters
            </p>
          </CardContent>
        </Card>

        {isBlog && (
          <Card>
            <CardHeader>
              <CardTitle>SEO</CardTitle>
              <CardDescription>How the article appears in search results and its URL. Nothing is published automatically.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-5">
              <FormField id="post-seo-title" label="SEO title" hint="The article headline (H1)." error={errors.seo_title?.message}>
                <Input {...fieldAria("post-seo-title", errors.seo_title?.message)} {...form.register("seo_title")} />
              </FormField>
              <FormField id="post-meta-title" label="Meta title" error={errors.meta_title?.message}>
                <Input {...fieldAria("post-meta-title", errors.meta_title?.message)} {...form.register("meta_title")} />
                <Counter value={metaTitle.length} max={META_TITLE_MAX} />
              </FormField>
              <FormField id="post-meta-description" label="Meta description" error={errors.meta_description?.message}>
                <Textarea
                  {...fieldAria("post-meta-description", errors.meta_description?.message)}
                  rows={2}
                  {...form.register("meta_description")}
                />
                <Counter value={metaDescription.length} max={META_DESCRIPTION_MAX} />
              </FormField>
              <div className="grid gap-5 sm:grid-cols-2">
                <FormField id="post-slug" label="Slug" error={errors.slug?.message}>
                  <div className="flex gap-2">
                    <Input {...fieldAria("post-slug", errors.slug?.message)} placeholder="article-url-slug" {...form.register("slug")} />
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      aria-label="Slug from SEO title"
                      title="Slug from SEO title"
                      disabled={!seoTitle.trim()}
                      onClick={() => form.setValue("slug", slugify(seoTitle), { shouldDirty: true, shouldValidate: true })}
                    >
                      <WandSparklesIcon />
                    </Button>
                  </div>
                </FormField>
                <FormField id="post-keywords" label="Keywords" hint="Primary keyword first." error={errors.keywords?.message}>
                  <Controller
                    control={form.control}
                    name="keywords"
                    render={({ field }) => (
                      <TagInput
                        id="post-keywords"
                        value={field.value}
                        onChange={field.onChange}
                        placeholder="Add a keyword"
                        maxLength={80}
                        disabled={locked}
                      />
                    )}
                  />
                </FormField>
              </div>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Design direction</CardTitle>
            <CardDescription>
              {isBlog ? "The featured image, also used when the article is shared." : "The visual to create for this post."}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5 sm:grid-cols-[12rem_1fr]">
            <FormField id="post-format" label="Format">
              <Controller
                control={form.control}
                name="design_format"
                render={({ field }) => (
                  <SimpleSelect
                    id="post-format"
                    aria-label="Format"
                    value={field.value || undefined}
                    onChange={field.onChange}
                    options={DESIGN_FORMAT_OPTIONS}
                    placeholder="Choose a format"
                    disabled={locked}
                  />
                )}
              />
            </FormField>
            <FormField id="post-visual" label={isBlog ? "Featured image" : "Visual concept"} error={errors.visual_concept?.message}>
              <Textarea {...fieldAria("post-visual", errors.visual_concept?.message)} rows={3} {...form.register("visual_concept")} />
            </FormField>
          </CardContent>
        </Card>
      </fieldset>

      {!locked && (
        <div className="sticky bottom-0 z-10 -mx-1 flex flex-wrap items-center gap-3 rounded-xl border bg-background/95 p-3 shadow-sm backdrop-blur">
          <Input
            aria-label="Change note"
            placeholder="What changed? (optional)"
            className="min-w-48 flex-1"
            {...form.register("change_note")}
          />
          <Button type="button" variant="outline" disabled={!isDirty || update.isPending} onClick={() => form.reset()}>
            Discard
          </Button>
          <Button type="submit" disabled={!isDirty || update.isPending}>
            <SaveIcon />
            {update.isPending ? "Saving…" : "Save version"}
          </Button>
        </div>
      )}
    </form>
  );
}

function Counter({ value, max }: { value: number; max: number }) {
  return (
    <p className={cn("text-xs tabular-nums", value > max ? "font-medium text-destructive" : "text-muted-foreground")}>
      {value} / {max} characters
    </p>
  );
}
