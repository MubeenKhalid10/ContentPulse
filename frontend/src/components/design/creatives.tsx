"use client";

import {
  AlertTriangleIcon,
  DownloadIcon,
  FileTextIcon,
  FilmIcon,
  LoaderCircleIcon,
  RotateCcwIcon,
  SendIcon,
  SparklesIcon,
  UploadCloudIcon,
  XIcon,
} from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { SignedImage } from "@/components/shared/signed-image";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useGenerateImage, useSubmitTask, useUploadCreatives, useUseCreativeVersion } from "@/hooks/use-design";
import { errorMessage } from "@/lib/api";
import { formatBytes } from "@/lib/design";
import { cleanNote, formatDateTime, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { CreativeFile, DesignTaskDetail } from "@/types/api";

const MAX_FILES = 20;
const TYPE_NAMES: Record<string, string> = {
  "image/png": "PNG",
  "image/jpeg": "JPG",
  "image/webp": "WebP",
  "image/gif": "GIF",
  "image/svg+xml": "SVG",
  "application/pdf": "PDF",
  "video/mp4": "MP4",
  "video/quicktime": "MOV",
  "video/webm": "WebM",
};
const acceptLabel = (types: string[]) => {
  const names = types.map((t) => TYPE_NAMES[t] ?? t.split("/")[1]?.toUpperCase() ?? t);
  return names.length > 1 ? `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}` : names.join("");
};

/** Add the design and send the post for approval in one step. "Upload only"
 * keeps a work-in-progress version without submitting it. */
export function CreativeUploader({ task, canSubmit }: { task: DesignTaskDetail; canSubmit: boolean }) {
  const upload = useUploadCreatives();
  const submit = useSubmitTask();
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [note, setNote] = useState("");
  const [progress, setProgress] = useState(0);
  const [dragging, setDragging] = useState(false);
  const accept = acceptLabel(task.allowed_types);
  const maxBytes = task.max_upload_mb * 1_000_000;
  const nextVersion = (task.creatives[0]?.version ?? 0) + 1;

  const add = (incoming: FileList | null) => {
    if (!incoming) return;
    const accepted: File[] = [];
    const problems: string[] = [];
    for (const file of Array.from(incoming)) {
      if (!task.allowed_types.includes(file.type)) problems.push(`“${file.name}” isn't a supported file type`);
      else if (file.size > maxBytes) problems.push(`“${file.name}” is larger than ${task.max_upload_mb} MB`);
      else accepted.push(file);
    }
    const combined = [...files, ...accepted];
    if (combined.length > MAX_FILES) problems.push(`Only ${MAX_FILES} files can go in one upload. ${combined.length - MAX_FILES} not added`);
    if (problems.length) toast.error(`${problems.join(". ")}.`, { description: `Allowed: ${accept}.` });
    setFiles(combined.slice(0, MAX_FILES));
  };

  // The latest design can be (re)submitted as is, e.g. after copy-only changes.
  const canResubmitCurrent =
    task.creatives.length > 0 &&
    ["design_pending", "design_in_progress", "design_uploaded", "changes_requested"].includes(task.post.status);
  const busy = upload.isPending || submit.isPending;
  const [submitting, setSubmitting] = useState(false);

  const send = async (andSubmit: boolean) => {
    setSubmitting(andSubmit);
    try {
      if (files.length) {
        await upload.mutateAsync({ taskId: task.id, files, note: note.trim() || undefined, onProgress: setProgress });
        setFiles([]);
        setNote("");
        setProgress(0);
      }
      if (andSubmit) {
        await submit.mutateAsync(task.id);
        toast.success("Submitted for approval");
      } else {
        toast.success(`Saved as version ${nextVersion}`);
      }
    } catch (e) {
      toast.error(errorMessage(e));
      setProgress(0);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Add the design</CardTitle>
        <CardDescription>
          Upload the finished files and submit the post for approval. Carousel slides go in one upload, in order. Earlier
          versions are kept.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid min-w-0 grid-cols-1 gap-3">
        {task.ai_images && <GenerateImage task={task} />}
        <button
          type="button"
          onClick={() => input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            add(e.dataTransfer.files);
          }}
          className={cn(
            "grid justify-items-center gap-1.5 rounded-xl border border-dashed p-6 text-center text-sm transition-colors hover:bg-muted/50",
            dragging && "border-primary bg-primary/5",
          )}
        >
          <UploadCloudIcon className="size-6 text-muted-foreground" />
          <span className="font-medium">Drop files here or choose files</span>
          <span className="text-xs text-muted-foreground">
            {accept}, up to {task.max_upload_mb} MB each, {MAX_FILES} files at a time
          </span>
        </button>
        <input
          ref={input}
          type="file"
          multiple
          accept={task.allowed_types.join(",")}
          className="sr-only"
          aria-label="Choose design files"
          onChange={(e) => {
            add(e.target.files);
            e.target.value = "";
          }}
        />
        {files.length > 0 && (
          <ol className="grid min-w-0 grid-cols-1 gap-1 text-sm" aria-label="Files to upload">
            {files.map((file, i) => (
              <li key={`${file.name}-${i}`} className="flex min-w-0 items-center gap-2 rounded-lg bg-muted/50 px-2.5 py-1.5">
                <span className="text-xs tabular-nums text-muted-foreground">{i + 1}.</span>
                <span className="min-w-0 flex-1 truncate">{file.name}</span>
                <span className="text-xs text-muted-foreground">{formatBytes(file.size)}</span>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  aria-label={`Remove ${file.name}`}
                  disabled={upload.isPending}
                  onClick={() => setFiles((current) => current.filter((_, j) => j !== i))}
                >
                  <XIcon />
                </Button>
              </li>
            ))}
          </ol>
        )}
        <Input aria-label="Note for this version" placeholder="Note for reviewers (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
        {upload.isPending && (
          <div className="grid gap-1" role="status">
            <div
              className="h-1.5 overflow-hidden rounded-full bg-muted"
              role="progressbar"
              aria-label="Upload progress"
              aria-valuenow={Math.round(progress * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${Math.round(progress * 100)}%` }} />
            </div>
            <span className="text-xs text-muted-foreground">
              {progress >= 1 ? "Finishing up…" : `Uploading… ${Math.round(progress * 100)}%`}
            </span>
          </div>
        )}
        {canSubmit ? (
          <div className="grid gap-1.5">
            <Button onClick={() => send(true)} disabled={busy || (!files.length && !canResubmitCurrent)} pending={busy && submitting}>
              <SendIcon />
              {upload.isPending
                ? "Uploading…"
                : submit.isPending
                  ? "Submitting…"
                  : "Submit for approval"}
            </Button>
            {!files.length && !canResubmitCurrent && (
              <p className="text-xs text-muted-foreground">Add at least one file to submit.</p>
            )}
            <p className="text-xs text-muted-foreground">
              Submitting locks the design until an admin approves it or asks for changes.
            </p>
            {files.length > 0 && (
              <Button variant="ghost" size="sm" onClick={() => send(false)} disabled={busy} pending={busy && !submitting}>
                <UploadCloudIcon />
                Upload only (don&apos;t submit yet)
              </Button>
            )}
          </div>
        ) : (
          <Button onClick={() => send(false)} disabled={!files.length || busy} pending={busy}>
            <UploadCloudIcon />
            {upload.isPending ? "Uploading…" : "Upload"}
          </Button>
        )}
        {task.storage === "local" && <LocalStorageNote />}
      </CardContent>
    </Card>
  );
}

/** Local storage keeps files on the server's own disk: fine on a laptop, lost on a hosted server. */
function LocalStorageNote() {
  const hosted =
    typeof window !== "undefined" && !["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);
  if (!hosted)
    return (
      <p className="text-xs text-muted-foreground">
        Files are stored on this ContentPulse server.
      </p>
    );
  return (
    <Alert>
      <AlertTriangleIcon />
      <AlertTitle>Files may disappear</AlertTitle>
      <AlertDescription>
        This site keeps design files on the server&apos;s own disk, which is erased whenever it restarts or
        redeploys. Ask your admin to set up permanent file storage so images stay available.
      </AlertDescription>
    </Alert>
  );
}

/** "Generate image with AI": draws an image from the brief and the post; it
 * arrives as the next version, ready to review and submit. */
function GenerateImage({ task }: { task: DesignTaskDetail }) {
  const generate = useGenerateImage();
  const job = task.image_job;
  const drawing = generate.isPending || (!!job && (job.status === "queued" || job.status === "running"));
  return (
    <div className="grid gap-2">
      <Button
        variant="outline"
        disabled={drawing}
        onClick={() =>
          generate.mutate(task.id, {
            onSuccess: () => toast.success("Creating an image from the brief…"),
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      >
        {drawing ? <LoaderCircleIcon className="animate-spin" /> : <SparklesIcon />}
        {drawing ? "Creating image…" : "Generate image with AI"}
      </Button>
      {drawing ? (
        <p className="text-xs text-muted-foreground" role="status">
          Using the brief, the post and this post&apos;s colors. This usually takes under a minute.
        </p>
      ) : job?.status === "failed" ? (
        <Alert variant="destructive">
          <AlertDescription>{job.error ?? "The image couldn't be created."}</AlertDescription>
        </Alert>
      ) : job?.status === "succeeded" && job.version ? (
        <p className="text-xs text-muted-foreground" role="status">
          AI image added as version {job.version}. Check it below, then submit it, or generate another.
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">Or upload your own files below.</p>
      )}
    </div>
  );
}

export function CreativeVersions({ task, canUse = false }: { task: DesignTaskDetail; canUse?: boolean }) {
  const use = useUseCreativeVersion();
  if (!task.creatives.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Design versions</CardTitle>
        <CardDescription>
          Every upload is kept. The newest version is the one reviewers see
          {canUse && task.creatives.length > 1 ? ": use an older one to make it the newest again." : "."}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5">
        {task.creatives.map((v, i) => (
          <section key={v.version} aria-label={`Version ${v.version}`} className="grid gap-2">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">Version {v.version}</span>
              {i === 0 && <Badge>Latest</Badge>}
              <span className="text-xs text-muted-foreground">
                {v.uploaded_by?.name ?? v.uploaded_by?.email ?? "Someone"} ·{" "}
                <time title={formatDateTime(v.created_at)}>{timeAgo(v.created_at)}</time>
              </span>
            </div>
            {v.note && <p className="text-sm text-muted-foreground">{cleanNote(v.note)}</p>}
            {canUse && i > 0 && (
              <Button
                size="sm"
                variant="outline"
                className="w-fit"
                disabled={use.isPending}
                pending={use.isPending && use.variables?.version === v.version}
                onClick={() =>
                  use.mutate(
                    { id: task.id, version: v.version },
                    {
                      onSuccess: () =>
                        toast.success(`Version ${v.version} is now the newest`, {
                          description: "Submit it for design approval when you're ready.",
                        }),
                      onError: (e) => toast.error(errorMessage(e)),
                    },
                  )
                }
              >
                <RotateCcwIcon />
                Use version {v.version} as newest
              </Button>
            )}
            <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {v.files.map((f) => (
                <CreativeTile key={f.id} file={f} />
              ))}
            </ul>
          </section>
        ))}
      </CardContent>
    </Card>
  );
}

export function CreativeTile({ file }: { file: CreativeFile }) {
  const isImage = file.file_type.startsWith("image/");
  const isVideo = file.file_type.startsWith("video/");
  return (
    <li className="grid gap-1 overflow-hidden rounded-lg border">
      <a
        href={file.url}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`Open ${file.file_name} in a new tab`}
        className="block aspect-square bg-muted/50"
      >
        {isImage ? (
          <SignedImage src={file.url} alt={file.file_name} className="size-full object-contain" />
        ) : (
          <span className="grid size-full place-items-center text-muted-foreground">
            {isVideo ? <FilmIcon className="size-8" /> : <FileTextIcon className="size-8" />}
          </span>
        )}
      </a>
      <div className="flex items-center gap-1 pl-2">
        <span className="min-w-0 flex-1 truncate text-xs" title={file.file_name}>
          {file.file_name}
        </span>
        <a
          href={file.download_url}
          className="grid size-8 shrink-0 place-items-center rounded text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label={`Download ${file.file_name}`}
          title={`Download (${formatBytes(file.file_size)})`}
        >
          <DownloadIcon className="size-3.5" />
        </a>
      </div>
    </li>
  );
}
