/** Where the organization's real logo goes on AI-generated images. */
export type LogoPosition =
  | "top_left"
  | "top_center"
  | "top_right"
  | "bottom_left"
  | "bottom_center"
  | "bottom_right"
  | "none";

export const LOGO_POSITIONS = [
  "top_left",
  "top_center",
  "top_right",
  "bottom_left",
  "bottom_center",
  "bottom_right",
  "none",
] as const satisfies readonly LogoPosition[];

export const LOGO_POSITION_LABEL: Record<LogoPosition, string> = {
  top_left: "Top left",
  top_center: "Top centre",
  top_right: "Top right",
  bottom_left: "Bottom left",
  bottom_center: "Bottom centre",
  bottom_right: "Bottom right",
  none: "No logo",
};
