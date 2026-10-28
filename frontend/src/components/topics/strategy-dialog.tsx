"use client";

import { Dialog, DialogContent } from "@/components/ui/dialog";
import type { ContentAngle, Platform, Strategy, TopicDetail } from "@/types/api";

import { StrategyForm } from "./strategy-form";

export function StrategyDialog({
  topic,
  open,
  platform,
  editing,
  angle = null,
  onClose,
}: {
  topic: TopicDetail;
  open: boolean;
  platform: Platform | null;
  editing: Strategy | null;
  /** A content angle from the analysis to start the plan from. */
  angle?: ContentAngle | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        {open && (
          <StrategyForm
            key={editing?.id ?? `${platform ?? "new"}:${angle?.title ?? ""}`}
            topic={topic}
            initialPlatform={editing?.platform ?? platform ?? topic.recommended_platforms[0] ?? "linkedin"}
            editing={editing}
            angle={angle}
            onClose={onClose}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
