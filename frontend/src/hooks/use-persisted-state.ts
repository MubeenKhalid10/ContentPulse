"use client";

import { type Dispatch, type SetStateAction, useCallback, useEffect, useState } from "react";

/**
 * useState that survives navigating away and back (kept per browser tab), so a
 * list returns to the tab and filters the user left it on. The saved value is
 * restored after mount to keep server and client markup identical.
 */
export function usePersistedState<T extends object>(key: string, initial: T): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(initial);

  useEffect(() => {
    try {
      const saved = window.sessionStorage.getItem(`cp:${key}`);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (saved) setValue((current) => ({ ...current, ...JSON.parse(saved) }));
    } catch {
      // Storage unavailable or corrupt: keep the default.
    }
  }, [key]);

  const set: Dispatch<SetStateAction<T>> = useCallback(
    (next) => {
      setValue((current) => {
        const resolved = typeof next === "function" ? (next as (v: T) => T)(current) : next;
        try {
          window.sessionStorage.setItem(`cp:${key}`, JSON.stringify(resolved));
        } catch {
          // Not persisted; the page still works.
        }
        return resolved;
      });
    },
    [key],
  );

  return [value, set];
}
