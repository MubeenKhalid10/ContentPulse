import { LockIcon } from "lucide-react";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b-[3px] border-double border-foreground pb-4">
      <div className="grid gap-1.5">
        <h1 className="headline text-4xl">{title}</h1>
        {description && <p className="max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function ReadOnlyNotice({ children }: { children?: React.ReactNode }) {
  return (
    <p className="mb-6 flex items-center gap-2 rounded-lg border border-dashed px-3 py-2 text-sm text-muted-foreground">
      <LockIcon className="size-4 shrink-0" />
      {children ?? "You can view this page. Only admins can make changes."}
    </p>
  );
}
