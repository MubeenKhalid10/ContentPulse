"use client";

import { DownloadIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { type TrendsExport, useExportTrends, useExportWindow } from "@/hooks/use-trends";
import { ApiError, errorMessage } from "@/lib/api";

/** "Oct 23, 2026, 1:00 PM (UTC+01:00)": the time in the organization's
 * timezone, with the offset the server used. */
function inZone(iso: string, timeZone: string): string {
  let shown: string;
  try {
    shown = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short", timeZone }).format(
      new Date(iso),
    );
  } catch {
    shown = new Date(iso).toLocaleString();
  }
  const offset = /([+-]\d{2}:\d{2})$/.exec(iso)?.[1];
  return offset ? `${shown} (UTC${offset})` : shown;
}

function exportError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Your session has ended. Sign in again to download.";
    if (error.status === 403) return "Only admins can download trends.";
    if (error.status === 404) return "This organization isn't available. Switch organization and try again.";
  }
  return `The export failed: ${errorMessage(error)}`;
}

function save({ blob, filename }: TrendsExport) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/**
 * Admin-only CSV of the active organization's trends last seen in the last
 * seven days. Hidden for other roles; the backend enforces it either way.
 */
export function TrendsExport() {
  const range = useExportWindow(true);
  const download = useExportTrends();
  const [last, setLast] = useState<TrendsExport | null>(null);
  const info = range.data;

  const run = () =>
    download.mutate(undefined, {
      onSuccess: (file) => {
        save(file);
        setLast(file);
        if (file.rows === 0) {
          toast.message("No trends were seen in the last 7 days.", {
            description: "The CSV has only the column headers.",
          });
        } else {
          toast.success(`Downloaded ${file.rows} trend${file.rows === 1 ? "" : "s"}.`);
        }
      },
      onError: (error) => toast.error(exportError(error)),
    });

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="grid min-w-0 flex-1 gap-1 text-sm">
          <p className="font-medium">
            Trends export{info && <span className="text-muted-foreground"> · {info.organization_name}</span>}
          </p>
          {info ? (
            <p className="text-muted-foreground" data-testid="export-range">
              Trends last seen from <span className="text-foreground">{inZone(info.start, info.timezone)}</span> up to{" "}
              <span className="text-foreground">{inZone(info.end, info.timezone)}</span>, {info.timezone} time. The exact range is set when you download.
            </p>
          ) : range.isError ? (
            <p className="text-destructive">{exportError(range.error)}</p>
          ) : (
            <Skeleton className="h-4 w-80 max-w-full" />
          )}
          {last && (
            <p className="text-muted-foreground" role="status">
              {last.rows === 0
                ? "No trends were seen in this range: the CSV has only the column headers."
                : `Last download: ${last.rows} trend${last.rows === 1 ? "" : "s"}`}
              {last.start && ` (${inZone(last.start, last.timezone)} to ${inZone(last.end, last.timezone)}).`}
            </p>
          )}
        </div>
        <Button
          variant="success"
          onClick={run}
          disabled={download.isPending || !info}
          className="shrink-0 self-start sm:self-center"
        >
          <DownloadIcon />
          {download.isPending ? "Preparing CSV…" : "Download Trends — Last 7 Days"}
        </Button>
      </CardContent>
    </Card>
  );
}
