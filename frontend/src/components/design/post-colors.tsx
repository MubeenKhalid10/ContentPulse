"use client";

import { PaletteIcon, PlusIcon, RotateCcwIcon, XIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useUpdateBrief } from "@/hooks/use-design";
import { errorMessage } from "@/lib/api";
import type { DesignTaskDetail } from "@/types/api";

const MAX_COLORS = 12;
const HEX = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;

/** #abc -> #aabbcc, for the native colour picker (which only takes 6-digit hex). */
function pickerValue(color: string): string {
  const c = color.trim();
  if (!HEX.test(c)) return "#000000";
  if (c.length === 4)
    return `#${[...c.slice(1)].map((d) => d + d).join("")}`.toLowerCase();
  return c.toLowerCase();
}

function sameColors(a: string[], b: string[]) {
  return (
    a.length === b.length &&
    a.every((c, i) => c.toLowerCase() === b[i]?.toLowerCase())
  );
}

/**
 * The palette for this post: the brand's colours unless someone adjusted them
 * for this design. Changes apply to this post only, never to Brand settings.
 */
export function PostColors({
  task: t,
  canEdit,
}: {
  task: DesignTaskDetail;
  canEdit: boolean;
}) {
  const update = useUpdateBrief();
  const brandColors = t.brand.colors;
  const own = t.brand_requirements.colors?.length
    ? t.brand_requirements.colors
    : null;
  const colors = own ?? brandColors;
  const adjusted = own !== null && !sameColors(own, brandColors);
  const [draft, setDraft] = useState<string[] | null>(null);

  function save(next: string[] | null, message: string) {
    update.mutate(
      { id: t.id, colors: next },
      {
        onSuccess: () => {
          setDraft(null);
          toast.success(message);
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  }

  if (draft) {
    const cleaned = draft.map((c) => c.trim()).filter(Boolean);
    const tooLong = draft.some((c) => c.trim().length > 40);
    return (
      <fieldset className="grid gap-3 rounded-lg border p-3">
        <legend className="px-1 text-sm font-medium">
          Colors for this post
        </legend>
        <p className="text-xs text-muted-foreground">
          Only this post changes. Your Brand settings stay the same.
        </p>
        <ul className="grid gap-2">
          {draft.map((color, i) => (
            <li key={i} className="flex items-center gap-2">
              <input
                type="color"
                aria-label={`Pick color ${i + 1}`}
                value={pickerValue(color)}
                onChange={(e) =>
                  setDraft(
                    draft.map((c, j) =>
                      j === i ? e.target.value.toUpperCase() : c,
                    ),
                  )
                }
                className="size-9 shrink-0 cursor-pointer rounded-md border bg-transparent p-0.5"
              />
              <Input
                aria-label={`Color ${i + 1}`}
                value={color}
                maxLength={40}
                placeholder="#0F766E or a color name"
                onChange={(e) =>
                  setDraft(draft.map((c, j) => (j === i ? e.target.value : c)))
                }
                className="font-mono text-xs"
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`Remove color ${i + 1}`}
                onClick={() => setDraft(draft.filter((_, j) => j !== i))}
              >
                <XIcon />
              </Button>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={draft.length >= MAX_COLORS}
            onClick={() => setDraft([...draft, draft.at(-1) ?? "#000000"])}
          >
            <PlusIcon /> Add color
          </Button>
          {draft.length >= MAX_COLORS && (
            <span className="text-xs text-muted-foreground">
              Up to {MAX_COLORS} colors.
            </span>
          )}
        </div>
        {tooLong && (
          <p className="text-xs text-destructive">
            Keep each color under 40 characters.
          </p>
        )}
        <div className="flex flex-wrap justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setDraft(null)}
          >
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={update.isPending || tooLong}
            onClick={() =>
              save(
                cleaned.length ? cleaned : null,
                "Colors saved for this post",
              )
            }
          >
            {update.isPending ? "Saving…" : "Save colors"}
          </Button>
        </div>
      </fieldset>
    );
  }

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">Colors</span>
        <span className="text-xs text-muted-foreground">
          {adjusted ? "Adjusted for this post" : "From your Brand settings"}
        </span>
        {canEdit && (
          <span className="ml-auto flex gap-1">
            {adjusted && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={update.isPending}
                onClick={() => save(null, "Back to your brand colors")}
              >
                <RotateCcwIcon /> Use brand colors
              </Button>
            )}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setDraft([...colors])}
            >
              <PaletteIcon /> Adjust colors
            </Button>
          </span>
        )}
      </div>
      {colors.length > 0 ? (
        <ul className="flex flex-wrap gap-3" aria-label="Colors for this post">
          {colors.map((c) => (
            <li key={c} className="flex items-center gap-2">
              <span
                className="size-6 rounded-md ring-1 ring-foreground/10"
                style={{ background: c }}
                aria-hidden
              />
              <span className="font-mono text-xs">{c}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">
          No colors yet.
          {canEdit
            ? " Add some for this post, or set them in Brand settings."
            : ""}
        </p>
      )}
    </div>
  );
}
