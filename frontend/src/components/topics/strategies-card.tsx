"use client";

import { ClipboardListIcon, PlusIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { Platform, TopicDetail } from "@/types/api";

import { SectionHeader } from "./platform-fit-card";

/** Starts a new plan. Saved plans are listed under Draft posts until a post is written. */
export function StrategiesCard({
  topic,
  canManage,
  onPlan,
}: {
  topic: TopicDetail;
  canManage: boolean;
  onPlan: (platform: Platform | null) => void;
}) {
  const shortlisted = topic.status === "shortlisted";
  return (
    <Card>
      <CardHeader>
        <SectionHeader
          icon={ClipboardListIcon}
          title="Post plans"
          description="Plans waiting to be turned into posts."
          badge="0 plans"
        />
      </CardHeader>
      <CardContent className="grid gap-3">
        {shortlisted ? (
          <div className="grid justify-items-center gap-3 rounded-lg border border-dashed p-5 text-center">
            <p className="text-sm text-muted-foreground">
              Every plan has a post. Review them under Generated posts below.
            </p>
            {canManage && (
              <Button size="sm" onClick={() => onPlan(null)}>
                <PlusIcon />
                Create plan
              </Button>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Plans can be made once the trend is shortlisted.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
