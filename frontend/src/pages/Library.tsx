import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, RefreshCw, Search, SortDesc } from "lucide-react";

import { api } from "../lib/api";
import { PaperCard } from "../components/PaperCard";
import { ImportDialog } from "../components/ImportDialog";
import { clsx } from "../lib/utils";

type SortKey = "recent" | "score" | "title";

export default function Library() {
  const queryClient = useQueryClient();

  const [sort, setSort] = useState<SortKey>("recent");
  const [minScore, setMinScore] = useState(0);
  const [search, setSearch] = useState("");
  const [importOpen, setImportOpen] = useState(false);

  const { data: papers = [], isLoading, isError } = useQuery({
    queryKey: ["papers", { sort, minScore }],
    queryFn: () => api.listPapers({ sort, minScore }),
  });

  const scanMutation = useMutation({
    mutationFn: api.triggerScan,
    onSuccess: () => {
      // Give the background job a moment before refetching.
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ["papers"] }), 2500);
    },
  });

  const filtered = papers.filter((p) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      p.title.toLowerCase().includes(q) ||
      p.authors.toLowerCase().includes(q) ||
      p.tags.some((t) => t.toLowerCase().includes(q))
    );
  });

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search title, author, or tag…"
            className="w-full rounded-lg border border-white/10 bg-ink-800 py-2 pl-9 pr-3 text-sm text-white placeholder:text-slate-500 focus:border-accent focus:outline-none"
          />
        </div>

        <label className="flex items-center gap-2 text-sm text-slate-400">
          <SortDesc className="h-4 w-4" />
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            className="rounded-lg border border-white/10 bg-ink-800 px-2 py-1.5 text-sm text-white focus:border-accent focus:outline-none"
          >
            <option value="recent">Recent</option>
            <option value="score">Score</option>
            <option value="title">Title</option>
          </select>
        </label>

        <label className="flex items-center gap-2 text-sm text-slate-400">
          Min score
          <input
            type="number"
            min={0}
            max={100}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
            className="w-16 rounded-lg border border-white/10 bg-ink-800 px-2 py-1.5 text-sm text-white focus:border-accent focus:outline-none"
          />
        </label>

        <button
          type="button"
          onClick={() => setImportOpen(true)}
          title="Import from URL"
          aria-label="Import from URL"
          className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-ink-800 px-3 py-2 text-sm font-medium text-slate-200 transition hover:border-accent hover:text-white"
        >
          <Plus className="h-4 w-4" />
          Import URL
        </button>

        <button
          onClick={() => scanMutation.mutate()}
          disabled={scanMutation.isPending}
          className={clsx(
            "inline-flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white shadow transition",
            "hover:bg-accent-soft disabled:opacity-60"
          )}
        >
          <RefreshCw
            className={clsx("h-4 w-4", scanMutation.isPending && "animate-spin")}
          />
          Scan library
        </button>
      </div>

      <ImportDialog open={importOpen} onClose={() => setImportOpen(false)} />

      {isLoading && <p className="text-slate-400">Loading…</p>}
      {isError && (
        <p className="text-red-400">
          Failed to load papers. Is the backend running on port 8000?
        </p>
      )}
      {!isLoading && filtered.length === 0 && (
        <div className="rounded-xl border border-dashed border-white/10 p-10 text-center text-slate-400">
          No papers yet. Drop some PDFs into{" "}
          <code className="rounded bg-black/30 px-1 py-0.5 text-slate-200">
            backend/data/papers/
          </code>{" "}
          and click <strong>Scan library</strong>.
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
        {filtered.map((p) => (
          <PaperCard key={p.id} paper={p} />
        ))}
      </div>
    </div>
  );
}
