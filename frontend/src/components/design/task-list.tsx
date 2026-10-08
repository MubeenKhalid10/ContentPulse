"use client";

import { PaletteIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { POST_STATUS_TONE } from "@/lib/tones";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { DayGroups } from "@/components/shared/day-groups";
import { PageHeader } from "@/components/shared/page-header";
import { SimpleSelect } from "@/components/shared/simple-select";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePersistedState } from "@/hooks/use-persisted-state";
import { type DesignFilters, useDesignTasks } from "@/hooks/use-design";
import { useCan } from "@/lib/auth";
import { POST_STATUS_LABEL } from "@/lib/content";
import { formatLabel } from "@/lib/design";
import { timeOfDay } from "@/lib/format";
import { PLATFORM_OPTIONS } from "@/lib/options";
import { cn } from "@/lib/utils";
import type { DesignTask, DesignTaskFilter } from "@/types/api";

const PAGE = 30;
const TABS: { value: DesignTaskFilter; label: string }[] = [
  { value: "todo", label: "To do" },
  { value: "submitted", label: "Waiting for approval" },
  { value: "done", label: "Done" },
  { value: "all", label: "All" },
];
const EMPTY: Record<DesignTaskFilter, string> = {
  todo: "No open design tasks. Posts appear here when they're sent to design from the content studio.",
  submitted: "Nothing submitted for approval yet.",
  done: "No completed designs yet.",
  cancelled: "No cancelled tasks.",
  all: "No design tasks yet.",
};

export function DesignTaskList() {
  const isDesigner = useCan()("design.upload");
  const [filters, setFilters] = usePersistedState<DesignFilters>("design", {
    status: "todo",
    mine: false,
    platform: "",
    q: "",
  });
  const [limit, setLimit] = useState(PAGE);
  const tasks = useDesignTasks(filters, limit);
  const update = (patch: Partial<DesignFilters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setLimit(PAGE);
  };
  const counts = tasks.data?.counts;

  return (
    <>
      <PageHeader
        title="Design"
        description="Posts that need a visual. Open a task, upload the finished design, then submit it for approval."
      />
      {counts?.all === 0 && !filters.q && !filters.platform && !filters.mine ? (
        <Card>
          <CardContent className="grid justify-items-center gap-4 py-12 text-center">
            <span className="grid size-12 place-items-center rounded-full bg-muted">
              <PaletteIcon className="size-6 text-muted-foreground" />
            </span>
            <div className="grid max-w-md gap-1.5">
              <p className="text-lg font-medium">No design tasks yet</p>
              <p className="text-sm text-muted-foreground">{EMPTY.todo}</p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid min-w-0 grid-cols-1 gap-6">
          <div className="flex flex-wrap items-center gap-3">
            <Tabs
              value={filters.status}
              onValueChange={(v) => update({ status: v as DesignTaskFilter })}
            >
              <TabsList>
                {TABS.map((tab) => (
                  <TabsTrigger key={tab.value} value={tab.value}>
                    {tab.label}
                    {counts && tab.value !== "all" && counts[tab.value] > 0 && (
                      <span className="ml-1 rounded-full bg-muted px-1.5 text-[11px] tabular-nums text-muted-foreground">
                        {counts[tab.value]}
                      </span>
                    )}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <Input
              aria-label="Search tasks"
              placeholder="Search tasks"
              value={filters.q}
              onChange={(e) => update({ q: e.target.value })}
              className="w-full sm:w-56"
            />
            <div className="flex flex-wrap items-center gap-3 sm:ml-auto">
              {isDesigner && (
                <div className="flex items-center gap-2">
                  <Switch
                    id="mine"
                    checked={filters.mine}
                    onCheckedChange={(mine) => update({ mine })}
                  />
                  <Label htmlFor="mine">Assigned to me</Label>
                </div>
              )}
              <SimpleSelect
                aria-label="Platform"
                value={filters.platform || "all"}
                onChange={(v) =>
                  update({
                    platform:
                      v === "all" ? "" : (v as DesignFilters["platform"]),
                  })
                }
                options={[
                  { value: "all", label: "Any platform" },
                  ...PLATFORM_OPTIONS,
                ]}
                className="w-40"
              />
            </div>
          </div>

          {tasks.isPending ? (
            <div className="grid gap-3">
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className="h-20 w-full rounded-xl" />
              ))}
            </div>
          ) : tasks.data?.items.length ? (
            <>
              <div
                aria-busy={tasks.isPlaceholderData}
                className={cn(
                  "transition-opacity",
                  tasks.isPlaceholderData && "opacity-50",
                )}
              >
                <DayGroups
                  items={tasks.data.items}
                  dateOf={(t) => t.updated_at}
                  label="Design tasks"
                  render={(task) => <TaskRow key={task.id} task={task} />}
                />
              </div>
              {tasks.data.total > tasks.data.items.length && (
                <Button
                  variant="outline"
                  className="justify-self-center"
                  onClick={() => setLimit((n) => n + PAGE)}
                >
                  Show more ({tasks.data.total - tasks.data.items.length} left)
                </Button>
              )}
            </>
          ) : (
            <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
              {filters.q || filters.platform || filters.mine
                ? "No tasks match these filters."
                : EMPTY[filters.status]}
            </p>
          )}
        </div>
      )}
    </>
  );
}

function TaskRow({ task }: { task: DesignTask }) {
  return (
    <li className="relative grid gap-1.5 rounded-xl bg-card p-4 ring-1 ring-foreground/10 transition-colors hover:bg-muted/40">
      <div className="flex flex-wrap items-center gap-2">
        <PlatformTag platform={task.post.platform} />
        <Link
          href={`/design/${task.id}`}
          className="truncate font-medium after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:rounded-xl focus-visible:after:ring-2 focus-visible:after:ring-ring"
        >
          {task.post.title ?? "Untitled post"}
        </Link>
        <Tag tone={POST_STATUS_TONE[task.post.status]} dot>
          {POST_STATUS_LABEL[task.post.status]}
        </Tag>
        <span className="ml-auto text-xs text-muted-foreground">
          {timeOfDay(task.updated_at)}
        </span>
      </div>
      {task.headline && (
        <p className="line-clamp-1 text-sm text-muted-foreground">
          “{task.headline}”
        </p>
      )}
      <p className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
        <span>
          {formatLabel(task.format)}
          {task.dimensions ? ` · ${task.dimensions}` : ""}
        </span>
        <span>
          {task.assignee
            ? `Assigned to ${task.assignee.name ?? task.assignee.email}`
            : "Unassigned"}
        </span>
        {task.creative_versions > 0 && (
          <span>
            {task.creative_versions} creative version
            {task.creative_versions === 1 ? "" : "s"}
          </span>
        )}
      </p>
    </li>
  );
}
