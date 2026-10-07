"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { NAV } from "@/components/shell/nav";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { Me } from "@/types/api";

const itemClass =
  "flex h-9 items-center gap-2.5 rounded-sm px-2.5 text-sm transition-colors pointer-coarse:h-11 [&_svg]:size-4 [&_svg]:shrink-0";

export function SidebarNav({ me, onNavigate }: { me: Me; onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <nav aria-label="Main" className="flex-1 overflow-y-auto px-2 py-2">
      {NAV.map((section, i) => {
        const items = section.items.filter(
          (item) => !item.permission || me.permissions.includes(item.permission),
        );
        if (!items.length) return null;
        return (
          <div key={section.label ?? i} className="mb-4">
            {section.label && (
              <p className="slug px-2.5 pb-1.5 text-muted-foreground">{section.label}</p>
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
                              className={cn(itemClass, "cursor-default text-muted-foreground/70")}
                            />
                          }
                        >
                          <Icon />
                          <span className="flex-1">{item.label}</span>
                          <span className="slug rounded-sm bg-muted px-1.5 text-[10px] text-muted-foreground">
                            Soon
                          </span>
                        </TooltipTrigger>
                        <TooltipContent side="right">Arrives in {item.comingIn}</TooltipContent>
                      </Tooltip>
                    </li>
                  );
                }
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      onClick={onNavigate}
                      className={cn(
                        itemClass,
                        active
                          ? "bg-sidebar-primary font-medium text-sidebar-primary-foreground [&_svg]:text-flash"
                          : "text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                      )}
                    >
                      <Icon />
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}
