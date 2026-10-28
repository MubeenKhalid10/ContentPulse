"use client";

import { ArrowRightIcon, CheckIcon } from "lucide-react";
import Link from "next/link";

import { Tag } from "@/components/shared/tag";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useKnowledgeSummary } from "@/hooks/use-knowledge";
import {
  useBrand,
  useMembers,
  useOrganization,
  useOrgSettings,
  useServices,
} from "@/hooks/use-organization";
import { useCan } from "@/lib/auth";
import { cn } from "@/lib/utils";

import type { SetupStep } from "./dashboard";

export function useSetupSteps() {
  const org = useOrganization();
  const settings = useOrgSettings();
  const brand = useBrand();
  const services = useServices();
  const members = useMembers();
  const canReadKnowledge = useCan()("knowledge.read");
  const knowledge = useKnowledgeSummary({ enabled: canReadKnowledge });

  const loading = [org, settings, brand, services, members].some(
    (q) => q.isPending,
  );
  const steps: SetupStep[] = [
    {
      done: !!org.data?.description,
      title: "Describe your organization",
      detail: "A sentence or two about what you do.",
      href: "/organization/profile",
    },
    {
      done: (services.data?.length ?? 0) > 0,
      title: "List your services and products",
      detail: "Trends are matched against these, so be specific.",
      href: "/organization/services",
    },
    {
      done: !!brand.data?.brand_voice,
      title: "Describe your brand voice",
      detail: "How you sound, and words to avoid.",
      href: "/organization/brand",
    },
    {
      done: !!settings.data?.target_markets.length,
      title: "Choose your markets and audience",
      detail: "Where your audience is and who you're writing for.",
      href: "/organization/content-setup#audience",
    },
    {
      done: !!settings.data?.enabled_platforms.length,
      title: "Turn on your platforms",
      detail: "Where you post. Content is only written for these.",
      href: "/organization/content-setup#platforms",
    },
    ...(canReadKnowledge
      ? [
          {
            done: (knowledge.data?.indexed_documents ?? 0) > 0,
            title: "Index your website",
            detail: "One click reads your pages so posts only say what your website backs up.",
            href: "/organization/knowledge?index=1",
          },
        ]
      : []),
    {
      done: (members.data?.length ?? 0) > 1,
      title: "Invite your team",
      detail:
        "Creators who write and design posts, and viewers. Optional if you work alone.",
      href: "/team",
      optional: true,
    },
  ];
  return {
    steps,
    completed: steps.filter((s) => s.done).length,
    essentialsDone: steps.every((s) => s.done || s.optional),
    loading,
  };
}

export function SetupChecklist({
  setup,
}: {
  setup: ReturnType<typeof useSetupSteps>;
}) {
  const { steps, completed } = setup;
  const first =
    steps.find((s) => !s.done && !s.optional) ?? steps.find((s) => !s.done);
  return (
    <Card>
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="grid gap-1">
            <CardTitle className="text-lg">Set up your workspace</CardTitle>
            <CardDescription>
              About 10 minutes. ContentPulse uses this to decide which trends
              matter to you and to write posts in your voice.
            </CardDescription>
          </div>
          {first && (
            <Link href={first.href} className={buttonVariants()}>
              {completed === 0 ? "Start setup" : "Continue setup"}
              <ArrowRightIcon />
            </Link>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div
            className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted"
            role="progressbar"
            aria-label="Setup progress"
            aria-valuemin={0}
            aria-valuemax={steps.length}
            aria-valuenow={completed}
          >
            <div
              className="h-full rounded-full bg-primary transition-[width] duration-500"
              style={{ width: `${(completed / steps.length) * 100}%` }}
            />
          </div>
          <span className="text-xs text-muted-foreground tabular-nums">
            {completed} of {steps.length} done.
          </span>
        </div>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-0.5 sm:grid-cols-2 sm:gap-x-6">
          {steps.map((step) => (
            <li key={step.href}>
              <Link
                href={step.href}
                className="group -mx-2 flex items-center gap-3 rounded-lg p-2 transition-colors hover:bg-muted"
              >
                <span
                  className={cn(
                    "grid size-5 shrink-0 place-items-center rounded-full border",
                    step.done &&
                      "border-primary bg-primary text-primary-foreground",
                  )}
                >
                  {step.done && <CheckIcon className="size-3" />}
                  <span className="sr-only">
                    {step.done ? "Done:" : "To do:"}
                  </span>
                </span>
                <span className="grid min-w-0 flex-1 gap-0.5">
                  <span
                    className={cn(
                      "text-sm font-medium",
                      step.done &&
                        "text-muted-foreground line-through decoration-muted-foreground/40",
                    )}
                  >
                    {step.title}
                    {step.optional && (
                      <Tag tone="neutral" className="ml-2 align-middle">
                        Optional
                      </Tag>
                    )}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {step.detail}
                  </span>
                </span>
                {step.done && (
                  <span className="text-xs text-muted-foreground group-hover:text-foreground">
                    Edit
                  </span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
