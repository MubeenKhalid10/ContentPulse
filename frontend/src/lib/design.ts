import { DESIGN_FORMAT_LABEL } from "@/lib/content";
import type { DesignFormat, DesignTaskStatus } from "@/types/api";

export const TASK_STATUS_LABEL: Record<DesignTaskStatus, string> = {
  open: "Open",
  assigned: "Assigned",
  in_progress: "In progress",
  submitted: "Submitted",
  completed: "Completed",
  cancelled: "Cancelled",
};

export function formatLabel(format: string): string {
  return DESIGN_FORMAT_LABEL[format as DesignFormat] ?? format;
}

export function formatBytes(bytes: number | null): string {
  if (bytes == null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
