import { Tag } from "@/components/shared/tag";
import { RELEVANCE_TONE } from "@/lib/tones";
import type { RelevanceLevel } from "@/types/api";

export const RELEVANCE: Record<RelevanceLevel, { label: string }> = {
  highly_relevant: { label: "Highly relevant" },
  relevant: { label: "Relevant" },
  weakly_relevant: { label: "Weakly relevant" },
  not_relevant: { label: "Not relevant" },
};

export const RELEVANCE_OPTIONS = (
  Object.keys(RELEVANCE) as RelevanceLevel[]
).map((value) => ({
  value,
  label: RELEVANCE[value].label,
}));

/** Green = strong fit, teal = fits, amber = borderline, gray = no fit. */
export function RelevanceBadge({
  level,
  overridden = false,
  className,
}: {
  level: RelevanceLevel | null;
  overridden?: boolean;
  className?: string;
}) {
  if (!level) return null;
  return (
    <Tag
      tone={RELEVANCE_TONE[level]}
      dot
      className={className}
      title={overridden ? "Set by a team member" : undefined}
    >
      {RELEVANCE[level].label}
      {overridden && <span className="opacity-70">· set manually</span>}
    </Tag>
  );
}
