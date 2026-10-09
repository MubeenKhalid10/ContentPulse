"use client";

import { ChevronDownIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { NAV, type NavItem } from "@/components/shell/nav";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { Me } from "@/types/api";

const itemClass =
  "flex h-9 items-center gap-2.5 rounded-sm px-2.5 text-sm transition-colors pointer-coarse:h-11 [&_svg]:size-4 [&_svg]:shrink-0";

/** The most specific nav entry for this page (so /trends/sources isn't also "Trends"). */
function activeHref(pathname: string): string | undefined {
  return NAV.flatMap((section) =>
    section.items.flatMap((item) => [
      item.href,
      ...(item.children ?? []).map((c) => c.href),
    ]),
  )
    .filter((href) => pathname === href || pathname.startsWith(`${href}/`))
    .sort((a, b) => b.length - a.length)[0];
}

export function SidebarNav({
  me,
  onNavigate,
}: {
  me: Me;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const current = activeHref(pathname);

  return (
    <nav aria-label="Main" className="flex-1 overflow-y-auto px-2 py-2">
      {NAV.map((section, i) => {
        const items = section.items.filter(
          (item) =>
            !item.permission || me.permissions.includes(item.permission),
        );
        if (!items.length) return null;
        return (
          <div key={section.label ?? i} className="mb-4">
            {section.label && (
              <p className="slug px-2.5 pb-1.5 text-muted-foreground">
                {section.label}
              </p>
            )}
            <ul className="grid gap-0.5">
              {items.map((item) => {
                const Icon = item.icon;
                if (item.comingIn) {
                  return (
                    <li key={item.href}>
                      <Tooltip>
                        <TooltipTrigger
                          render={
                            <span
                              aria-disabled="true"
                              tabIndex={0}
                              className={cn(
                                itemClass,
                                "cursor-default text-muted-foreground/70",
                              )}
                            />
                          }
                        >
                          <Icon />
                          <span className="flex-1">{item.label}</span>
                          <span className="slug rounded-sm bg-muted px-1.5 text-[10px] text-muted-foreground">
                            Soon
                          </span>
                        </TooltipTrigger>
                        <TooltipContent side="right">
                          Arrives in {item.comingIn}
                        </TooltipContent>
                      </Tooltip>
                    </li>
                  );
                }
                return (
                  <NavLink
                    key={item.href}
                    item={item}
                    current={current}
                    onNavigate={onNavigate}
                  />
                );
              })}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

function NavLink({
  item,
  current,
  onNavigate,
}: {
  item: NavItem;
  current: string | undefined;
  onNavigate?: () => void;
}) {
  const children = item.children ?? [];
  const inside = children.some((c) => c.href === current);
  // Open while you're on one of its pages; otherwise it's the reader's choice.
  const [open, setOpen] = useState(inside);
  const expanded = open || inside;
  const active = item.href === current;
  const link = (entry: NavItem, isActive: boolean, child = false) => (
    <Link
      href={entry.href}
      aria-current={isActive ? "page" : undefined}
      onClick={onNavigate}
      className={cn(
        itemClass,
        "flex-1",
        child && "h-8 text-[13px] pointer-coarse:h-11",
        isActive
          ? "bg-sidebar-primary font-medium text-sidebar-primary-foreground [&_svg]:text-flash"
          : "text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
      )}
    >
      <entry.icon />
      {entry.label}
    </Link>
  );

  if (!children.length) return <li>{link(item, active)}</li>;
  const listId = `nav-${item.href.replaceAll("/", "-")}`;
  return (
    <li>
      <div className="flex items-center gap-0.5">
        {link(item, active)}
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={listId}
          aria-label={`${expanded ? "Hide" : "Show"} ${item.label} pages`}
          onClick={() => setOpen(!expanded)}
          className="grid size-9 shrink-0 place-items-center rounded-sm text-muted-foreground outline-none hover:bg-sidebar-accent hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 pointer-coarse:size-11"
        >
          <ChevronDownIcon
            aria-hidden
            className={cn(
              "size-4 transition-transform",
              expanded && "rotate-180",
            )}
          />
        </button>
      </div>
      {expanded && (
        <ul
          id={listId}
          className="mt-0.5 ml-5 grid gap-0.5 border-l border-sidebar-border pl-1.5"
        >
          {children.map((c) => (
            <li key={c.href} className="flex">
              {link(c, c.href === current, true)}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
