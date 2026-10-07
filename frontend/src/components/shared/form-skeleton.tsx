import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function FormSkeleton({ fields = 4 }: { fields?: number }) {
  return (
    <Card aria-busy="true">
      <CardHeader>
        <Skeleton className="h-5 w-40" />
      </CardHeader>
      <CardContent className="grid gap-5">
        {Array.from({ length: fields }, (_, i) => (
          <div key={i} className="grid gap-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-8 w-full" />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

/** Sticky save bar shown under a form; hidden for read-only users. */
export function SaveBar({
  dirty,
  pending,
  onReset,
}: {
  dirty: boolean;
  pending: boolean;
  onReset: () => void;
}) {
  return (
    <div className="sticky bottom-0 -mx-1 mt-6 flex items-center justify-end gap-2 border-t bg-background/90 px-1 py-3 backdrop-blur">
      {dirty && <span className="mr-auto text-xs text-muted-foreground">Unsaved changes</span>}
      <Button type="button" variant="ghost" onClick={onReset} disabled={!dirty || pending}>
        Discard
      </Button>
      <Button type="submit" disabled={!dirty || pending}>
        {pending ? "Saving…" : "Save changes"}
      </Button>
    </div>
  );
}
