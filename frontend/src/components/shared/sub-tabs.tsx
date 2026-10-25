import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

/** A second row of tabs under a list's main tabs, with the number in each. */
export function SubTabs<T extends string>({
  label,
  value,
  onChange,
  items,
}: {
  label: string;
  value: T;
  onChange: (value: T) => void;
  items: { value: T; label: string; count?: number }[];
}) {
  return (
    <Tabs value={value} onValueChange={(v) => onChange(v as T)} aria-label={label}>
      <TabsList variant="line">
        {items.map((item) => (
          <TabsTrigger key={item.value} value={item.value}>
            {item.label}
            {item.count != null && item.count > 0 && (
              <span className="ml-1 rounded-full bg-muted px-1.5 text-[11px] tabular-nums text-muted-foreground">
                {item.count}
              </span>
            )}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
