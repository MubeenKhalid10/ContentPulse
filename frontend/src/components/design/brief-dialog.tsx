"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { fieldAria, FormField } from "@/components/shared/form-field";
import { SimpleSelect } from "@/components/shared/simple-select";
import { TagInput } from "@/components/shared/tag-input";
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
import { useUpdateBrief } from "@/hooks/use-design";
import { errorMessage } from "@/lib/api";
import { DESIGN_FORMAT_OPTIONS } from "@/lib/content";
import type { DesignFormat, DesignTaskDetail } from "@/types/api";

const schema = z.object({
  format: z.string().min(1),
  dimensions: z.string().trim().max(40),
  headline: z.string().trim().max(4000),
  supporting_text: z.string().trim().max(4000),
  visual_concept: z.string().trim().max(4000),
  slides: z.string().max(6000),
  visual_elements: z.array(z.string()),
  cta: z.string().trim().max(4000),
  designer_notes: z.string().trim().max(4000),
});
type Values = z.infer<typeof schema>;

export function BriefDialog({ task, open, onClose }: { task: DesignTaskDetail; open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        {open && <BriefForm task={task} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

function BriefForm({ task, onClose }: { task: DesignTaskDetail; onClose: () => void }) {
  const update = useUpdateBrief();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      format: task.format,
      dimensions: task.dimensions ?? "",
      headline: task.headline ?? "",
      supporting_text: task.supporting_text ?? "",
      visual_concept: task.visual_concept ?? "",
      slides: task.slide_structure.join("\n"),
      visual_elements: task.visual_elements,
      cta: task.cta ?? "",
      designer_notes: task.designer_notes ?? "",
    },
  });
  const { errors } = form.formState;
  const text = (name: Exclude<keyof Values, "format" | "visual_elements" | "slides" | "dimensions">, label: string, rows = 2, hint?: string) => (
    <FormField id={`brief-${name}`} label={label} hint={hint} error={errors[name]?.message}>
      <Textarea {...fieldAria(`brief-${name}`, errors[name]?.message)} rows={rows} {...form.register(name)} />
    </FormField>
  );

  return (
    <form
      noValidate
      className="grid gap-5"
      onSubmit={form.handleSubmit((v) =>
        update.mutate(
          {
            id: task.id,
            format: v.format as DesignFormat,
            dimensions: v.dimensions || null,
            headline: v.headline || null,
            supporting_text: v.supporting_text || null,
            visual_concept: v.visual_concept || null,
            slide_structure: v.slides
              .split("\n")
              .map((s) => s.trim())
              .filter(Boolean),
            visual_elements: v.visual_elements,
            cta: v.cta || null,
            designer_notes: v.designer_notes || null,
          },
          {
            onSuccess: () => {
              toast.success("Brief updated");
              onClose();
            },
          },
        ),
      )}
    >
      <DialogHeader>
        <DialogTitle>Edit design brief</DialogTitle>
        <DialogDescription>
          Brand colors, typography and logo rules come from your Brand settings and are always attached.
        </DialogDescription>
      </DialogHeader>
      {update.isError && (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(update.error)}</AlertDescription>
        </Alert>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField id="brief-format" label="Format">
          <Controller
            control={form.control}
            name="format"
            render={({ field }) => (
              <SimpleSelect id="brief-format" aria-label="Format" value={field.value} onChange={field.onChange} options={DESIGN_FORMAT_OPTIONS} />
            )}
          />
        </FormField>
        <FormField id="brief-dimensions" label="Dimensions" error={errors.dimensions?.message}>
          <Input {...fieldAria("brief-dimensions", errors.dimensions?.message)} placeholder="1080×1350 (4:5)" {...form.register("dimensions")} />
        </FormField>
      </div>
      {text("headline", "Headline")}
      {text("supporting_text", "Supporting text")}
      {text("visual_concept", "Visual concept", 3)}
      <FormField id="brief-slides" label="Slides or shots" hint="One per line." error={errors.slides?.message}>
        <Textarea {...fieldAria("brief-slides", errors.slides?.message)} rows={5} {...form.register("slides")} />
      </FormField>
      <FormField id="brief-elements" label="Visual elements">
        <Controller
          control={form.control}
          name="visual_elements"
          render={({ field }) => (
            <TagInput id="brief-elements" value={field.value} onChange={field.onChange} placeholder="e.g. Bar chart" maxLength={300} />
          )}
        />
      </FormField>
      {text("cta", "Call to action")}
      {text("designer_notes", "Notes for the designer", 3)}
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" disabled={update.isPending}>
          {update.isPending ? "Saving…" : "Save brief"}
        </Button>
      </DialogFooter>
    </form>
  );
}
