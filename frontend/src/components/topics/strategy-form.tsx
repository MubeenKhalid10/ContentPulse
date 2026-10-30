"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { LoaderCircleIcon, SparklesIcon, WandSparklesIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Controller, useForm, useWatch, type FieldErrors } from "react-hook-form";
import { toast } from "sonner";

import { fieldAria, FormField } from "@/components/shared/form-field";
import { SimpleSelect } from "@/components/shared/simple-select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateStrategy,
  usePlatformRules,
  useSuggestStrategy,
  useUpdateStrategy,
} from "@/hooks/use-topics";
import { useGeneratePost, useTopicPosts } from "@/hooks/use-content";
import { useOrgSettings } from "@/hooks/use-organization";
import { useAIStatus } from "@/hooks/use-trends";
import { ApiError, errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { stripCitations } from "@/lib/format";
import { PLATFORM_LABEL } from "@/lib/topics";
import type { ContentAngle, Platform, SearchIntent, Strategy, TopicDetail } from "@/types/api";

import {
  INTENT_OPTIONS,
  schema,
  type Values,
  AUTO_POST_TYPE,
  toValues,
  toBody,
} from "./strategy-form-model";

export function StrategyForm({
  topic,
  initialPlatform,
  editing,
  angle,
  onClose,
}: {
  topic: TopicDetail;
  initialPlatform: Platform;
  editing: Strategy | null;
  angle: ContentAngle | null;
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
  // Multi-platform save is several requests. What already went through is kept
  // here so a retry after a failure doesn't create the same plans or posts twice.
  const [progress] = useState(() => ({
    plans: {} as Partial<Record<Platform, Strategy>>,
    written: new Set<string>(),
  }));
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: toValues(
      initialPlatform,
      editing ?? (angle ? { content_angle: `${angle.title}: ${stripCitations(angle.angle)}` } : undefined),
      topic.target_audience,
    ),
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
  const [selected, setSelected] = useState<Platform[]>([initialPlatform]);
  const multi = !editing && selected.length > 1;
  const allSelected = platforms.every((p) => selected.includes(p));
  // With several platforms, each keeps its own AI/playbook draft; the form edits the active one.
  const [drafts, setDrafts] = useState<Partial<Record<Platform, Values>>>({});
  const hasDrafts = multi && Object.keys(drafts).length > 0;
  const isBlog = platform === "blog" && (!multi || hasDrafts);
  const notEnabled = (Object.keys(PLATFORM_LABEL) as Platform[]).filter((p) => !platforms.includes(p));
  const postTypes = [...new Set([...(rule?.post_types ?? []), ...(postType && !rule ? [postType] : [])])];
  const objectives = [...new Set([...(rule?.objectives ?? []), ...(objective ? [objective] : [])])];
  const generate = useGeneratePost();
  const router = useRouter();
  const canGenerate = useCan()("content.generate");
  const topicPosts = useTopicPosts(topic.id);
  // Editing a plan that already has its post: just save.
  const hasPost = !!editing && (topicPosts.data?.items ?? []).some((p) => p.content_strategy_id === editing.id);
  const saving = create.isPending || update.isPending || generate.isPending;
  // Which footer button started the save, so only that one spins.
  const [writing, setWriting] = useState(false);
  const failure = create.error ?? update.error;

  const select = (next: Platform[]) => {
    if (!next.length) return;
    const ordered = platforms.filter((p) => next.includes(p));
    const kept = Object.fromEntries(
      Object.entries(drafts).filter(([p]) => ordered.includes(p as Platform)),
    ) as Partial<Record<Platform, Values>>;
    if (ordered.includes(platform)) kept[platform] = form.getValues();
    setSelected(ordered);
    setDrafts(kept);
    if (ordered.length > 1 && ordered.includes(platform)) return;
    setNotice(null);
    const first = ordered[0];
    if (ordered.length > 1 && kept[first]) {
      form.reset(kept[first]);
      return;
    }
    form.setValue("platform", first);
    form.setValue("post_type", ordered.length > 1 ? AUTO_POST_TYPE : "");
    if (ordered.length > 1) form.setValue("objective", "");
  };
  const viewDraft = (p: Platform) => {
    const saved = { ...drafts, [platform]: form.getValues() };
    setDrafts(saved);
    form.reset(saved[p] ?? { ...form.getValues(), platform: p, post_type: AUTO_POST_TYPE, objective: "" });
  };
  const toggle = (p: Platform) => select(selected.includes(p) ? selected.filter((x) => x !== p) : [...selected, p]);
  const toggleAll = () => select(allSelected ? [platforms[0]] : platforms);

  const runSuggestAll = async () => {
    try {
      const results = await Promise.all(
        selected.map(async (p) => [p, await suggest.mutateAsync({ topicId: topic.id, platform: p })] as const),
      );
      const next: Partial<Record<Platform, Values>> = {};
      // Post type is hidden with several platforms; an empty one falls back to the platform default.
      for (const [p, draft] of results) next[p] = { ...toValues(p, draft), post_type: draft.post_type || AUTO_POST_TYPE };
      setDrafts(next);
      form.reset(next[selected[0]]);
      setSource(results[0][1].source);
      setNotice(results.find(([, d]) => d.notice)?.[1].notice ?? null);
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

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

  // A failed check is otherwise only shown next to its field, which may be scrolled out of
  // view (or hidden, like Post type with several platforms), so the button seemed to do nothing.
  const onInvalid = (invalid: FieldErrors<Values>) => {
    const [field, error] = Object.entries(invalid)[0] ?? [];
    if (!field) return;
    toast.error(error?.message ?? "Check the highlighted fields.");
    document.querySelector<HTMLElement>(`[name="${field}"], #strategy-${field.replace("_", "-")}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  };

  // "Write post": save the plan, then write the post from it right away.
  const submitWith = (write: boolean) => form.handleSubmit(async (values) => {
    setWriting(write);
    if (multi) {
      const saved: Strategy[] = [];
      const all = { ...drafts, [platform]: values };
      let failed: Platform | null = null;
      // Only the draft on screen went through the form's checks; check the others too and
      // open the first one that fails, instead of sending it and getting a bare 422.
      for (const p of selected) {
        const draft = all[p];
        if (!draft || progress.plans[p]) continue;
        const check = schema.safeParse({ ...draft, post_type: draft.post_type || AUTO_POST_TYPE });
        if (check.success) continue;
        const issue = check.error.issues[0];
        if (p !== platform) viewDraft(p);
        form.setError(issue.path[0] as keyof Values, { message: issue.message });
        toast.error(`${PLATFORM_LABEL[p]}: ${issue.message}`);
        return;
      }
      try {
        for (const p of selected) {
          failed = p;
          let plan = progress.plans[p];
          if (!plan) {
            const defaultType = rules.data?.find((r) => r.platform === p)?.post_types[0] ?? "Post";
            const draft = all[p];
            const v: Values = draft
              ? { ...draft, platform: p, post_type: !draft.post_type || draft.post_type === AUTO_POST_TYPE ? defaultType : draft.post_type }
              : { ...values, platform: p, post_type: defaultType, objective: "" };
            plan = await create.mutateAsync({ topicId: topic.id, source, ...toBody(v) });
            progress.plans[p] = plan;
          }
          saved.push(plan);
        }
        if (write && canGenerate) {
          for (const strategy of saved) {
            failed = strategy.platform;
            if (progress.written.has(strategy.id)) continue;
            await generate.mutateAsync(strategy.id);
            progress.written.add(strategy.id);
          }
          toast.success(`Writing ${saved.length} posts`);
          onClose();
          router.push("/content");
          return;
        }
        toast.success(`${saved.length} plans saved`);
        onClose();
      } catch (e) {
        const plans = Object.keys(progress.plans).length;
        const posts = progress.written.size;
        toast.error(
          `${failed ? `${PLATFORM_LABEL[failed]} failed: ` : ""}${errorMessage(e)}`,
          {
            description: plans
              ? `${plans} of ${selected.length} plans saved${posts ? `, ${posts} ${posts === 1 ? "post" : "posts"} started` : ""}. Try again to finish the rest; saved items won't be repeated.`
              : undefined,
          },
        );
      }
      return;
    }
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
        toast.error(errorMessage(error));
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
  }, onInvalid);

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
        {!editing ? (
          <fieldset className="grid gap-2">
            <legend className="mb-1 text-sm font-medium">Platforms</legend>
            <div className="flex flex-wrap gap-x-5 gap-y-2">
              <label className="flex items-center gap-2 text-sm font-medium">
                <input type="checkbox" className="size-4 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2" checked={allSelected} onChange={toggleAll} />
                All platforms
              </label>
              {platforms.map((p) => (
                <label key={p} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" className="size-4 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2" checked={selected.includes(p)} onChange={() => toggle(p)} />
                  {PLATFORM_LABEL[p]}
                </label>
              ))}
            </div>
          </fieldset>
        ) : (
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
        )}
        <Button type="button" variant="outline" onClick={multi ? runSuggestAll : runSuggest} disabled={suggest.isPending} pending={suggest.isPending}>
          {ai.data?.engine === "ai" ? <SparklesIcon /> : <WandSparklesIcon />}
          {suggest.isPending
            ? "Drafting…"
            : ai.data?.engine === "ai"
              ? "Draft Plan with AI"
              : "Draft Plan from playbook"}
        </Button>
        <p className="basis-full text-xs text-muted-foreground">
          Drafting replaces what you&apos;ve entered below.
        </p>
      </div>

      {notEnabled.length > 0 && (
        <p className="-mt-2 text-xs text-muted-foreground">
          {notEnabled.map((p) => PLATFORM_LABEL[p]).join(", ")} {notEnabled.length === 1 ? "isn't" : "aren't"} enabled
          for your organization.{" "}
          <Link href="/organization/content-setup#platforms" className="underline underline-offset-4">
            Turn on platforms in Audience & platforms
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

      {multi && (
        <p className="-mt-2 text-xs text-muted-foreground">
          {hasDrafts
            ? "Each platform keeps its own draft. Switch below to review or edit one."
            : `One plan is created for each of the ${selected.length} platforms from the details below. Use Draft to get a tailored plan for each, or save as-is with each platform's default post type.`}
        </p>
      )}
      {hasDrafts && (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Platform drafts">
          {selected.map((p) => (
            <Button
              key={p}
              type="button"
              size="sm"
              aria-pressed={p === platform}
              variant={p === platform ? "default" : "outline"}
              onClick={() => p !== platform && viewDraft(p)}
            >
              {PLATFORM_LABEL[p]}
            </Button>
          ))}
        </div>
      )}
      {!multi && <div className="grid gap-4 sm:grid-cols-2">
        <FormField id="strategy-post-type" label="Post type (required)" error={errors.post_type?.message}>
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
      </div>}

      <FormField id="strategy-angle" label="Post idea (required)" hint="The main point or story this post tells." error={errors.content_angle?.message}>
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
            <FormField id="strategy-keyword" label="Primary keyword" hint="The main phrase people search for." error={errors.primary_keyword?.message}>
              <Input {...fieldAria("strategy-keyword", errors.primary_keyword?.message)} {...form.register("primary_keyword")} />
            </FormField>
            <FormField id="strategy-intent" label="Search intent" hint="What the reader wants when they search it.">
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
            <FormField id="strategy-words" label="Target words" hint="Typically 800 to 2,500." error={errors.target_word_count?.message}>
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
            <Button type="button" variant="outline" disabled={saving} pending={saving && !writing} onClick={submitWith(false)}>
              {editing ? "Save changes" : multi ? "Save Plan Drafts" : "Save Plan Draft"}
            </Button>
            <Button type="submit" disabled={saving} pending={saving && writing}>
              <SparklesIcon />
              {generate.isPending ? "Starting…" : saving ? "Saving…" : multi ? `Write ${selected.length} posts` : isBlog ? "Write article" : "Write post"}
            </Button>
          </>
        ) : (
          <Button type="submit" disabled={saving}>
            {saving && <LoaderCircleIcon className="animate-spin" />}
            {saving ? "Saving…" : editing ? "Save changes" : "Save Plan Draft"}
          </Button>
        )}
      </DialogFooter>
    </form>
  );
}
