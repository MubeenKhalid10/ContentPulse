"use client";

import { ImageUpIcon, Trash2Icon } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  useLogoSrc,
  useRemoveLogo,
  useUploadLogo,
} from "@/hooks/use-organization";
import { errorMessage } from "@/lib/api";
import type { Organization } from "@/types/api";

const ACCEPT = ["image/png", "image/jpeg", "image/webp"];
const MAX_BYTES = 2_000_000;

/** The logo placed on AI-generated images: an uploaded file, else the Logo URL. */
export function LogoCard({
  org,
  canEdit,
}: {
  org: Organization;
  canEdit: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const upload = useUploadLogo();
  const remove = useRemoveLogo();
  const src = useLogoSrc(org);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [broken, setBroken] = useState(false);
  const source = org.has_logo_file
    ? "Uploaded file"
    : org.logo_url
      ? "From the Logo URL"
      : null;

  function choose(file: File | undefined) {
    if (!file) return;
    if (!ACCEPT.includes(file.type)) {
      toast.error("Choose a PNG, JPG or WebP image. SVG logos aren't supported.");
      return;
    }
    if (file.size > MAX_BYTES) {
      toast.error("The logo is larger than 2 MB. Export a smaller PNG.");
      return;
    }
    upload.mutate(file, {
      onSuccess: () => toast.success("Logo uploaded"),
      onError: (error) => toast.error(errorMessage(error)),
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Logo</CardTitle>
        <CardDescription>
          Placed on AI-generated images exactly as it is: the AI never redraws
          it. An uploaded file is used first; the Logo URL above is the
          fallback. A transparent PNG looks best.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-4">
        {/* White, so the logo looks the way it will on a light image. */}
        <div className="relative flex h-24 w-56 shrink-0 items-center justify-center overflow-hidden rounded-md border border-paper-5 bg-white p-3">
          {src && !broken ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={src}
              alt="Your logo"
              referrerPolicy="no-referrer"
              onError={() => setBroken(true)}
              className="block size-full object-contain"
            />
          ) : (
            <span className="text-xs text-neutral-500">
              {src ? "The logo couldn't be loaded" : "No logo yet"}
            </span>
          )}
        </div>
        <div className="grid gap-2">
          {source && <p className="text-sm text-muted-foreground">{source}</p>}
          {canEdit && (
            <div className="flex flex-wrap gap-2">
              <input
                ref={input}
                type="file"
                accept={ACCEPT.join(",")}
                className="sr-only"
                aria-label="Logo file"
                onChange={(e) => {
                  choose(e.target.files?.[0]);
                  e.target.value = ""; // allow choosing the same file again
                }}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={upload.isPending}
                pending={upload.isPending}
                onClick={() => input.current?.click()}
              >
                <ImageUpIcon />
                {upload.isPending
                  ? "Uploading…"
                  : org.has_logo_file
                    ? "Replace logo"
                    : "Upload logo"}
              </Button>
              {org.has_logo_file && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={remove.isPending}
                  pending={remove.isPending}
                  onClick={() => setConfirmRemove(true)}
                >
                  <Trash2Icon /> Remove uploaded logo
                </Button>
              )}
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            PNG, JPG or WebP, up to 2 MB.
          </p>
        </div>
      </CardContent>
      <AlertDialog open={confirmRemove} onOpenChange={setConfirmRemove}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove the uploaded logo?</AlertDialogTitle>
            <AlertDialogDescription>
              {org.logo_url
                ? "AI images will use the Logo URL instead."
                : "AI images will have no logo until you upload one."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                setConfirmRemove(false);
                remove.mutate(undefined, {
                  onSuccess: () => toast.success("Uploaded logo removed"),
                  onError: (error) => toast.error(errorMessage(error)),
                });
              }}
            >
              Remove logo
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
