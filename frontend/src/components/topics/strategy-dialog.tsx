"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { SparklesIcon, WandSparklesIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { fieldAria, FormField } from "@/components/shared/form-field";
import { SimpleSelect } from "@/components/shared/simple-select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateStrategy,
  usePlatformRules,
  useSuggestStrategy,
  useUpdateStrategy,
} from "@/hooks/use-topics";
import { useGeneratePost, usePosts } from "@/hooks/use-content";
import { useOrgSettings } from "@/hooks/use-organization";
import { useAIStatus } from "@/hooks/use-trends";
import { ApiError, errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { PLATFORM_LABEL } from "@/lib/topics";
import type { Platform, SearchIntent, Strategy, StrategyDetails, StrategySuggestion, TopicDetail } from "@/types/api";

const text = (max: number) => z.string().trim().max(max, `Keep it under ${max} characters.`);
const lines = (value: string) =>
  value
    .split(/\n|,/)
    .map((v) => v.trim())
    .filter(Boolean);
const INTENT_OPTIONS: { value: SearchIntent; label: string }[] = [
  { value: "informational", label: "Informational" },
  { value: "commercial", label: "Commercial" },
  { value: "transactional", label: "Transactional" },
  { value: "navigational", label: "Navigational" },
];
const schema = z.object({
  platform: z.enum(["linkedin", "x", "instagram", "facebook", "blog"]),
  post_type: z.string().trim().min(1, "Choose a post type."),
  objective: text(120),
  content_angle: text(2000).min(1, "Describe the angle."),
  target_audience: text(2000),
  hook_direction: text(2000),
  cta_direction: text(2000),
  tone: text(120),
  recommended_format: text(60),
  rationale: text(2000),
  // Blog only: the SEO plan.
  seo_title: text(120),
  primary_keyword: text(80),
  secondary_keywords: z
    .string()
    .refine((v) => lines(v).length <= 15, "Up to 15 keywords.")
    .refine((v) => lines(v).every((k) => k.length <= 80), "Keep each keyword under 80 characters."),
  search_intent: z.string(),
  outline: z
    .string()
    .refine((v) => v.split("\n").filter((h) => h.trim()).length <= 15, "Up to 15 sections.")
    .refine((v) => v.split("\n").every((h) => h.trim().length <= 200), "Keep each heading under 200 characters."),
  target_word_count: z
    .string()
    .trim()
    .refine((v) => !v || (/^\d+$/.test(v) && +v >= 300 && +v <= 6000), "Between 300 and 6,000 words."),
  featured_image_direction: text(2000),
});
type Values = z.infer<typeof schema>;
const FIELDS = [
  "objective",
  "content_angle",
  "target_audience",
  "hook_direction",
  "cta_direction",
  "tone",
  "recommended_format",
  "rationale",
] as const;

function toValues(platform: Platform, s?: Partial<Strategy | StrategySuggestion>, audience?: string | null): Values {
  return {
    platform,
    post_type: s?.post_type ?? "",
    objective: s?.objective ?? "",
    content_angle: s?.content_angle ?? "",
    target_audience: s?.target_audience ?? audience ?? "",
    hook_direction: s?.hook_direction ?? "",
    cta_direction: s?.cta_direction ?? "",
    tone: s?.tone ?? "",
    recommended_format: s?.recommended_format ?? "",
    rationale: s?.rationale ?? "",
    seo_title: s?.details?.seo_title ?? "",
    primary_keyword: s?.details?.primary_keyword ?? "",
    secondary_keywords: (s?.details?.secondary_keywords ?? []).join(", "),
    search_intent: s?.details?.search_intent ?? "",
    outline: (s?.details?.outline ?? []).join("\n"),
    target_word_count: s?.details?.target_word_count ? String(s.details.target_word_count) : "",
    featured_image_direction: s?.details?.featured_image_direction ?? "",
  };
}

function toDetails(values: Values): StrategyDetails | null {
  if (values.platform !== "blog") return null;
  return {
    seo_title: values.seo_title || null,
    primary_keyword: values.primary_keyword || null,
    secondary_keywords: lines(values.secondary_keywords),
    search_intent: (values.search_intent || null) as SearchIntent | null,
    outline: values.outline
      .split("\n")
      .map((h) => h.trim())
      .filter(Boolean),
    target_word_count: values.target_word_count ? Number(values.target_word_count) : null,
    featured_image_direction: values.featured_image_direction || null,
  };
}

/** Empty strings become null so optional fields stay empty in the API. */
function toBody(values: Values) {
  return {
    platform: values.platform,
    post_type: values.post_type,
    ...(Object.fromEntries(FIELDS.map((f) => [f, values[f] || null])) as Record<(typeof FIELDS)[number], string | null>),
    details: toDetails(values),
  };
}

export function StrategyDialog({
  topic,
  open,
  platform,
  editing,
  onClose,
}: {
  topic: TopicDetail;
  open: boolean;
  platform: Platform | null;
  editing: Strategy | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        {open && (
          <StrategyForm
            key={editing?.id ?? platform ?? "new"}
            topic={topic}
            initialPlatform={editing?.platform ?? platform ?? topic.recommended_platforms[0] ?? "linkedin"}
            editing={editing}
            onClose={onClose}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function StrategyForm({
  topic,
  initialPlatform,
  editing,
  onClose,
}: {
  topic: TopicDetail;
  initialPlatform: Platform;
  editing: Strategy | null;
  onClose: () => void;
}) {
  const rules = usePlatformRules();
  const settings = useOrgSettings();
  const ai = useAIStatus();
  const suggest = useSuggestStrategy();
  const create = useCreateStrategy();
  const update = useUpdateStrategy();
  const [source, setSource] = useState<"ai" | "rules" | "manual">(editing?.source ?? "manual");
  const [notice, setNotice] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: toValues(initialPlatform, editing ?? undefined, topic.target_audience),
  });
  const { errors } = form.formState;
  const [platform, postType, objective] = useWatch({
    control: form.control,
    name: ["platform", "post_type", "objective"],
  });
  const rule = rules.data?.find((r) => r.platform === platform);
  // Best fit first, then any platform enabled after the topic was analyzed (e.g. Blog).
  const enabled = settings.data?.enabled_platforms.length
    ? settings.data.enabled_platforms
    : (Object.keys(PLATFORM_LABEL) as Platform[]);
  const platforms = [...new Set([...topic.platform_fit.map((f) => f.platform), ...enabled])];
  const platformOptions = platforms.map((p) => ({ value: p, label: PLATFORM_LABEL[p] }));
  const isBlog = platform === "blog";
  const notEnabled = (Object.keys(PLATFORM_LABEL) as Platform[]).filter((p) => !platforms.includes(p));
  const postTypes = [...new Set([...(rule?.post_types ?? []), ...(postType && !rule ? [postType] : [])])];
  const objectives = [...new Set([...(rule?.objectives ?? []), ...(objective ? [objective] : [])])];
  const generate = useGeneratePost();
  const router = useRouter();
  const canGenerate = useCan()("content.generate");
  const topicPosts = usePosts({ status: "all", platform: "", topicId: topic.id, q: "" }, 50);
  // Editing a plan that already has its post: just save.
  const hasPost = !!editing && (topicPosts.data?.items ?? []).some((p) => p.content_strategy_id === editing.id);
  const saving = create.isPending || update.isPending || generate.isPending;
  const failure = create.error ?? update.error;

  const runSuggest = () =>
    suggest.mutate(
      { topicId: topic.id, platform },
      {
        onSuccess: (draft) => {
          form.reset(toValues(platform, draft));
          setSource(draft.source);
          setNotice(draft.notice);
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    );

  // "Save & write post": save the plan, then write the post from it right away.
  const submitWith = (write: boolean) => form.handleSubmit((values) => {
    const body = toBody(values);
    const done = {
      onSuccess: (saved: Strategy) => {
        if (write && canGenerate) {
          generate.mutate(saved.id, {
            onSuccess: (post) => {
              onClose();
              router.push(`/content/${post.id}`);
            },
            onError: (e) => toast.error(errorMessage(e)),
          });
          return;
        }
        toast.success(editing ? "Plan updated" : `${PLATFORM_LABEL[values.platform]} plan saved`);
        onClose();
      },
      onError: (error: unknown) => {
        if (error instanceof ApiError) {
          for (const [field, message] of Object.entries(error.fieldErrors)) {
            const key = field.replace(/^details\./, "").split(".")[0];
            form.setError((key in values ? key : "content_angle") as keyof Values, { message });
          }
        }
      },
    };
    if (editing) update.mutate({ topicId: topic.id, id: editing.id, ...body }, done);
    else create.mutate({ topicId: topic.id, source, ...body }, done);
  });

  return (
    <form noValidate className="grid gap-5" onSubmit={submitWith(canGenerate && !hasPost)}>
      <DialogHeader>
        <DialogTitle>{editing ? "Edit plan" : "Plan a post"}</DialogTitle>
        <DialogDescription>
          The direction for “{topic.title}” on one platform: what to say, to whom, and how. Save it, or write
          the post from it straight away.
        </DialogDescription>
      </DialogHeader>

      <div className="flex flex-wrap items-end gap-3">
        <FormField id="strategy-platform" label="Platform" className="w-44">
          <Controller
            control={form.control}
            name="platform"
            render={({ field }) => (
              <SimpleSelect
                id="strategy-platform"
                aria-label="Platform"
                value={field.value}
                onChange={(v) => {
                  field.onChange(v);
                  form.setValue("post_type", "");
                  setNotice(null);
                }}
                options={platformOptions}
                disabled={!!editing && editing.status !== "draft"}
              />
            )}
          />
        </FormField>
        <Button type="button" variant="outline" onClick={runSuggest} disabled={suggest.isPending}>
          {ai.data?.engine === "ai" ? <SparklesIcon /> : <WandSparklesIcon />}
          {suggest.isPending
            ? "Drafting…"
            : ai.data?.engine === "ai"
              ? "Draft with AI"
              : "Draft from playbook"}
        </Button>
      </div>

      {notEnabled.length > 0 && (
        <p className="-mt-2 text-xs text-muted-foreground">
          {notEnabled.map((p) => PLATFORM_LABEL[p]).join(", ")} {notEnabled.length === 1 ? "isn't" : "aren't"} enabled
          for your organization.{" "}
          <Link href="/settings" className="underline underline-offset-4">
            Turn on platforms in Settings
          </Link>
          .
        </p>
      )}
      {notice && (
        <Alert>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      )}
      {failure && !(failure instanceof ApiError && failure.status === 422) && (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(failure)}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField id="strategy-post-type" label="Post type" error={errors.post_type?.message}>
          <Controller
            control={form.control}
            name="post_type"
            render={({ field }) => (
              <SimpleSelect
                id="strategy-post-type"
                aria-label="Post type"
                value={field.value || undefined}
                onChange={field.onChange}
                options={postTypes.map((p) => ({ value: p, label: p }))}
                placeholder={rules.isPending ? "Loading…" : "Choose a post type"}
              />
            )}
          />
        </FormField>
        <FormField id="strategy-objective" label="Objective" error={errors.objective?.message}>
          <Controller
            control={form.control}
            name="objective"
            render={({ field }) => (
              <SimpleSelect
                id="strategy-objective"
                aria-label="Objective"
                value={field.value || undefined}
                onChange={field.onChange}
                options={objectives.map((o) => ({ value: o, label: o }))}
                placeholder="Choose an objective"
              />
            )}
          />
        </FormField>
      </div>

      <FormField id="strategy-angle" label="Content angle" error={errors.content_angle?.message}>
        <Textarea {...fieldAria("strategy-angle", errors.content_angle?.message)} rows={3} {...form.register("content_angle")} />
      </FormField>
      <FormField id="strategy-audience" label="Target audience" error={errors.target_audience?.message}>
        <Input {...fieldAria("strategy-audience", errors.target_audience?.message)} {...form.register("target_audience")} />
      </FormField>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          id="strategy-hook"
          label={isBlog ? "Introduction direction" : "Hook direction"}
          hint={isBlog ? "How the article opens." : "How the post opens."}
          error={errors.hook_direction?.message}
        >
          <Textarea {...fieldAria("strategy-hook", errors.hook_direction?.message)} rows={3} {...form.register("hook_direction")} />
        </FormField>
        <FormField id="strategy-cta" label="Call to action" hint="What the reader should do next." error={errors.cta_direction?.message}>
          <Textarea {...fieldAria("strategy-cta", errors.cta_direction?.message)} rows={3} {...form.register("cta_direction")} />
        </FormField>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField id="strategy-tone" label="Tone" error={errors.tone?.message}>
          <Input {...fieldAria("strategy-tone", errors.tone?.message)} placeholder={rule?.tone ?? undefined} {...form.register("tone")} />
        </FormField>
        <FormField
          id="strategy-format"
          label="Format"
          hint={isBlog ? "e.g. 1,500-word how-to guide" : "e.g. 6-slide carousel"}
          error={errors.recommended_format?.message}
        >
          <Input {...fieldAria("strategy-format", errors.recommended_format?.message)} {...form.register("recommended_format")} />
        </FormField>
      </div>
      <FormField id="strategy-rationale" label="Why this approach" error={errors.rationale?.message}>
        <Textarea {...fieldAria("strategy-rationale", errors.rationale?.message)} rows={2} {...form.register("rationale")} />
      </FormField>

      {isBlog && (
        <fieldset className="grid gap-4 rounded-lg border p-4" aria-label="SEO plan">
          <legend className="px-1 text-sm font-medium">SEO plan</legend>
          <FormField id="strategy-seo-title" label="Working SEO title" error={errors.seo_title?.message}>
            <Input {...fieldAria("strategy-seo-title", errors.seo_title?.message)} {...form.register("seo_title")} />
          </FormField>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField id="strategy-keyword" label="Primary keyword" error={errors.primary_keyword?.message}>
              <Input {...fieldAria("strategy-keyword", errors.primary_keyword?.message)} {...form.register("primary_keyword")} />
            </FormField>
            <FormField id="strategy-intent" label="Search intent">
              <Controller
                control={form.control}
                name="search_intent"
                render={({ field }) => (
                  <SimpleSelect
                    id="strategy-intent"
                    aria-label="Search intent"
                    value={(field.value || undefined) as SearchIntent | undefined}
                    onChange={field.onChange}
                    options={INTENT_OPTIONS}
                    placeholder="Choose an intent"
                  />
                )}
              />
            </FormField>
          </div>
          <FormField
            id="strategy-keywords"
            label="Secondary keywords"
            hint="Comma-separated."
            error={errors.secondary_keywords?.message}
          >
            <Input {...fieldAria("strategy-keywords", errors.secondary_keywords?.message)} {...form.register("secondary_keywords")} />
          </FormField>
          <FormField id="strategy-outline" label="Outline" hint="One section heading per line." error={errors.outline?.message}>
            <Textarea {...fieldAria("strategy-outline", errors.outline?.message)} rows={5} {...form.register("outline")} />
          </FormField>
          <div className="grid gap-4 sm:grid-cols-[10rem_1fr]">
            <FormField id="strategy-words" label="Target words" error={errors.target_word_count?.message}>
              <Input
                {...fieldAria("strategy-words", errors.target_word_count?.message)}
                inputMode="numeric"
                placeholder="1500"
                {...form.register("target_word_count")}
              />
            </FormField>
            <FormField
              id="strategy-featured"
              label="Featured image direction"
              error={errors.featured_image_direction?.message}
            >
              <Input
                {...fieldAria("strategy-featured", errors.featured_image_direction?.message)}
                {...form.register("featured_image_direction")}
              />
            </FormField>
          </div>
        </fieldset>
      )}

      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        {canGenerate && !hasPost ? (
          <>
            <Button type="button" variant="outline" disabled={saving} onClick={submitWith(false)}>
              {editing ? "Save changes" : "Save plan"}
            </Button>
            <Button type="submit" disabled={saving}>
              <SparklesIcon />
              {generate.isPending ? "Starting…" : saving ? "Saving…" : isBlog ? "Save & write article" : "Save & write post"}
            </Button>
          </>
        ) : (
          <Button type="submit" disabled={saving}>
            {saving ? "Saving…" : editing ? "Save changes" : "Save plan"}
          </Button>
        )}
      </DialogFooter>
    </form>
  );
}
