"use client";

import { MenuIcon } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Logo } from "@/components/shared/logo";
import { SidebarNav } from "@/components/shell/sidebar-nav";
import { UserMenu } from "@/components/shell/user-menu";
import { WelcomeTour } from "@/components/shell/welcome-tour";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, getActiveOrgId, setActiveOrgId } from "@/lib/api";
import { signOutEverywhere, useMe } from "@/lib/auth";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const me = useMe();
  const [mobileOpen, setMobileOpen] = useState(false);

  const unauthenticated = me.error instanceof ApiError && me.error.status === 401;
  // Wait for any refetch: cached data may predate a just-created organization.
  const needsOrganization = me.data && !me.data.organization_id && !me.isFetching;

  useEffect(() => {
    if (unauthenticated) {
      // Clear stale/expired sessions first, or the proxy would bounce /login back here.
      signOutEverywhere().finally(() => router.replace(`/login?next=${encodeURIComponent(pathname)}`));
    } else if (needsOrganization) {
      router.replace("/onboarding");
    } else if (me.data?.organization_id) {
      // Only repair a missing/foreign stored org. Comparing against
      // me.organization_id would undo a switch whose refetch is in flight.
      const stored = getActiveOrgId();
      if (!stored || !me.data.memberships.some((m) => m.organization_id === stored)) {
        setActiveOrgId(me.data.organization_id);
      }
    }
  }, [unauthenticated, needsOrganization, me.data, pathname, router]);

  if (!me.data?.organization_id) {
    return me.isError && !unauthenticated ? <ShellError onRetry={() => me.refetch()} /> : <ShellSkeleton />;
  }

  return (
    <div className="flex min-h-svh">
      <aside className="sticky top-0 hidden h-svh w-64 shrink-0 flex-col border-r bg-sidebar lg:flex">
        <div className="flex h-14 items-center px-4">
          <Logo />
        </div>
        <SidebarNav me={me.data} />
        <div className="border-t p-2">
          <UserMenu me={me.data} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background/90 px-4 backdrop-blur lg:hidden">
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger render={<Button variant="ghost" size="icon" aria-label="Open navigation" />}>
              <MenuIcon />
            </SheetTrigger>
            <SheetContent side="left" className="flex w-72 flex-col gap-0 bg-sidebar p-0">
              <SheetHeader className="h-14 justify-center px-4">
                <SheetTitle>
                  <Logo />
                </SheetTitle>
              </SheetHeader>
              <SidebarNav me={me.data} onNavigate={() => setMobileOpen(false)} />
              <div className="border-t p-2">
                <UserMenu me={me.data} />
              </div>
            </SheetContent>
          </Sheet>
          <Logo />
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 lg:px-10">{children}</main>
        <WelcomeTour me={me.data} />
      </div>
    </div>
  );
}

function ShellSkeleton() {
  return (
    <div className="flex min-h-svh" aria-busy="true" aria-label="Loading">
      <div className="hidden w-64 border-r bg-sidebar p-4 lg:block">
        <Skeleton className="h-7 w-36" />
        <div className="mt-8 grid gap-2">
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton key={i} className="h-7 w-full" />
          ))}
        </div>
      </div>
      <div className="flex-1 p-10">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="mt-3 h-4 w-96 max-w-full" />
      </div>
    </div>
  );
}

function ShellError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="grid min-h-svh place-items-center p-6 text-center">
      <div className="grid max-w-sm gap-3">
        <h1 className="text-lg font-semibold">We couldn&apos;t load your workspace</h1>
        <p className="text-sm text-muted-foreground">
          The server didn&apos;t respond. Check that the API is running, then try again.
        </p>
        <Button onClick={onRetry} className="justify-self-center">
          Try again
        </Button>
      </div>
    </div>
  );
}
