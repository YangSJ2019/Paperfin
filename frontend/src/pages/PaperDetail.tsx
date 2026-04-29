import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Radar,
  RadarChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  ResponsiveContainer,
} from "recharts";
import { ArrowLeft, ExternalLink, FileText, RefreshCw } from "lucide-react";

import { api } from "../lib/api";
import { clsx } from "../lib/utils";

function RadarPanel({
  affiliation,
  fame,
  venue,
  llm,
}: {
  affiliation: number;
  fame: number;
  venue: number;
  llm: number;
}) {
  // Axis labels reflect what each score actually measures today:
  //  - llm: LLM-rubric content/quality score (currently the main signal)
  //  - affiliation / fame / venue: placeholders until we wire in
  //    Semantic Scholar + institution whitelist (M3).
  const data = [
    { axis: "内容质量", value: llm },
    { axis: "作者影响", value: fame },
    { axis: "机构声望", value: affiliation },
    { axis: "发表场合", value: venue },
  ];
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer>
        <RadarChart data={data} outerRadius="75%">
          <PolarGrid stroke="#374151" />
          <PolarAngleAxis dataKey="axis" stroke="#94a3b8" tick={{ fontSize: 12 }} />
          <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
          <Radar
            dataKey="value"
            stroke="#a78bfa"
            fill="#7c3aed"
            fillOpacity={0.45}
            isAnimationActive={false}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function PaperDetail() {
  const { id } = useParams();
  const paperId = Number(id);
  const queryClient = useQueryClient();

  const { data: paper, isLoading, isError } = useQuery({
    queryKey: ["paper", paperId],
    queryFn: () => api.getPaper(paperId),
    enabled: Number.isFinite(paperId),
  });

  // Re-run the summarizer. Refetches the paper itself, plus the library list
  // so tags that may have changed are reflected on the poster wall too.
  const resummarizeMutation = useMutation({
    mutationFn: () => api.resummarizePaper(paperId),
    onSuccess: () => {
      // The background task takes ~15-30s; poll twice to catch it.
      const refetch = () => {
        queryClient.invalidateQueries({ queryKey: ["paper", paperId] });
        queryClient.invalidateQueries({ queryKey: ["papers"] });
      };
      window.setTimeout(refetch, 15_000);
      window.setTimeout(refetch, 35_000);
    },
  });

  if (isLoading) return <p className="text-slate-400">Loading…</p>;
  if (isError || !paper)
    return <p className="text-red-400">Could not load this paper.</p>;

  return (
    <div className="space-y-6">
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-sm text-slate-400 hover:text-white"
      >
        <ArrowLeft className="h-4 w-4" /> Back to library
      </Link>

      <header className="flex flex-col gap-4 lg:flex-row lg:items-start">
        {paper.has_thumbnail && (
          <img
            src={api.thumbnailUrl(paper.id)}
            alt=""
            className="h-64 w-auto flex-shrink-0 rounded-lg object-cover shadow-xl ring-1 ring-white/10"
          />
        )}
        <div className="flex-1">
          <h1 className="text-2xl font-semibold leading-tight">{paper.title}</h1>
          <p className="mt-1 text-sm text-slate-400">{paper.authors || "Unknown authors"}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {paper.venue && (
              <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-slate-300">
                {paper.venue}
              </span>
            )}
            {paper.arxiv_id && (
              <a
                href={`https://arxiv.org/abs/${paper.arxiv_id}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-full bg-white/5 px-2 py-0.5 text-xs text-slate-300 hover:bg-white/10"
              >
                arXiv:{paper.arxiv_id} <ExternalLink className="h-3 w-3" />
              </a>
            )}
            {paper.doi && (
              <a
                href={`https://doi.org/${paper.doi}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-full bg-white/5 px-2 py-0.5 text-xs text-slate-300 hover:bg-white/10"
              >
                DOI <ExternalLink className="h-3 w-3" />
              </a>
            )}
            <span className="rounded-full bg-accent/20 px-2 py-0.5 text-xs font-semibold text-accent-soft">
              评分 {Math.round(paper.score)}
            </span>
          </div>
          {paper.tags.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1">
              {paper.tags.map((t) => (
                <span
                  key={t}
                  className="rounded bg-white/5 px-2 py-0.5 text-[11px] uppercase tracking-wide text-slate-300"
                >
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section className="space-y-4 lg:col-span-2">
          <div className="rounded-xl bg-ink-800/60 p-5 ring-1 ring-white/5">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-accent-soft">
              贡献
            </h2>
            <p className="text-sm leading-relaxed text-slate-200">
              {paper.summary_contribution || "—"}
            </p>
          </div>
          <div className="rounded-xl bg-ink-800/60 p-5 ring-1 ring-white/5">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-accent-soft">
              方法
            </h2>
            <p className="text-sm leading-relaxed text-slate-200">
              {paper.summary_method || "—"}
            </p>
          </div>
          <div className="rounded-xl bg-ink-800/60 p-5 ring-1 ring-white/5">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-accent-soft">
              结果
            </h2>
            <p className="text-sm leading-relaxed text-slate-200">
              {paper.summary_result || "—"}
            </p>
          </div>
          {paper.abstract && (
            <div className="rounded-xl bg-ink-800/40 p-5 ring-1 ring-white/5">
              <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">
                摘要
              </h2>
              <p className="whitespace-pre-line text-sm leading-relaxed text-slate-300">
                {paper.abstract}
              </p>
            </div>
          )}
        </section>

        <aside className="space-y-4">
          <div className="rounded-xl bg-ink-800/60 p-5 ring-1 ring-white/5">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-accent-soft">
              质量评分
            </h2>
            <RadarPanel
              affiliation={paper.score_affiliation}
              fame={paper.score_author_fame}
              venue={paper.score_venue}
              llm={paper.score_llm}
            />
            <p className="mt-2 text-xs leading-relaxed text-slate-500">
              当前综合分 = 内容质量分(LLM 评审)。作者影响 / 机构声望 / 发表场合
              三项待接入 Semantic Scholar 数据后自动填充。
            </p>
          </div>
          {paper.has_pdf && (
            <a
              href={api.pdfUrl(paper.id)}
              target="_blank"
              rel="noreferrer"
              className="flex items-center justify-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-white shadow hover:bg-accent-soft"
            >
              <FileText className="h-4 w-4" /> Open PDF
            </a>
          )}
          {paper.has_pdf && (
            <button
              type="button"
              onClick={() => resummarizeMutation.mutate()}
              disabled={resummarizeMutation.isPending}
              title="Re-run the LLM summarizer (e.g. to switch language or refresh a bad summary)"
              className={clsx(
                "flex items-center justify-center gap-2 rounded-lg border border-white/10 bg-ink-800 px-3 py-2 text-sm font-medium text-slate-200 transition",
                "hover:border-accent hover:text-white disabled:opacity-60",
              )}
            >
              <RefreshCw
                className={clsx(
                  "h-4 w-4",
                  resummarizeMutation.isPending && "animate-spin",
                )}
              />
              {resummarizeMutation.isPending
                ? "重新总结中…"
                : resummarizeMutation.isSuccess
                  ? "已提交,15–30 秒后刷新"
                  : "重新总结"}
            </button>
          )}
        </aside>
      </div>

      {paper.has_pdf && (
        <section className="overflow-hidden rounded-xl bg-black ring-1 ring-white/5">
          <iframe
            src={api.pdfUrl(paper.id)}
            title={paper.title}
            className="h-[90vh] w-full"
          />
        </section>
      )}
    </div>
  );
}
