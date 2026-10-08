import { dayLabel } from "@/lib/format";

/** A list split under Today / Yesterday / date headings, in the order given. */
export function DayGroups<T>({
  items,
  dateOf,
  label,
  render,
  className = "grid gap-3",
}: {
  items: T[];
  dateOf: (item: T) => string;
  label: string;
  render: (item: T) => React.ReactNode;
  className?: string;
}) {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const day = dayLabel(dateOf(item));
    groups.set(day, [...(groups.get(day) ?? []), item]);
  }
  return (
    <div className="grid gap-6">
      {[...groups].map(([day, rows]) => (
        <section key={day} aria-label={day} className="grid gap-2">
          <h2 className="text-sm font-medium text-muted-foreground">{day}</h2>
          <ul aria-label={`${label}, ${day}`} className={className}>
            {rows.map(render)}
          </ul>
        </section>
      ))}
    </div>
  );
}
