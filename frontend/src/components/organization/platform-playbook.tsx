"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { RotateCcwIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { FormSkeleton } from "@/components/shared/form-skeleton";
import { fieldAria, FormField } from "@/components/shared/form-field";
import { PageHeader, ReadOnlyNotice } from "@/components/shared/page-header";
import { TagInput } from "@/components/shared/tag-input";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useOrgSettings } from "@/hooks/use-organization";
import {
  usePlatformRules,
  useResetPlatformRule,
  useUpdatePlatformRule,
} from "@/hooks/use-topics";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { PLATFORM_DOT, PLATFORM_TAB_ACTIVE } from "@/lib/tones";
import { PLATFORM_LABEL } from "@/lib/topics";
import { cn } from "@/lib/utils";
import type { Platform, PlatformRule } from "@/types/api";

const optionalInt = (max: number) =>
  z
    .union([
      z.literal(""),
      z.coerce
        .number()
        .int()
        .min(0, "Must be 0 or more.")
        .max(max, `At most ${max}.`),
    ])
    .transform((v) => (v === "" ? null : v));

const schema = z.object({
  post_types: z.array(z.string()).min(1, "Keep at least one post type."),
  objectives: z.array(z.string()),
  affinity_keywords: z.array(z.string()),
  tone: z.string().trim().max(200),
  guidance: z.string().trim().max(2000),
  max_length: optionalInt(100_000),
  hashtag_limit: optionalInt(60),
});
type Input = z.input<typeof schema>;
type Output = z.output<typeof schema>;

export function PlatformPlaybook() {
  const rules = usePlatformRules();
  const settings = useOrgSettings();
  const canEdit = useCan()("organization.write");
  const [platform, setPlatform] = useState<Platform>("linkedin");
  const rule = rules.data?.find((r) => r.platform === platform);
  const enabled = settings.data?.enabled_platforms ?? [];

  return (
    <>
      <PageHeader
        title="Platform playbook"
        description="Your rules for each platform, from social posts to blog articles: post types, tone and length. Plans and posts follow them."
      />
      {!canEdit && <ReadOnlyNotice />}
      <div className="grid gap-6">
        <Tabs
          value={platform}
          onValueChange={(v) => setPlatform(v as Platform)}
        >
          <TabsList>
            {(Object.keys(PLATFORM_LABEL) as Platform[]).map((p) => (
              <TabsTrigger
                key={p}
                value={p}
                className={cn(
                  "px-2.5 data-active:shadow-none data-active:ring-1 data-active:ring-inset dark:data-active:border-transparent",
                  PLATFORM_TAB_ACTIVE[p],
                )}
              >
                <span
                  aria-hidden
                  className={cn(
                    "size-1.5 rounded-full",
                    PLATFORM_DOT[p],
                    p === "x" &&
                      "in-data-active:bg-white dark:in-data-active:bg-zinc-900",
                  )}
                />
                {PLATFORM_LABEL[p]}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        {rule ? (
          <RuleForm
            key={`${rule.platform}:${rule.updated_at}`}
            rule={rule}
            canEdit={canEdit}
            enabled={!enabled.length || enabled.includes(rule.platform)}
          />
        ) : (
          <FormSkeleton fields={5} />
        )}
      </div>
    </>
  );
}

function RuleForm({
  rule,
  canEdit,
  enabled,
}: {
  rule: PlatformRule;
  canEdit: boolean;
  enabled: boolean;
}) {
  const update = useUpdatePlatformRule();
  const reset = useResetPlatformRule();
  const [confirmReset, setConfirmReset] = useState(false);
  const label = PLATFORM_LABEL[rule.platform];
  const form = useForm<Input, unknown, Output>({
    resolver: zodResolver(schema),
    defaultValues: {
      post_types: rule.post_types,
      objectives: rule.objectives,
      affinity_keywords: rule.affinity_keywords,
      tone: rule.tone ?? "",
      guidance: rule.guidance ?? "",
      max_length: rule.max_length ?? "",
      hashtag_limit: rule.hashtag_limit ?? "",
    },
  });
  const { errors, isDirty } = form.formState;

  const list = (
    name: "post_types" | "objectives" | "affinity_keywords",
    title: string,
    hint: string,
    placeholder: string,
  ) => (
    <FormField
      id={`${rule.platform}-${name}`}
      label={title}
      hint={hint}
      error={errors[name]?.message}
    >
      <Controller
        control={form.control}
        name={name}
        render={({ field }) => (
          <TagInput
            id={`${rule.platform}-${name}`}
            value={field.value}
            onChange={field.onChange}
            placeholder={placeholder}
            disabled={!canEdit}
          />
        )}
      />
    </FormField>
  );

  return (
    <form
      noValidate
      aria-label={`${label} playbook`}
      onSubmit={form.handleSubmit((values) =>
        update.mutate(
          {
            platform: rule.platform,
            ...values,
            tone: values.tone || null,
            guidance: values.guidance || null,
          },
          {
            onSuccess: () => toast.success(`${label} playbook saved`),
            onError: (e) => toast.error(errorMessage(e)),
          },
        ),
      )}
    >
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-start gap-2">
          <div className="grid flex-1 gap-1">
            <CardTitle className="flex items-center gap-2">
              {label}
              {!enabled && (
                <Badge variant="outline">Not one of your platforms</Badge>
              )}
            </CardTitle>
            <CardDescription>
              {enabled ? (
                "Used when topics are scored for this platform and post plans are drafted."
              ) : (
                <>
                  Topics aren&apos;t recommended for {label} until you enable it
                  in{" "}
                  <Link
                    href="/organization/content-setup#platforms"
                    className="underline underline-offset-4"
                  >
                    Content setup
                  </Link>
                  .
                </>
              )}
            </CardDescription>
          </div>
          {canEdit && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={reset.isPending}
              onClick={() => setConfirmReset(true)}
            >
              <RotateCcwIcon />
              Reset to defaults
            </Button>
          )}
          <AlertDialog open={confirmReset} onOpenChange={setConfirmReset}>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Reset the {label} playbook?</AlertDialogTitle>
                <AlertDialogDescription>
                  Your post types, tone, limits and guidance for {label} are
                  replaced by the defaults.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  variant="destructive"
                  disabled={reset.isPending}
                  onClick={() =>
                    reset.mutate(rule.platform, {
                      onSuccess: () => {
                        toast.success(`${label} playbook reset to defaults`);
                        setConfirmReset(false);
                      },
                      onError: (e) => toast.error(errorMessage(e)),
                    })
                  }
                >
                  Reset
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </CardHeader>
        <CardContent>
          <fieldset disabled={!canEdit} className="grid gap-5">
            {list(
              "post_types",
              "Post types",
              "Offered when planning a post, most preferred first.",
              "e.g. Carousel",
            )}
            {list(
              "objectives",
              "Objectives",
              "What posts on this platform are for.",
              "e.g. Thought leadership",
            )}
            {list(
              "affinity_keywords",
              "Audience signals",
              "Words in your audience, goals or a topic that make this platform a good fit.",
              "e.g. decision makers",
            )}
            <div className="grid gap-5 sm:grid-cols-[1fr_9rem_9rem]">
              <FormField
                id={`${rule.platform}-tone`}
                label="Tone"
                error={errors.tone?.message}
              >
                <Input
                  {...fieldAria(`${rule.platform}-tone`, errors.tone?.message)}
                  {...form.register("tone")}
                />
              </FormField>
              <FormField
                id={`${rule.platform}-max`}
                label="Max characters"
                error={errors.max_length?.message}
              >
                <Input
                  {...fieldAria(
                    `${rule.platform}-max`,
                    errors.max_length?.message,
                  )}
                  type="number"
                  inputMode="numeric"
                  min={1}
                  {...form.register("max_length")}
                />
              </FormField>
              <FormField
                id={`${rule.platform}-hashtags`}
                label="Max hashtags"
                error={errors.hashtag_limit?.message}
              >
                <Input
                  {...fieldAria(
                    `${rule.platform}-hashtags`,
                    errors.hashtag_limit?.message,
                  )}
                  type="number"
                  inputMode="numeric"
                  min={0}
                  {...form.register("hashtag_limit")}
                />
              </FormField>
            </div>
            <FormField
              id={`${rule.platform}-guidance`}
              label="Guidance"
              hint="Shared with the AI and your writers."
              error={errors.guidance?.message}
            >
              <Textarea
                {...fieldAria(
                  `${rule.platform}-guidance`,
                  errors.guidance?.message,
                )}
                rows={3}
                {...form.register("guidance")}
              />
            </FormField>
            {canEdit && (
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  disabled={!isDirty}
                  onClick={() => form.reset()}
                >
                  Discard changes
                </Button>
                <Button type="submit" disabled={!isDirty || update.isPending}>
                  {update.isPending ? "Saving…" : "Save playbook"}
                </Button>
              </div>
            )}
          </fieldset>
        </CardContent>
      </Card>
    </form>
  );
}
