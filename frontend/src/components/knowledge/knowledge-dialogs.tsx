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
import { useCreateDocument, useStartCrawl, useUpdateDocument } from "@/hooks/use-knowledge";
import { errorMessage } from "@/lib/api";
import type { KnowledgeDocumentDetail } from "@/types/api";

const crawlSchema = z.object({
  url: z
    .string()
    .trim()
    .regex(/^https?:\/\/\S+\.\S+/i, "Enter a full URL, e.g. https://example.com"),
  max_pages: z.coerce.number().int().min(1, "At least 1 page.").max(300, "At most 300 pages."),
});

export function CrawlDialog({
  open,
  onClose,
  websiteUrl,
}: {
  open: boolean;
  onClose: () => void;
  websiteUrl: string | null;
}) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        {open && <CrawlForm websiteUrl={websiteUrl} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

function CrawlForm({ websiteUrl, onClose }: { websiteUrl: string | null; onClose: () => void }) {
  const start = useStartCrawl();
  const form = useForm<z.input<typeof crawlSchema>, unknown, z.output<typeof crawlSchema>>({
    resolver: zodResolver(crawlSchema),
    defaultValues: { url: websiteUrl ?? "", max_pages: 50 },
  });
  const { errors } = form.formState;

  return (
    <form
      noValidate
      className="grid gap-5"
      onSubmit={form.handleSubmit((values) =>
        start.mutate(values, {
          onSuccess: () => {
            toast.success("Crawl started. You can keep working; it runs in the background.");
            onClose();
          },
        }),
      )}
    >
      <DialogHeader>
        <DialogTitle>Crawl your website</DialogTitle>
        <DialogDescription>
          ContentPulse reads your pages, keeps the meaningful text and skips navigation, footers and
          anything robots.txt asks it not to read. Unchanged pages are skipped on later crawls.
        </DialogDescription>
      </DialogHeader>
      {start.isError && (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(start.error)}</AlertDescription>
        </Alert>
      )}
      <FormField id="crawl-url" label="Website" error={errors.url?.message}>
        <Input {...fieldAria("crawl-url", errors.url?.message)} type="url" {...form.register("url")} />
      </FormField>
      <FormField
        id="crawl-max"
        label="Page limit"
        hint="Most important pages (shallowest URLs) are read first."
        error={errors.max_pages?.message}
        className="max-w-40"
      >
        <Input
          {...fieldAria("crawl-max", errors.max_pages?.message)}
          type="number"
          inputMode="numeric"
          min={1}
          max={300}
          {...form.register("max_pages")}
        />
      </FormField>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" disabled={start.isPending}>
          {start.isPending ? "Starting…" : "Start crawl"}
        </Button>
      </DialogFooter>
    </form>
  );
}

const documentSchema = z.object({
  title: z.string().trim().min(1, "Give it a title.").max(200),
  content: z.string().trim().min(1, "Add some content.").max(100_000, "Keep it under 100,000 characters."),
});
type DocumentValues = z.infer<typeof documentSchema>;

export function DocumentDialog({
  open,
  editing,
  onClose,
}: {
  open: boolean;
  editing: KnowledgeDocumentDetail | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        {open && <DocumentForm key={editing?.id ?? "new"} editing={editing} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

function DocumentForm({ editing, onClose }: { editing: KnowledgeDocumentDetail | null; onClose: () => void }) {
  const create = useCreateDocument();
  const update = useUpdateDocument();
  const pending = create.isPending || update.isPending;
  const error = create.error ?? update.error;
  const form = useForm<DocumentValues>({
    resolver: zodResolver(documentSchema),
    defaultValues: { title: editing?.title ?? "", content: editing?.content ?? "" },
  });
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit((values) => {
    const options = {
      onSuccess: () => {
        toast.success(editing ? "Document updated" : "Document added to knowledge");
        onClose();
      },
    };
    if (editing) update.mutate({ id: editing.id, ...values }, options);
    else create.mutate(values, options);
  });

  return (
    <form noValidate onSubmit={onSubmit} className="grid gap-5">
      <DialogHeader>
        <DialogTitle>{editing ? "Edit document" : "Add a document"}</DialogTitle>
        <DialogDescription>
          For knowledge that isn&apos;t on your website: positioning notes, case studies, service
          details. Use &ldquo;## Heading&rdquo; lines to split it into sections.
        </DialogDescription>
      </DialogHeader>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(error)}</AlertDescription>
        </Alert>
      )}
      <FormField id="doc-title" label="Title" error={errors.title?.message}>
        <Input {...fieldAria("doc-title", errors.title?.message)} autoFocus {...form.register("title")} />
      </FormField>
      <FormField id="doc-content" label="Content" error={errors.content?.message}>
        <Textarea
          {...fieldAria("doc-content", errors.content?.message)}
          rows={14}
          className="font-mono text-xs"
          placeholder={"## Who we serve\n\nMid-size logistics companies…"}
          {...form.register("content")}
        />
      </FormField>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" disabled={pending}>
          {pending ? "Saving…" : editing ? "Save" : "Add document"}
        </Button>
      </DialogFooter>
    </form>
  );
}
