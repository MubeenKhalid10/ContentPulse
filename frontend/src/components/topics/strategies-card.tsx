"use client";

import { ClipboardListIcon, PlusIcon, SparklesIcon } from "lucide-react";
import { toast } from "sonner";

import { StrategyCard } from "@/components/topics/strategy-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { usePosts, useWriteAll } from "@/hooks/use-content";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import type { Platform, Strategy, TopicDetail } from "@/types/api";

import { SectionHeader } from "./platform-fit-card";

export function StrategiesCard({
  topic,
  canManage,
  onPlan,
  onEdit,
}: {
  topic: TopicDetail;
  canManage: boolean;
  onPlan: (platform: Platform | null) => void;
  onEdit: (strategy: Strategy) => void;
}) {
  const shortlisted = topic.status === "shortlisted";
  const strategies = [...topic.strategies].sort(
    (a, b) => Number(a.status === "archived") - Number(b.status === "archived"),
  );
  // Same query as the Posts card below (shared cache): the post each plan led to.
  const posts = usePosts(
    { status: "all", platform: "", topicId: topic.id, q: "" },
    50,
  );
  const canGenerate = useCan()("content.generate");
  const writeAll = useWriteAll();
  // A plan that already has a post is shown in the Posts card instead.
  const unwritten = strategies.filter(
    (s) =>
      !(posts.data?.items ?? []).some((p) => p.content_strategy_id === s.id),
  );
  const toWrite = unwritten.filter((s) => s.status !== "archived");
  const hasPlans = strategies.length > 0;
  const canCreate = canManage && shortlisted;
  return (
    <Card>
      <CardHeader>
        <SectionHeader
          icon={ClipboardListIcon}
          title="Post plans"
          description="Each plan sets the platform, audience, message and goal of one post."
          badge={`${strategies.length} ${strategies.length === 1 ? "plan" : "plans"}`}
          actions={
            hasPlans && canCreate && unwritten.length > 0 ? (
              <>
                {canGenerate && toWrite.length > 1 && (
                  <Button
                    size="sm"
                    disabled={writeAll.isPending}
                    pending={writeAll.isPending}
                    onClick={() =>
                      writeAll.mutate(
                        toWrite.map((s) => s.id),
                        {
                          onError: (e) => toast.error(errorMessage(e)),
                          onSuccess: (r) =>
                            r.failed
                              ? toast.error(
                                  `Started ${r.ok}, but ${r.failed} failed: ${errorMessage(r.error)}`,
                                )
                              : toast.success(
                                  `Writing ${r.ok} posts, one per platform. They stay together in Write posts.`,
                                ),
                        },
                      )
                    }
                  >
                    <SparklesIcon />
                    {writeAll.isPending ? "Starting…" : `Write all ${toWrite.length} posts`}
                  </Button>
                )}
                <Button
                  size="sm"
                  variant={toWrite.length > 1 && canGenerate ? "outline" : "default"}
                  onClick={() => onPlan(null)}
                >
                  <PlusIcon />
                  Create plan
                </Button>
              </>
            ) : null
          }
        />
      </CardHeader>
      <CardContent className="grid gap-3">
        {unwritten.length ? (
          unwritten.map((s) => (
            <StrategyCard
              key={s.id}
              strategy={s}
              canManage={canManage && shortlisted}
              onEdit={() => onEdit(s)}
            />
          ))
        ) : hasPlans ? (
          <div className="grid justify-items-center gap-3 rounded-lg border border-dashed p-5 text-center">
            <p className="text-sm text-muted-foreground">
              Every plan has a post. Review them under Generated posts below.
            </p>
            {canCreate && (
              <Button size="sm" onClick={() => onPlan(null)}>
                <PlusIcon />
                Create plan
              </Button>
            )}
          </div>
        ) : shortlisted ? (
          <div className="grid justify-items-center gap-3 rounded-lg border border-dashed p-5 text-center">
            <p className="text-sm text-muted-foreground">
              Choose where to publish, who you&apos;re targeting, and what the post should achieve.
            </p>
            {canCreate && (
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
