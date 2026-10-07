"use client";

import { XIcon } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/utils";

/** Free-form list editor: type and press Enter (or comma) to add. */
export function TagInput({
  id,
  value,
  onChange,
  placeholder,
  disabled,
  maxLength = 120,
}: {
  id: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
  maxLength?: number;
}) {
  const [draft, setDraft] = useState("");

  function commit() {
    const tag = draft.trim().slice(0, maxLength);
    if (tag && !value.some((v) => v.toLowerCase() === tag.toLowerCase())) {
      onChange([...value, tag]);
    }
    setDraft("");
  }

  return (
    <div
      className={cn(
        "flex min-h-8 flex-wrap items-center gap-1.5 rounded-lg border border-input bg-transparent px-2 py-1 text-sm transition-colors focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50 dark:bg-input/30",
        disabled && "pointer-events-none opacity-50",
      )}
    >
      {value.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 rounded-md bg-secondary px-1.5 py-0.5 text-xs text-secondary-foreground"
        >
          {tag}
          <button
            type="button"
            onClick={() => onChange(value.filter((v) => v !== tag))}
            className="rounded-sm text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
            aria-label={`Remove ${tag}`}
          >
            <XIcon className="size-3" />
          </button>
        </span>
      ))}
      <input
        id={id}
        value={draft}
        disabled={disabled}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            commit();
          } else if (e.key === "Backspace" && !draft && value.length) {
            onChange(value.slice(0, -1));
          }
        }}
        onBlur={commit}
        placeholder={value.length ? undefined : placeholder}
        className="min-w-24 flex-1 bg-transparent py-0.5 outline-none placeholder:text-muted-foreground"
      />
    </div>
  );
}
