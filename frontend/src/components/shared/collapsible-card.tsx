"use client";

import { ChevronDownIcon } from "lucide-react";
import { useId, useState } from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * A card whose body opens from its header (title, description and a chevron),
 * for supporting detail that would otherwise push the main content down.
 * Closed by default; `count` is shown after the title.
 */
export function CollapsibleCard({
  title,
  description,
  count,
  defaultOpen = false,
  contentClassName,
  children,
}: {
  title: string;
  description?: React.ReactNode;
  count?: number;
  defaultOpen?: boolean;
  contentClassName?: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const contentId = useId();
  return (
    <Card>
      <CardHeader>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={contentId}
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-start gap-2 rounded-sm text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <span className="grid flex-1 gap-1">
            <CardTitle>
              {title}
              {count !== undefined && ` (${count})`}
            </CardTitle>
            {description && <CardDescription>{description}</CardDescription>}
          </span>
          <ChevronDownIcon
            aria-hidden
            className={cn(
              "mt-1 size-4 shrink-0 text-muted-foreground transition-transform",
              open && "rotate-180",
            )}
          />
        </button>
      </CardHeader>
      {open && (
        <CardContent id={contentId} className={contentClassName}>
          {children}
        </CardContent>
      )}
    </Card>
  );
}
