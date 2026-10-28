"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { SearchInput } from "@/components/shared/search-input";

export function TrendSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");
  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        const query = q.trim();
        // The Trends page keeps its filters in this tab's storage: hand it the query.
        try {
          const key = "cp:trends";
          const saved = JSON.parse(window.sessionStorage.getItem(key) ?? "{}");
          window.sessionStorage.setItem(
            key,
            JSON.stringify({ ...saved, q: query, status: "active" }),
          );
        } catch {
          // Storage unavailable: the Trends page opens unfiltered.
        }
        router.push("/trends");
      }}
    >
      <SearchInput
        aria-label="Search trends"
        placeholder="Search trends…"
        value={q}
        onChange={setQ}
        className="w-full sm:w-56"
      />
    </form>
  );
}

// --- Metric cards --------------------------------------------------------------------
