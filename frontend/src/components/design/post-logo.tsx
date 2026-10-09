"use client";

import { MoveIcon, RotateCcwIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import {
  LogoPlacementPreview,
  LogoPositionPicker,
} from "@/components/shared/logo-position-picker";
import { Button } from "@/components/ui/button";
import { useUpdateBrief } from "@/hooks/use-design";
import { errorMessage } from "@/lib/api";
import { LOGO_POSITION_LABEL, type LogoPosition } from "@/lib/logo";
import type { DesignTaskDetail } from "@/types/api";

/**
 * Where the real logo (Profile: uploaded file, else Logo URL) goes on this post's AI images: the
 * brand default unless someone moved it for this post.
 */
export function PostLogo({
  task: t,
  canEdit,
  canEditBrand,
}: {
  task: DesignTaskDetail;
  canEdit: boolean;
  canEditBrand: boolean;
}) {
  const update = useUpdateBrief();
  const brandDefault = t.brand.logo_position;
  const own = t.brand_requirements.logo_position ?? null;
  const position = own ?? brandDefault;
  const moved = own !== null && own !== brandDefault;
  const [draft, setDraft] = useState<LogoPosition | null>(null);

  function save(next: LogoPosition | null, message: string) {
    update.mutate(
      { id: t.id, logo_position: next },
      {
        onSuccess: () => {
          setDraft(null);
          toast.success(message);
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    );
  }

  if (!t.brand.logo_url) {
    return (
      <div className="grid gap-1">
        <span className="text-sm font-medium">Logo</span>
        <p className="text-xs text-muted-foreground">
          No logo yet. Upload one (or add a Logo URL) in the organization
          profile to place it on AI-generated images.{" "}
          {canEditBrand && (
            <Link
              href="/organization/profile"
              className="underline underline-offset-4"
            >
              Add it in Profile
            </Link>
          )}
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">Logo</span>
        <span className="text-xs text-muted-foreground">
          {moved ? "Moved for this post" : "Brand default"}
        </span>
        {canEdit && !draft && (
          <span className="ml-auto flex gap-1">
            {moved && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={update.isPending}
                onClick={() => save(null, "Logo back to the brand position")}
              >
                <RotateCcwIcon /> Use brand position
              </Button>
            )}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setDraft(position)}
            >
              <MoveIcon /> Change position
            </Button>
          </span>
        )}
      </div>

      {!draft && (
        <div className="flex flex-wrap items-center gap-3">
          {/* A white frame shaped like the image, logo at its real spot and size. */}
          <LogoPlacementPreview
            src={t.brand.logo_url}
            position={position}
            label={
              position === "none"
                ? "Your logo is not placed on AI images"
                : `Your logo, ${LOGO_POSITION_LABEL[position].toLowerCase()}`
            }
          />
          <span className="text-sm">
            {position === "none"
              ? "Not placed on AI images"
              : LOGO_POSITION_LABEL[position]}
          </span>
        </div>
      )}

      {draft && (
        <div className="grid gap-3 rounded-lg border p-3">
          <LogoPositionPicker
            label="Logo position for this post"
            value={draft}
            onChange={setDraft}
            logoSrc={t.brand.logo_url}
          />
          <p className="text-xs text-muted-foreground">
            Applies to images generated for this post. The logo is placed as it
            is, never redrawn.
          </p>
          <div className="flex flex-wrap justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setDraft(null)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={update.isPending}
              onClick={() =>
                save(
                  draft === brandDefault ? null : draft,
                  "Logo position saved for this post",
                )
              }
            >
              {update.isPending ? "Saving…" : "Save position"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
