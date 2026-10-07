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
  SettingsIcon,
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
}

export interface NavSection {
  label?: string;
  items: NavItem[];
}

export const NAV: NavSection[] = [
  { items: [{ href: "/dashboard", label: "Dashboard", icon: LayoutDashboardIcon }] },
  {
    label: "Workflow",
    items: WORKFLOW.map((s) => ({
      href: s.href,
      label: s.label,
      icon: STEP_ICONS[s.href],
      permission: s.permission,
    })),
  },
  {
    label: "Organization",
    items: [
      { href: "/organization/profile", label: "Profile", icon: Building2Icon },
      { href: "/organization/services", label: "Services & products", icon: BriefcaseIcon },
      { href: "/organization/brand", label: "Brand", icon: FileTextIcon },
      { href: "/organization/platforms", label: "Platform playbook", icon: LayoutGridIcon },
      { href: "/organization/knowledge", label: "Knowledge base", icon: BookOpenIcon, permission: "knowledge.read" },
    ],
  },
  {
    label: "Admin",
    items: [
      { href: "/team", label: "Team", icon: UsersIcon },
      { href: "/settings", label: "Settings", icon: SettingsIcon },
      { href: "/activity", label: "Activity log", icon: ActivityIcon, permission: "organization.write" },
    ],
  },
];
