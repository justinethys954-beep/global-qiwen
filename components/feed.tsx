"use client";

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Payload, Story } from "@/lib/types";
import { cn } from "@/lib/utils";

const EMPTY_REGIONS: Payload["regions"] = [];
const EMPTY_STORIES: Story[] = [];

const TINT: Record<string, string> = {
  非洲: "bg-[#e5f0cf] text-[#3f6212]",
  印度: "bg-[#f6e2c4] text-[#9a3412]",
  菲律宾: "bg-[#fde2e4] text-[#9f1239]",
  巴基斯坦: "bg-[#d7efe4] text-[#115e59]",
  部落: "bg-[#efe2cc] text-[#78350f]",
  其他: "bg-[#e7e5e4] text-[#44403c]",
  猎奇: "bg-[#ffedd5] text-[#c2410c]",
  离谱: "bg-[#ffe4e6] text-[#be123c]",
  温情: "bg-[#f5f5f4] text-[#78716c]",
};

const TASTE_ORDER = ["离谱", "猎奇", "温情"];

function tint(tag: string) {
  return TINT[tag] ?? "bg-secondary text-secondary-foreground";
}

function formatWhen(iso: string | null) {
  if (!iso) return "时间不详";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "时间不详";
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startThat = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const days = Math.round((startToday.getTime() - startThat.getTime()) / 86400000);
  const time = new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(date);
  if (days === 0) return `今天 ${time}`;
  if (days === 1) return `昨天 ${time}`;
  if (days > 1 && days < 8) return `${days} 天前`;
  return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(date);
}

function StoryCard({ story }: { story: Story }) {
  const [imageOk, setImageOk] = useState(true);
  const rawTags = story.tags?.length ? story.tags : [story.region || "其他"];
  const tags = [
    ...TASTE_ORDER.filter((tag) => rawTags.includes(tag)),
    ...rawTags.filter((tag) => !TASTE_ORDER.includes(tag)),
  ];
  const summary =
    story.summaryZh && story.summaryZh !== story.titleZh ? story.summaryZh : "";

  return (
    <article className="group flex flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-[0_1px_0_rgba(28,25,23,0.04)]">
      <a
        href={story.url}
        target="_blank"
        rel="noopener noreferrer"
        className="relative block aspect-[16/10] overflow-hidden bg-[#efe6d6]"
      >
        {imageOk ? (
          <img
            src={story.image}
            alt={story.titleZh || story.title}
            referrerPolicy="no-referrer"
            loading="lazy"
            onError={() => setImageOk(false)}
            className="h-full w-full object-cover transition duration-300 group-hover:scale-[1.03]"
          />
        ) : (
          <div className="flex h-full items-center justify-center px-6 text-center text-sm text-muted-foreground">
            主图没加载出来
            <br />
            原文里仍有图
          </div>
        )}
        <span className="absolute left-3 top-3 flex flex-wrap gap-1">
          {tags.map((tag) => (
            <Badge key={tag} className={cn("border-transparent", tint(tag))}>
              {tag}
            </Badge>
          ))}
        </span>
      </a>
      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
          <span className="truncate">{story.sourceNameZh || story.sourceName}</span>
          <time dateTime={story.publishedAt || story.fetchedAt}>{formatWhen(story.publishedAt)}</time>
        </div>
        <h2 className="line-clamp-3 font-serif text-[1.15rem] font-semibold leading-snug tracking-tight">
          <a href={story.url} target="_blank" rel="noopener noreferrer" className="hover:text-[#c2410c]">
            {story.titleZh}
          </a>
        </h2>
        {summary ? <p className="line-clamp-4 text-sm leading-6 text-stone-700">{summary}</p> : null}
        <p className="line-clamp-2 text-xs leading-5 text-stone-400">{story.title}</p>
        <div className="mt-auto flex items-center justify-between gap-3 pt-1">
          <a
            href={story.url}
            target="_blank"
            rel="noopener noreferrer"
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            阅读原文
          </a>
          {story.discussionUrl ? (
            <a
              href={story.discussionUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-muted-foreground underline-offset-4 hover:underline"
            >
              讨论帖
            </a>
          ) : null}
        </div>
      </div>
    </article>
  );
}

export default function Feed({ data }: { data: Payload | null }) {
  const [taste, setTaste] = useState("猎奇");
  const [region, setRegion] = useState("全部");
  const [source, setSource] = useState("全部");
  const [query, setQuery] = useState("");

  const regions = data?.regions ?? EMPTY_REGIONS;
  const stories = data?.stories ?? EMPTY_STORIES;

  const matchesTaste = (tags: string[]) => {
    if (taste === "全部") return true;
    if (taste === "猎奇") return tags.includes("猎奇") || tags.includes("离谱");
    return tags.includes(taste);
  };

  const tasteCounts = useMemo(() => {
    const map = new Map<string, number>();
    for (const story of stories) {
      const tags = story.tags?.length ? story.tags : [];
      if (tags.includes("猎奇") || tags.includes("离谱")) map.set("猎奇", (map.get("猎奇") ?? 0) + 1);
      if (tags.includes("离谱")) map.set("离谱", (map.get("离谱") ?? 0) + 1);
      if (tags.includes("温情")) map.set("温情", (map.get("温情") ?? 0) + 1);
    }
    return map;
  }, [stories]);

  const counts = useMemo(() => {
    const map = new Map<string, number>();
    for (const name of regions.map((item) => item.nameZh)) map.set(name, 0);
    for (const story of stories) {
      const tags = story.tags?.length ? story.tags : [story.region];
      if (!matchesTaste(tags)) continue;
      for (const tag of tags) map.set(tag, (map.get(tag) ?? 0) + 1);
    }
    return map;
  }, [regions, stories, taste]);

  const visibleSources = useMemo(() => {
    const ids = new Set<string>();
    for (const story of stories) {
      const tags = story.tags?.length ? story.tags : [story.region];
      if (!matchesTaste(tags)) continue;
      if (region !== "全部" && !tags.includes(region)) continue;
      ids.add(story.sourceId);
    }
    return (data?.sources ?? []).filter((item) => ids.has(item.id) && item.lastStatus === "ok");
  }, [data, region, stories, taste]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return stories
      .filter((story) => {
      const tags = story.tags?.length ? story.tags : [story.region];
      if (!matchesTaste(tags)) return false;
      if (region !== "全部" && !tags.includes(region)) return false;
      if (source !== "全部" && story.sourceId !== source) return false;
      if (!needle) return true;
      const hay = `${story.titleZh} ${story.summaryZh} ${story.title} ${story.summary} ${story.sourceNameZh} ${story.sourceName}`.toLowerCase();
      return hay.includes(needle);
    })
      .sort((a, b) => (b.tasteScore ?? 0) - (a.tasteScore ?? 0));
  }, [query, region, source, stories, taste]);

  const failed = (data?.sources ?? []).filter((item) => item.lastStatus !== "ok");
  const updated = data?.generatedAt
    ? new Intl.DateTimeFormat("zh-CN", {
        month: "long",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(data.generatedAt))
    : "";

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col px-4 pb-16 pt-6 sm:px-6">
      <header className="border-b border-border pb-6">
        <div className="flex items-start gap-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-[#c2410c] font-serif text-2xl text-[#fffaf3]">
            奇
          </div>
          <div>
            <p className="text-xs font-medium tracking-[0.22em] text-[#c2410c]">新奇特</p>
            <h1 className="font-serif text-4xl font-semibold tracking-tight sm:text-5xl">全球奇闻</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-stone-600 sm:text-base">
              非洲、印度、菲律宾、巴基斯坦和部落的稿子都还在。打开先看猎奇和离谱，暖心动物和节日祝福往后放。
            </p>
          </div>
        </div>
        {data ? (
          <p className="mt-4 text-sm text-muted-foreground">
            {stories.length} 条 · 更新于 {updated}
          </p>
        ) : null}
      </header>

      {!data ? (
        <section className="mt-10 rounded-2xl border border-dashed border-border bg-card px-6 py-16 text-center">
          <h2 className="font-serif text-2xl">还没有条目</h2>
          <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-muted-foreground">
            页面要读 <code className="rounded bg-secondary px-1.5 py-0.5">/data/stories.json</code>
            。本地先跑一次 <code className="rounded bg-secondary px-1.5 py-0.5">python3 scripts/update.py</code>
            ，再 <code className="rounded bg-secondary px-1.5 py-0.5">npm run build</code>。
          </p>
        </section>
      ) : (
        <>
          <div className="sticky top-0 z-10 -mx-4 mt-4 border-b border-border/80 bg-[#f4efe4]/90 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
            <div className="flex gap-2 overflow-x-auto pb-1" role="group" aria-label="口味">
              {(
                [
                  ["猎奇", "猎奇"],
                  ["离谱", "只看离谱"],
                  ["全部", "全部口味"],
                  ["温情", "温情"],
                ] as const
              ).map(([id, label]) => (
                <Button
                  key={id}
                  type="button"
                  size="sm"
                  variant={taste === id ? "default" : "outline"}
                  aria-pressed={taste === id}
                  onClick={() => setTaste(id)}
                >
                  {label}
                  {id !== "全部" ? ` ${tasteCounts.get(id) ?? 0}` : ""}
                </Button>
              ))}
            </div>
            <div className="mt-2 flex gap-2 overflow-x-auto pb-1" role="group" aria-label="地区">
              <Button
                type="button"
                size="sm"
                variant={region === "全部" ? "default" : "outline"}
                aria-pressed={region === "全部"}
                onClick={() => {
                  setRegion("全部");
                  setSource("全部");
                }}
              >
                全部 {stories.length}
              </Button>
              {regions.map((item) => (
                <Button
                  key={item.id}
                  type="button"
                  size="sm"
                  variant={region === item.nameZh ? "default" : "outline"}
                  aria-pressed={region === item.nameZh}
                  onClick={() => {
                    setRegion(item.nameZh);
                    setSource("全部");
                  }}
                >
                  {item.nameZh} {counts.get(item.nameZh) ?? 0}
                </Button>
              ))}
            </div>
            <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center">
              <label className="sr-only" htmlFor="source-filter">
                来源
              </label>
              <select
                id="source-filter"
                value={source}
                onChange={(event) => setSource(event.target.value)}
                className="h-10 rounded-md border border-input bg-background px-3 text-sm sm:w-64"
              >
                <option value="全部">全部来源</option>
                {visibleSources.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.nameZh}
                  </option>
                ))}
              </select>
              <label className="sr-only" htmlFor="search">
                搜索
              </label>
              <Input
                id="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜标题、概要、来源"
              />
            </div>
          </div>

          <p className="mt-4 text-sm text-muted-foreground" aria-live="polite">
            显示 {visible.length} 条
          </p>

          {visible.length === 0 ? (
            <section className="mt-6 rounded-2xl border border-dashed border-border bg-card px-6 py-14 text-center">
              <h2 className="font-serif text-2xl">这个筛选下是空的</h2>
              <p className="mt-2 text-sm text-muted-foreground">换个地区，或把搜索清掉。</p>
            </section>
          ) : (
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {visible.map((story) => (
                <StoryCard key={story.id} story={story} />
              ))}
            </div>
          )}

          {failed.length > 0 ? (
            <details className="mt-10 text-sm text-muted-foreground">
              <summary className="cursor-pointer">这次有 {failed.length} 个来源没抓到</summary>
              <ul className="mt-3 space-y-1">
                {failed.map((item) => (
                  <li key={item.id}>
                    {item.nameZh}：{item.lastError || item.lastStatus}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </>
      )}

      <footer className="mt-12 border-t border-border pt-6 text-xs leading-6 text-muted-foreground">
        <p>
          图片是来源站点的原链接，页面只引用、不另存原图。标题和导语取自公开 RSS 或列表页，中文由机器翻译，以原文为准。
        </p>
        <p className="mt-2">
          想加一个国家或一块地区，在 sources.json 里加一条来源，region 用 africa、india、philippines、pakistan、tribe、other。
          每天跑 <code>python3 scripts/update.py</code> 会按原文链接去重，已经译过的不会再译一遍。
        </p>
      </footer>
    </div>
  );
}
