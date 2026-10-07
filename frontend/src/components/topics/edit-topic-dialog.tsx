"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { fieldAria, FormField } from "@/components/shared/form-field";
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
import { useUpdateTopic } from "@/hooks/use-topics";
import { errorMessage } from "@/lib/api";
import type { TopicDetail } from "@/types/api";

const schema = z.object({
  title: z.string().trim().min(1, "Give the topic a title.").max(300),
  summary: z.string().trim().max(10_000),
  target_audience: z.string().trim().max(2000),
});
type Values = z.infer<typeof schema>;

export function EditTopicDialog({ topic, open, onClose }: { topic: TopicDetail; open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-lg">{open && <EditForm topic={topic} onClose={onClose} />}</DialogContent>
    </Dialog>
  );
}

function EditForm({ topic, onClose }: { topic: TopicDetail; onClose: () => void }) {
  const update = useUpdateTopic();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      title: topic.title,
      summary: topic.summary ?? "",
      target_audience: topic.target_audience ?? "",
    },
  });
  const { errors } = form.formState;

  return (
    <form
      noValidate
      className="grid gap-5"
      onSubmit={form.handleSubmit((v) =>
        update.mutate(
          { id: topic.id, title: v.title, summary: v.summary || null, target_audience: v.target_audience || null },
          {
            onSuccess: () => {
              toast.success("Topic updated");
              onClose();
            },
          },
        ),
      )}
    >
      <DialogHeader>
        <DialogTitle>Edit topic</DialogTitle>
        <DialogDescription>
          Your wording is kept when the trend is re-analyzed. The analysis only updates relevance, angles and
          platform recommendations.
        </DialogDescription>
      </DialogHeader>
      {update.isError && (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(update.error)}</AlertDescription>
        </Alert>
      )}
      <FormField id="topic-title" label="Title" error={errors.title?.message}>
        <Input {...fieldAria("topic-title", errors.title?.message)} {...form.register("title")} />
      </FormField>
      <FormField id="topic-summary" label="Summary" error={errors.summary?.message}>
        <Textarea {...fieldAria("topic-summary", errors.summary?.message)} rows={4} {...form.register("summary")} />
      </FormField>
      <FormField id="topic-audience" label="Target audience" error={errors.target_audience?.message}>
        <Input {...fieldAria("topic-audience", errors.target_audience?.message)} {...form.register("target_audience")} />
      </FormField>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" disabled={update.isPending}>
          {update.isPending ? "Saving…" : "Save"}
        </Button>
      </DialogFooter>
    </form>
  );
}
