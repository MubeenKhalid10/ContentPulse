"use client";

import {
  AlertTriangleIcon,
  ChevronRightIcon,
  LoaderCircleIcon,
  RefreshCwIcon,
  SparklesIcon,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PlatformTag, Tag } from "@/components/shared/tag";
import { AngleDialog } from "@/components/trends/angle-dialog";
import { RelevanceBadge } from "@/components/trends/relevance";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  useAIStatus,
  useAnalyzeTrend,
} from "@/hooks/use-trends";
import { errorMessage } from "@/lib/api";
import { stripCitations, timeAgo } from "@/lib/format";
import type {
  ContentAngle,
  Platform,
  TrendDetail,
} from "@/types/api";

type PossibleAngle = ContentAngle;

/** Reasoning text without [K1]-style source markers (sources aren't listed here). */
function CitedText({ text }: { text: string }) {
  return <>{stripCitations(text)}</>;
}

export function AlignmentPanel({
  trend,
  canReview,
  onPlanAngle,
  mode = "all",
}: {
  trend: TrendDetail;
  canReview: boolean;
  /** "fit": why it fits the business. "ideas": the post ideas. Default: both. */
  mode?: "fit" | "ideas" | "all";
  /** When set, each content angle gets a button to plan a post from it. */
  onPlanAngle?: (angle: PossibleAngle) => void;
}) {
  const ai = useAIStatus();
  const analyze = useAnalyzeTrend();
  const a = trend.alignment;
  const [openAngle, setOpenAngle] = useState<PossibleAngle | null>(null);
  const running =
    trend.analysis?.status === "queued" || trend.analysis?.status === "running";
  const failed = trend.analysis?.status === "failed";
  const analyzed = !!a.classification;
  const engineIsAI = ai.data?.engine === "ai";
  const showFit = mode !== "ideas";
  const showIdeas = mode !== "fit";

  const runAnalysis = () =>
    analyze.mutate(trend.id, {
      onSuccess: () =>
        toast.success(
          engineIsAI
            ? "Analyzing with AI…"
            : "Re-running the rule-based check…",
        ),
      onError: (e) => toast.error(errorMessage(e)),
    });

  return (
    <Card>
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="flex flex-1 items-center gap-2">
            <SparklesIcon className="size-4 text-primary" />
            {showFit ? "Why it fits your business" : "Post ideas"}
          </CardTitle>
          {showFit && canReview && analyzed && !running && (
            <Button
              variant="ghost"
              size="sm"
              onClick={runAnalysis}
              disabled={analyze.isPending}
              pending={analyze.isPending}
            >
              <RefreshCwIcon />
              Re-analyze
            </Button>
          )}
        </div>
        {analyzed && showFit && (
        <CardDescription className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <RelevanceBadge
              level={trend.relevance_level}
              overridden={trend.relevance_overridden}
            />
            <span
              title={
                a.engine === "ai"
                  ? "Judged by an AI model against your services and knowledge base."
                  : "A basic keyword match against your services. Less precise than AI analysis."
              }
            >
              {a.engine === "ai" ? "AI analysis" : "Rule-based estimate"}
              {a.analyzed_at && ` · ${timeAgo(a.analyzed_at)}`}
            </span>
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="grid gap-5">
        {running && (
          <p className="flex items-center gap-2 text-sm" role="status">
            <LoaderCircleIcon className="size-4 animate-spin text-primary" />
            {trend.analysis?.engine === "ai"
              ? "Analyzing against your services and knowledge base…"
              : "Checking against your services and knowledge base…"}
          </p>
        )}
        {failed && !running && (
          <Alert variant="destructive">
            <AlertTriangleIcon />
            <AlertTitle>The last analysis failed</AlertTitle>
            <AlertDescription className="grid gap-2">
              <span>
                The analysis couldn&apos;t finish. Details: {trend.analysis?.error}
              </span>
              {canReview && (
                <Button
                  size="sm"
                  variant="outline"
                  className="justify-self-start"
                  onClick={runAnalysis}
                  disabled={analyze.isPending}
                  pending={analyze.isPending}
                >
                  Try again
                </Button>
              )}
            </AlertDescription>
          </Alert>
        )}
        {!analyzed && !running && !failed && (
          <div className="grid justify-items-start gap-3 text-sm text-muted-foreground">
            <p>
              Not analyzed yet. Analysis judges how this trend relates to your
              services, explains the connection with evidence from your
              knowledge base
              {engineIsAI ? ", and suggests post ideas." : "."}
            </p>
            {canReview && (
              <Button onClick={runAnalysis} disabled={analyze.isPending} pending={analyze.isPending}>
                <SparklesIcon />
                Analyze now
              </Button>
            )}
          </div>
        )}

        {analyzed && (
          <>
            {showFit && a.reason && (
              <div className="grid gap-1.5">
                <p className="text-sm leading-relaxed">
                  <CitedText text={a.reason} />
                </p>
              </div>
            )}

            {showFit && !!a.matched_services?.length && (
              <div className="grid gap-1.5">
                <p className="text-sm font-semibold text-foreground">
                  Your services it matches
                </p>
                <ul className="flex flex-wrap gap-1.5">
                  {a.matched_services.map((s) => (
                    <li key={s}>
                      <Tag tone="teal">{s}</Tag>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {showIdeas && !!a.possible_angles?.length && (
              <div className="grid gap-2">
                {showFit && (
                  <p className="text-sm font-semibold text-foreground">Post ideas</p>
                )}
                <ol className="grid gap-2">
                  {a.possible_angles.map((angle, i) => (
                    <li
                      key={i}
                      className="relative grid gap-1 rounded-lg border p-3 transition-colors hover:bg-muted/40"
                    >
                      {/* The whole card opens the idea's details. */}
                      <button
                        type="button"
                        onClick={() => setOpenAngle(angle)}
                        aria-label={`Details of the idea “${angle.title}”`}
                        className="flex items-start gap-2 text-left text-sm font-medium outline-none after:absolute after:inset-0 after:rounded-lg focus-visible:after:ring-2 focus-visible:after:ring-ring"
                      >
                        <span className="flex-1">{angle.title}</span>
                        <span
                          aria-hidden
                          className="flex shrink-0 items-center gap-0.5 text-xs font-normal text-muted-foreground"
                        >
                          View details
                          <ChevronRightIcon className="size-4" />
                        </span>
                      </button>
                      <p className="text-sm text-muted-foreground">
                        <CitedText text={angle.angle} />
                      </p>
                      <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                        {angle.platforms.map((p) => (
                          <PlatformTag key={p} platform={p as Platform} />
                        ))}
                        {onPlanAngle && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="relative z-10 ml-auto"
                            aria-label={`Plan a post from the idea “${angle.title}”`}
                            onClick={() => onPlanAngle(angle)}
                          >
                            Plan a post from this idea
                          </Button>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
                <AngleDialog
                  angle={openAngle}
                  trend={trend}
                  onClose={() => setOpenAngle(null)}
                  onPlan={
                    onPlanAngle &&
                    ((angle) => {
                      setOpenAngle(null);
                      onPlanAngle(angle);
                    })
                  }
                />
              </div>
            )}


          </>
        )}
      </CardContent>
    </Card>
  );
}
