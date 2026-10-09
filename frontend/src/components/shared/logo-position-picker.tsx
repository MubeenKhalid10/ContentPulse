"use client";

import { useId } from "react";

import { LOGO_POSITION_LABEL, type LogoPosition } from "@/lib/logo";
import { cn } from "@/lib/utils";

const SPOTS = [
  "top_left",
  "top_center",
  "top_right",
  "bottom_left",
  "bottom_center",
  "bottom_right",
] as const satisfies readonly LogoPosition[];

/*
 * Same geometry the server uses when it places the logo (backend
 * app/services/design/logo.py): at most 18% of the width and 12% of the height,
 * never enlarged, 4% from the edges. The frame is white so the logo looks the
 * way it will on a light image.
 */
const MAX_W = "18cqw";
const MAX_H = "12cqh";
// Container units: the frame is a size container, so 4cqmin is 4% of its short
// side on every edge, exactly like the server.
const MARGIN = "4cqmin";

function spotStyle(position: LogoPosition): React.CSSProperties {
  const [vertical, horizontal] = position.split("_");
  return {
    position: "absolute",
    ...(vertical === "top" ? { top: MARGIN } : { bottom: MARGIN }),
    ...(horizontal === "left"
      ? { left: MARGIN }
      : horizontal === "right"
        ? { right: MARGIN }
        : { left: "50%", transform: "translateX(-50%)" }),
  };
}

/** The logo (or a stand-in block) sized and placed as it will be on the image. */
function PlacedLogo({
  src,
  position,
  width = MAX_W,
  height = MAX_H,
}: {
  src: string | null;
  position: LogoPosition;
  width?: string;
  height?: string;
}) {
  if (position === "none") return null;
  return (
    <span
      style={{ ...spotStyle(position), width, height }}
      className={cn(
        "pointer-events-none flex",
        position.endsWith("left")
          ? "justify-start"
          : position.endsWith("right")
            ? "justify-end"
            : "justify-center",
        position.startsWith("top") ? "items-start" : "items-end",
      )}
    >
      {src ? (
        // The organization's own logo, unchanged: signed or external links.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt=""
          referrerPolicy="no-referrer"
          className="block max-h-full max-w-full object-contain"
        />
      ) : (
        <span className="block h-full w-full rounded-[2px] bg-paper-10" />
      )}
    </span>
  );
}

/**
 * A compact read-only thumbnail of the current choice: a small white frame with
 * the logo in its spot. The logo is drawn larger than true scale here so it
 * stays recognisable; the picker shows the true size.
 */
export function LogoPlacementPreview({
  src,
  position,
  label,
  className,
}: {
  src: string | null;
  position: LogoPosition;
  label: string;
  className?: string;
}) {
  return (
    <div
      role="img"
      aria-label={label}
      className={cn(
        "relative aspect-[16/10] w-28 shrink-0 overflow-hidden rounded-md border border-paper-5 bg-white [container-type:size]",
        className,
      )}
    >
      <PlacedLogo src={src} position={position} width="40cqw" height="40cqh" />
      {position === "none" && (
        <span className="absolute inset-0 grid place-items-center text-xs text-neutral-500">
          No logo
        </span>
      )}
    </div>
  );
}

/**
 * Pick the logo's spot by clicking it on the frame. The chosen spot shows the
 * real logo; the others are dashed targets. Plain radio buttons underneath, so
 * keyboard and screen readers work as usual.
 */
export function LogoPositionPicker({
  value,
  onChange,
  disabled = false,
  label = "Logo position",
  logoSrc = null,
}: {
  value: LogoPosition;
  onChange: (value: LogoPosition) => void;
  disabled?: boolean;
  label?: string;
  logoSrc?: string | null;
}) {
  const name = useId();
  return (
    <fieldset className="grid gap-2" disabled={disabled}>
      <legend className="mb-1 text-sm font-medium">{label}</legend>
      <div className="flex flex-wrap items-center gap-4">
        <div className="relative aspect-[16/10] w-64 shrink-0 overflow-hidden rounded-md border border-paper-5 bg-white [container-type:size]">
          {SPOTS.map((position) => {
            const selected = value === position;
            return (
              <label
                key={position}
                title={LOGO_POSITION_LABEL[position]}
                // Click targets stay at least 24px tall (WCAG 2.5.8); the logo
                // itself is still drawn at its true size.
                style={{
                  ...spotStyle(position),
                  width: MAX_W,
                  height: `max(${MAX_H}, 24px)`,
                }}
                className={cn(
                  "cursor-pointer rounded-[2px] has-focus-visible:ring-3 has-focus-visible:ring-ring/50 has-disabled:cursor-not-allowed",
                  !selected &&
                    "border border-dashed border-neutral-400 hover:border-neutral-700 hover:bg-neutral-100",
                )}
              >
                <input
                  type="radio"
                  name={name}
                  value={position}
                  checked={selected}
                  disabled={disabled}
                  onChange={() => onChange(position)}
                  className="sr-only"
                />
                <span className="sr-only">{LOGO_POSITION_LABEL[position]}</span>
              </label>
            );
          })}
          <PlacedLogo src={logoSrc} position={value} />
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm has-disabled:cursor-not-allowed">
          <input
            type="radio"
            name={name}
            value="none"
            checked={value === "none"}
            disabled={disabled}
            onChange={() => onChange("none")}
            className="size-4 accent-foreground"
          />
          No logo
        </label>
      </div>
      <p className="text-xs text-muted-foreground" aria-live="polite">
        {value === "none"
          ? "Images are generated without a logo."
          : `Logo: ${LOGO_POSITION_LABEL[value].toLowerCase()}. Click another spot to move it.`}
      </p>
    </fieldset>
  );
}
