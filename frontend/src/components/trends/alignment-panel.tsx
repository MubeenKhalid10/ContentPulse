"use client";

import {
  AlertTriangleIcon,
  LoaderCircleIcon,
  RefreshCwIcon,
  ShieldAlertIcon,
  SparklesIcon,
} from "lucide-react";
import { toast } from "sonner";

import { PlatformTag, Tag } from "@/components/shared/tag";
import { SimpleSelect } from "@/components/shared/simple-select";
import {
  RELEVANCE,
  RELEVANCE_OPTIONS,
  RelevanceBadge,
} from "@/components/trends/relevance";
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
  useOverrideRelevance,
} from "@/hooks/use-trends";
import { errorMessage } from "@/lib/api";
import { stripCitations, timeAgo } from "@/lib/format";
import type {
  ContentAngle,
  Platform,
  RelevanceLevel,
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
}: {
  trend: TrendDetail;
  canReview: boolean;
  /** When set, each content angle gets a button to plan a post from it. */
  onPlanAngle?: (angle: PossibleAngle) => void;
}) {
  const ai = useAIStatus();
  const analyze = useAnalyzeTrend();
  const override = useOverrideRelevance();
  const a = trend.alignment;
  const running =
    trend.analysis?.status === "queued" || trend.analysis?.status === "running";
  const failed = trend.analysis?.status === "failed";
  const analyzed = !!a.classification;
  const engineIsAI = ai.data?.engine === "ai";

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
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-start gap-2">
          <div className="grid min-w-0 flex-1 gap-2">
            <CardTitle className="flex items-center gap-2">
              <SparklesIcon className="size-4 text-primary" />
              Relevance to your organization
            </CardTitle>
            {analyzed && (
              <CardDescription className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <RelevanceBadge
                  level={trend.relevance_level}
                  overridden={trend.relevance_overridden}
                />
                <span>
                  {a.engine === "ai" ? "AI analysis" : "Rule-based estimate"}
                  {a.confidence != null &&
                    ` - ${Math.round(a.confidence * 100)}% confidence`}
                  {a.analyzed_at && ` · ${timeAgo(a.analyzed_at)}`}
                </span>
              </CardDescription>
            )}
          </div>
          {canReview && analyzed && !running && (
            <div className="ml-auto grid justify-items-end gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={runAnalysis}
                disabled={analyze.isPending}
              >
                <RefreshCwIcon />
                Re-analyze
              </Button>
              <div className="grid gap-1">
                <label
                  htmlFor="relevance-override"
                  className="text-xs text-muted-foreground"
                >
                  Relevance rating (change it if you disagree)
                </label>
                <SimpleSelect
                  id="relevance-override"
                  value={
                    trend.relevance_overridden
                      ? (trend.relevance_level ?? "auto")
                      : "auto"
                  }
                  onChange={(value) =>
                    override.mutate(
                      {
                        id: trend.id,
                        level:
                          value === "auto" ? null : (value as RelevanceLevel),
                      },
                      {
                        onSuccess: () => toast.success("Relevance updated"),
                        onError: (e) => toast.error(errorMessage(e)),
                      },
                    )
                  }
                  options={[
                    {
                      value: "auto",
                      label: `Automatic${a.classification ? ` (${RELEVANCE[a.classification].label})` : ""}`,
                    },
                    ...RELEVANCE_OPTIONS,
                  ]}
                  disabled={override.isPending}
                  className="w-56"
                />
              </div>
            </div>
          )}
        </div>
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
              <span>{trend.analysis?.error}</span>
              {canReview && (
                <Button
                  size="sm"
                  variant="outline"
                  className="justify-self-start"
                  onClick={runAnalysis}
                  disabled={analyze.isPending}
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
              {engineIsAI ? ", and suggests content angles." : "."}
            </p>
            {canReview && (
              <Button onClick={runAnalysis} disabled={analyze.isPending}>
                <SparklesIcon />
                Analyze now
              </Button>
            )}
          </div>
        )}

        {analyzed && (
          <>
            {a.reason && (
              <p className="text-sm leading-relaxed">
                <CitedText text={a.reason} />
              </p>
            )}

            {!!a.matched_services?.length && (
              <div className="grid gap-1.5">
                <p className="text-xs font-medium text-muted-foreground">
                  Connects to
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

            {!!a.possible_angles?.length && (
              <div className="grid gap-2">
                <p className="text-xs font-medium text-muted-foreground">
                  Content angles
                </p>
                <ol className="grid gap-2">
                  {a.possible_angles.map((angle, i) => (
                    <li key={i} className="grid gap-1 rounded-lg border p-3">
                      <p className="text-sm font-medium">{angle.title}</p>
                      <p className="text-sm text-muted-foreground">
                        <CitedText text={angle.angle} />
                      </p>
                      <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                        {angle.platforms.map((p) => (
                          <PlatformTag key={p} platform={p as Platform} />
                        ))}
                        {onPlanAngle && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="ml-auto"
                            aria-label={`Plan a post from “${angle.title}”`}
                            onClick={() => onPlanAngle(angle)}
                          >
                            Plan a post from this angle
                          </Button>
                        )}
                      </p>
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {a.engine === "rules" && (
              <p className="rounded-lg border border-dashed px-3 py-2 text-xs text-muted-foreground">
                This is a basic estimate from keyword and knowledge-base
                matches. Ask your administrator to turn on AI analysis for
                written reasoning and tailored content angles.
              </p>
            )}

            {!!a.unsupported_claims?.length && (
              <div className="grid gap-1.5 rounded-lg bg-destructive/5 p-3">
                <p className="flex items-center gap-1.5 text-xs font-medium text-destructive">
                  <ShieldAlertIcon className="size-3.5" />
                  Don&apos;t claim (not supported by your profile or knowledge
                  base)
                </p>
                <ul className="grid list-disc gap-0.5 pl-5 text-sm">
                  {a.unsupported_claims.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
