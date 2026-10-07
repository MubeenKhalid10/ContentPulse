"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { FormSkeleton, SaveBar } from "@/components/shared/form-skeleton";
import { fieldAria, FormField } from "@/components/shared/form-field";
import { PageHeader, ReadOnlyNotice } from "@/components/shared/page-header";
import { TagInput } from "@/components/shared/tag-input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useBrand, useUpdateBrand } from "@/hooks/use-organization";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { brandSchema } from "@/schemas/organization";
import type { BrandProfile } from "@/types/api";

type Input = z.input<typeof brandSchema>;
type Output = z.output<typeof brandSchema>;
type TextField = { [K in keyof Input]: Input[K] extends string ? K : never }[keyof Input];
type ListField = { [K in keyof Input]: Input[K] extends string[] ? K : never }[keyof Input];

export function BrandEditor() {
  const brand = useBrand();
  const canEdit = useCan()("organization.write");
  return (
    <>
      <PageHeader
        title="Brand"
        description="How you sound and what you never say. Every generated post follows these rules."
      />
      {!canEdit && <ReadOnlyNotice />}
      {brand.data ? (
        <BrandForm key={brand.data.updated_at} brand={brand.data} canEdit={canEdit} />
      ) : (
        <FormSkeleton fields={6} />
      )}
    </>
  );
}

function BrandForm({ brand, canEdit }: { brand: BrandProfile; canEdit: boolean }) {
  const update = useUpdateBrand();
  const form = useForm<Input, unknown, Output>({
    resolver: zodResolver(brandSchema),
    defaultValues: {
      brand_voice: brand.brand_voice ?? "",
      tone: brand.tone ?? "",
      writing_style: brand.writing_style ?? "",
      preferred_terms: brand.preferred_terms,
      forbidden_terms: brand.forbidden_terms,
      content_guidelines: brand.content_guidelines ?? "",
      cta_guidelines: brand.cta_guidelines ?? "",
      hashtag_guidelines: brand.hashtag_guidelines ?? "",
      brand_colors: brand.brand_colors,
      typography: brand.typography ?? "",
    },
  });
  const { errors, isDirty } = form.formState;

  const text = (name: TextField, label: string, hint: string, rows = 3) => (
    <FormField id={name} label={label} hint={hint} error={errors[name]?.message}>
      <Textarea {...fieldAria(name, errors[name]?.message)} rows={rows} {...form.register(name)} />
    </FormField>
  );

  const list = (name: ListField, label: string, hint: string, placeholder: string) => (
    <FormField id={name} label={label} hint={hint}>
      <Controller
        control={form.control}
        name={name}
        render={({ field }) => (
          <TagInput
            id={name}
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
      onSubmit={form.handleSubmit((values) =>
        update.mutate(values, {
          onSuccess: () => toast.success("Brand profile saved"),
          onError: (e) => toast.error(errorMessage(e)),
        }),
      )}
    >
      <fieldset disabled={!canEdit} className="grid gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Voice</CardTitle>
            <CardDescription>The personality behind every post.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5">
            {text("brand_voice", "Brand voice", "e.g. Expert but approachable. We explain, we don't lecture.")}
            <div className="grid gap-5 sm:grid-cols-2">
              {text("tone", "Tone", "e.g. Confident, optimistic, practical.", 2)}
              {text("writing_style", "Writing style", "e.g. Short sentences, active voice, no jargon.", 2)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Vocabulary</CardTitle>
            <CardDescription>Press Enter after each term.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5 sm:grid-cols-2">
            {list("preferred_terms", "Preferred terms", "Words and phrases to favor.", "e.g. AI automation")}
            {list("forbidden_terms", "Forbidden terms", "Never used in generated content.", "e.g. synergy")}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Guidelines</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-5">
            {text("content_guidelines", "Content guidelines", "Topics to avoid, claims that need care, compliance notes.", 4)}
            <div className="grid gap-5 sm:grid-cols-2">
              {text("cta_guidelines", "Calls to action", "e.g. Point to a consultation, never hard-sell.")}
              {text("hashtag_guidelines", "Hashtags", "e.g. 3–5 per post, always include #YourBrand.")}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Visual identity</CardTitle>
            <CardDescription>Passed to designers in every design brief.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5 sm:grid-cols-2">
            {list("brand_colors", "Brand colors", "Hex codes or names.", "e.g. #0F766E")}
            {text("typography", "Typography", "e.g. Headings in Inter Bold, body in Inter Regular.", 2)}
          </CardContent>
        </Card>
      </fieldset>
      {canEdit && <SaveBar dirty={isDirty} pending={update.isPending} onReset={() => form.reset()} />}
    </form>
  );
}
