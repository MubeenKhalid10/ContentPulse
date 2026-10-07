"use client";

import {
  CheckIcon,
  ChevronsUpDownIcon,
  CircleHelpIcon,
  LogOutIcon,
  MonitorIcon,
  MoonIcon,
  PlusIcon,
  SunIcon,
} from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { replayWelcomeTour } from "@/components/shell/welcome-tour";
import { useLogout, useSwitchOrganization } from "@/lib/auth";
import { roleLabel } from "@/lib/options";
import type { Me } from "@/types/api";

function initials(value: string) {
  return (
    value
      .split(/[\s@._-]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("") || "?"
  );
}

const THEMES = [
  { value: "light", label: "Light", icon: SunIcon },
  { value: "dark", label: "Dark", icon: MoonIcon },
  { value: "system", label: "Match my device", icon: MonitorIcon },
] as const;

export function UserMenu({ me }: { me: Me }) {
  const router = useRouter();
  const logout = useLogout();
  const switchOrganization = useSwitchOrganization();
  const active = me.memberships.find((m) => m.organization_id === me.organization_id);
  const { theme, setTheme } = useTheme();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex w-full items-center gap-2.5 rounded-md p-2 text-left outline-none hover:bg-sidebar-accent focus-visible:ring-3 focus-visible:ring-ring/50 data-popup-open:bg-sidebar-accent">
        <Avatar className="size-8">
          <AvatarFallback className="bg-muted text-xs font-medium text-foreground">
            {initials(me.name ?? me.email)}
          </AvatarFallback>
        </Avatar>
        <span className="grid min-w-0 flex-1 leading-tight">
          <span className="truncate text-sm font-medium">{active?.organization_name}</span>
          <span className="truncate text-xs text-muted-foreground">
            {me.name ?? me.email} · {me.role && roleLabel(me.role)}
          </span>
        </span>
        <ChevronsUpDownIcon className="size-4 text-muted-foreground" />
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" className="w-60">
        <DropdownMenuGroup>
          <DropdownMenuLabel>Organizations</DropdownMenuLabel>
          {me.memberships.map((m) => (
            <DropdownMenuItem
              key={m.organization_id}
              onClick={() => {
                if (m.organization_id !== me.organization_id) {
                  switchOrganization(m.organization_id);
                  router.push("/dashboard");
                }
              }}
            >
              <span className="flex-1 truncate">{m.organization_name}</span>
              {m.organization_id === me.organization_id && <CheckIcon className="text-primary" />}
            </DropdownMenuItem>
          ))}
          <DropdownMenuItem onClick={() => router.push("/onboarding")}>
            <PlusIcon />
            New organization
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuLabel>Theme</DropdownMenuLabel>
          {THEMES.map(({ value, label, icon: Icon }) => (
            <DropdownMenuItem key={value} onClick={() => setTheme(value)}>
              <Icon />
              <span className="flex-1">{label}</span>
              {theme === value && <CheckIcon className="text-primary" />}
            </DropdownMenuItem>
          ))}
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuLabel className="truncate">{me.email}</DropdownMenuLabel>
          <DropdownMenuItem
            onClick={() => {
              router.push("/dashboard");
              replayWelcomeTour();
            }}
          >
            <CircleHelpIcon />
            Show the welcome tour
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => logout.mutate()}>
            <LogOutIcon />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
