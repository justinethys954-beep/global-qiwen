"use client";

import { useEffect, useState } from "react";
import Feed from "@/components/feed";
import type { Payload } from "@/lib/types";

export default function StoriesApp() {
  const [data, setData] = useState<Payload | null | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
    fetch(`${base}/data/stories.json`, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error(String(response.status));
        return response.json() as Promise<Payload>;
      })
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (data === undefined) {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6">
        <div className="h-16 w-64 animate-pulse rounded-2xl bg-[#e7dcc8]" />
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, index) => (
            <div key={index} className="overflow-hidden rounded-2xl border border-border bg-card">
              <div className="aspect-[16/10] animate-pulse bg-[#efe6d6]" />
              <div className="space-y-3 p-4">
                <div className="h-3 w-24 animate-pulse rounded bg-[#efe6d6]" />
                <div className="h-5 w-4/5 animate-pulse rounded bg-[#efe6d6]" />
                <div className="h-12 animate-pulse rounded bg-[#efe6d6]" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return <Feed data={data} />;
}
