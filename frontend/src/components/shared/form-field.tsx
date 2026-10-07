import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export function FormField({
  id,
  label,
  hint,
  error,
  className,
  action,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string;
  className?: string;
  /** Small control shown at the end of the label row (e.g. "Forgot password?"). */
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("grid gap-1.5", className)}>
      {action ? (
        <div className="flex items-center justify-between gap-2">
          <Label htmlFor={id}>{label}</Label>
          {action}
        </div>
      ) : (
        <Label htmlFor={id}>{label}</Label>
      )}
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/** aria props wiring an input to its FormField message. */
export function fieldAria(id: string, error?: string) {
  return {
    id,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": error ? `${id}-error` : undefined,
  } as const;
}
