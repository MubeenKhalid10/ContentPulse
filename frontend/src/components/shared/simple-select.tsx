"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

export interface Option<T extends string = string> {
  value: T;
  label: string;
}

/** Single-value select over a flat option list. Never emits null. */
export function SimpleSelect<T extends string>({
  id,
  value,
  onChange,
  options,
  placeholder = "Select…",
  disabled,
  className,
  "aria-label": ariaLabel,
}: {
  id?: string;
  value: T | undefined;
  onChange: (value: T) => void;
  options: readonly Option<T>[];
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  "aria-label"?: string;
}) {
  return (
    <Select
      items={options}
      value={value ?? null}
      onValueChange={(next) => {
        if (next !== null) onChange(next as T);
      }}
      disabled={disabled}
    >
      <SelectTrigger id={id} aria-label={ariaLabel} className={cn("w-full", className)}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
