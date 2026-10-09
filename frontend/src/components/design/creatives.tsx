"use client";

import {
  DownloadIcon,
  FileTextIcon,
  FilmIcon,
  LoaderCircleIcon,
  SendIcon,
  SparklesIcon,
  UploadCloudIcon,
  XIcon,
} from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useGenerateImage, useSubmitTask, useUploadCreatives } from "@/hooks/use-design";
import { errorMessage } from "@/lib/api";
import { formatBytes } from "@/lib/design";
import { cleanNote, formatDateTime, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { CreativeFile, DesignTaskDetail } from "@/types/api";

const ACCEPT_LABEL = "PNG, JPG, WebP, GIF, SVG, PDF, MP4, MOV or WebM";

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
  const maxBytes = task.max_upload_mb * 1_000_000;
  const nextVersion = (task.creatives[0]?.version ?? 0) + 1;

  const add = (incoming: FileList | null) => {
    if (!incoming) return;
    const accepted: File[] = [];
    for (const file of Array.from(incoming)) {
      if (!task.allowed_types.includes(file.type)) toast.error(`“${file.name}” isn't a supported file (${ACCEPT_LABEL}).`);
      else if (file.size > maxBytes) toast.error(`“${file.name}” is larger than ${task.max_upload_mb} MB.`);
      else accepted.push(file);
    }
    setFiles((current) => [...current, ...accepted].slice(0, 20));
  };

  // The latest design can be (re)submitted as is, e.g. after copy-only changes.
  const canResubmitCurrent =
    task.creatives.length > 0 && (task.post.status === "design_uploaded" || task.post.status === "changes_requested");
  const busy = upload.isPending || submit.isPending;

  const send = async (andSubmit: boolean) => {
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
            {ACCEPT_LABEL}, up to {task.max_upload_mb} MB each
          </span>
        </button>
        <input
          ref={input}
          type="file"
          multiple
          accept={task.allowed_types.join(",")}
          className="sr-only"
          aria-label="Choose creative files"
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
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${Math.round(progress * 100)}%` }} />
            </div>
            <span className="text-xs text-muted-foreground">Uploading… {Math.round(progress * 100)}%</span>
          </div>
        )}
        {canSubmit ? (
          <div className="grid gap-1.5">
            <Button onClick={() => send(true)} disabled={busy || (!files.length && !canResubmitCurrent)}>
              <SendIcon />
              {upload.isPending
                ? "Uploading…"
                : submit.isPending
                  ? "Submitting…"
                  : files.length
                    ? "Upload & submit for approval"
                    : canResubmitCurrent
                      ? "Submit current design for approval"
                      : "Choose files to submit"}
            </Button>
            {files.length > 0 && (
              <Button variant="ghost" size="sm" onClick={() => send(false)} disabled={busy}>
                <UploadCloudIcon />
                Upload only (don&apos;t submit yet)
              </Button>
            )}
          </div>
        ) : (
          <Button onClick={() => send(false)} disabled={!files.length || busy}>
            <UploadCloudIcon />
            {upload.isPending ? "Uploading…" : "Upload"}
          </Button>
        )}
        {task.storage === "local" && (
          <p className="text-xs text-muted-foreground">Stored on the ContentPulse server. Configure S3 for production storage.</p>
        )}
      </CardContent>
    </Card>
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

export function CreativeVersions({ task }: { task: DesignTaskDetail }) {
  if (!task.creatives.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Creative versions</CardTitle>
        <CardDescription>Every upload is kept. The newest version is the one reviewers see.</CardDescription>
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
      <a href={file.url} target="_blank" rel="noopener noreferrer" className="block aspect-square bg-muted/50">
        {isImage ? (
          // Signed, short-lived URLs from S3 or the API: next/image can't optimize them.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={file.url} alt={file.file_name} className="size-full object-contain" loading="lazy" />
        ) : (
          <span className="grid size-full place-items-center text-muted-foreground">
            {isVideo ? <FilmIcon className="size-8" /> : <FileTextIcon className="size-8" />}
          </span>
        )}
      </a>
      <div className="flex items-center gap-1 px-2 pb-1.5">
        <span className="min-w-0 flex-1 truncate text-xs" title={file.file_name}>
          {file.file_name}
        </span>
        <a
          href={file.download_url}
          className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label={`Download ${file.file_name}`}
          title={`Download (${formatBytes(file.file_size)})`}
        >
          <DownloadIcon className="size-3.5" />
        </a>
      </div>
    </li>
  );
}
