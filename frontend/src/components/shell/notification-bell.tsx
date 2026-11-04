"use client";

import { BellIcon } from "lucide-react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useMarkNotificationsRead, useNotifications } from "@/hooks/use-notifications";
import { dayLabel, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Approval news for this person: change requests, resubmissions, decisions, replies. */
export function NotificationBell() {
  const router = useRouter();
  const notifications = useNotifications();
  const markRead = useMarkNotificationsRead();
  const unread = notifications.data?.unread ?? 0;
  const items = notifications.data?.items ?? [];
  // Newest first, split under Today / Yesterday / date headings.
  const days = new Map<string, typeof items>();
  for (const n of items) {
    const day = dayLabel(n.created_at);
    days.set(day, [...(days.get(day) ?? []), n]);
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            size="icon"
            className="relative"
            aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
          />
        }
      >
        <BellIcon />
        {unread > 0 && (
          <span
            aria-hidden
            className="absolute -right-0.5 -top-0.5 grid min-w-4 place-items-center rounded-full bg-primary px-1 text-[10px] tabular-nums leading-4 text-primary-foreground"
          >
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-[28rem] w-80 overflow-y-auto">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="flex items-center justify-between">
            Notifications
            {unread > 0 && (
              <button
                type="button"
                className="text-xs font-normal text-primary hover:underline"
                onClick={() => markRead.mutate("all")}
              >
                Mark all read
              </button>
            )}
          </DropdownMenuLabel>
        </DropdownMenuGroup>
        {items.length === 0 && (
          <p className="px-2 py-6 text-center text-sm text-muted-foreground">Nothing new.</p>
        )}
        {[...days].map(([day, rows]) => (
          <DropdownMenuGroup key={day}>
            <DropdownMenuLabel className="text-xs text-muted-foreground">{day}</DropdownMenuLabel>
            {rows.map((n) => (
              <DropdownMenuItem
                key={n.id}
                className="items-start"
                onClick={() => {
                  if (!n.read_at) markRead.mutate(n.id);
                  router.push(n.link);
                }}
              >
                <span className="grid min-w-0 flex-1 gap-0.5 leading-snug">
                  <span className={cn("text-sm", !n.read_at && "font-medium")}>{n.title}</span>
                  {n.body && <span className="line-clamp-2 text-xs text-muted-foreground">{n.body}</span>}
                  <span className="text-xs text-muted-foreground">{timeAgo(n.created_at)}</span>
                </span>
                {!n.read_at && <span aria-label="Unread" className="mt-1.5 size-2 shrink-0 rounded-full bg-primary" />}
              </DropdownMenuItem>
            ))}
          </DropdownMenuGroup>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
