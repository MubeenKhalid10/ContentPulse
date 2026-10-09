"use client";

import { useState } from "react";
import { toast } from "sonner";

import { TagInput } from "@/components/shared/tag-input";
import { Button } from "@/components/ui/button";
import { useOrgSettings, useUpdateSettings } from "@/hooks/use-organization";
import { errorMessage } from "@/lib/api";
import { settingsSchema } from "@/schemas/organization";

type ListField = "subreddits" | "rss_feeds";

const COPY: Record<
  ListField,
  { label: string; hint: string; placeholder: string; saved: string }
> = {
  subreddits: {
    label: "Subreddits to follow",
    hint: "Communities your audience reads. Without any, r/popular is used.",
    placeholder: "e.g. r/automation",
    saved: "Subreddits saved",
  },
  rss_feeds: {
    label: "RSS feeds",
    hint: "Industry blogs and trade publications (RSS or Atom URLs).",
    placeholder: "https://example.com/feed",
    saved: "RSS feeds saved",
  },
};

/**
 * A source's own list (Reddit's subreddits, RSS's feeds), edited right on its
 * card in Trends › Sources and saved to the organization's settings.
 */
export function SourceListEditor({
  field,
  canEdit,
}: {
  field: ListField;
  canEdit: boolean;
}) {
  const settings = useOrgSettings();
  if (!settings.data) return null;
  return (
    <ListForm
      key={settings.data.updated_at}
      field={field}
      initial={settings.data[field]}
      canEdit={canEdit}
    />
  );
}

function ListForm({
  field,
  initial,
  canEdit,
}: {
  field: ListField;
  initial: string[];
  canEdit: boolean;
}) {
  const copy = COPY[field];
  const update = useUpdateSettings();
  const [value, setValue] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const dirty = value.join("\n") !== initial.join("\n");
  const id = `source-${field}`;

  function save() {
    const parsed = settingsSchema.shape[field].safeParse(value);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Check the entries.");
      return;
    }
    setError(null);
    update.mutate(
      { [field]: parsed.data },
      {
        onSuccess: () => toast.success(copy.saved),
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  }

  return (
    <div className="grid gap-1.5 rounded-lg border bg-muted/30 p-3">
      <label htmlFor={id} className="text-sm font-medium">
        {copy.label}
      </label>
      <TagInput
        id={id}
        value={value}
        onChange={(next) => {
          setValue(next);
          setError(null);
        }}
        placeholder={copy.placeholder}
        disabled={!canEdit}
        maxLength={field === "rss_feeds" ? 2048 : undefined}
      />
      {error ? (
        <p className="text-xs text-destructive" role="alert">
          {error}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">{copy.hint}</p>
      )}
      {canEdit && dirty && (
        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setValue(initial)}
          >
            Discard
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={update.isPending}
            onClick={save}
          >
            {update.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      )}
    </div>
  );
}
