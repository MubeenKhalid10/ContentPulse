import {
  ActivityIcon,
  BookOpenIcon,
  BriefcaseIcon,
  Building2Icon,
  CheckCircle2Icon,
  FileTextIcon,
  LayoutDashboardIcon,
  LayoutGridIcon,
  type LucideIcon,
  PaletteIcon,
  RadarIcon,
  SettingsIcon,
  TargetIcon,
  SparklesIcon,
  TrendingUpIcon,
  UsersIcon,
  ListChecksIcon,
} from "lucide-react";

import type { Permission } from "@/types/api";
import { WORKFLOW } from "@/lib/workflow";

const STEP_ICONS: Record<string, LucideIcon> = {
  "/trends": TrendingUpIcon,
  "/topics": ListChecksIcon,
  "/content": SparklesIcon,
  "/design": PaletteIcon,
  "/approvals": CheckCircle2Icon,
};

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  permission?: Permission;
  /** Not built yet: shown disabled so the full workflow is visible. */
  comingIn?: string;
  /** Sub-pages that fold out under this item. */
  children?: NavItem[];
}

export interface NavSection {
  label?: string;
  items: NavItem[];
}

export const NAV: NavSection[] = [
  {
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboardIcon },
    ],
  },
  {
    label: "Workflow",
    items: WORKFLOW.map((s) => ({
      href: s.href,
      label: s.label,
      icon: STEP_ICONS[s.href],
      permission: s.permission,
      // Sources fold out under Trends.
      children:
        s.href === "/trends"
          ? [
              {
                href: "/trends/sources",
                label: "Trend sources",
                icon: RadarIcon,
              },
            ]
          : undefined,
    })),
  },
  {
    label: "Organization",
    items: [
      { href: "/organization/profile", label: "Profile", icon: Building2Icon },
      {
        href: "/organization/content-setup",
        label: "Content setup",
        icon: TargetIcon,
      },
      {
        href: "/organization/services",
        label: "Services & products",
        icon: BriefcaseIcon,
      },
      { href: "/organization/brand", label: "Brand", icon: FileTextIcon },
      {
        href: "/organization/platforms",
        label: "Platform playbook",
        icon: LayoutGridIcon,
      },
      {
        href: "/organization/knowledge",
        label: "Knowledge base",
        icon: BookOpenIcon,
        permission: "knowledge.read",
      },
    ],
  },
  {
    label: "Admin",
    items: [
      { href: "/team", label: "Team", icon: UsersIcon },
      {
        href: "/activity",
        label: "Activity log",
        icon: ActivityIcon,
        permission: "organization.write",
      },
    ],
  },
  {
    label: "Account",
    items: [{ href: "/settings", label: "Settings", icon: SettingsIcon }],
  },
];
