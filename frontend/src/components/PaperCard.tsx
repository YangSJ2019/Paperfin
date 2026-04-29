import { Link } from "react-router-dom";
import { api, type PaperListItem } from "../lib/api";
import { clsx } from "../lib/utils";

interface Props {
  paper: PaperListItem;
}

/**
 * A single poster card: cover thumbnail fills the frame, metadata is rendered
 * as a gradient overlay that reveals fully on hover. Mirrors the Jellyfin
 * poster affordance – dense grids, strong visuals.
 */
export function PaperCard({ paper }: Props) {
  const scoreColor =
    paper.score >= 80 ? "bg-emerald-500" : paper.score >= 60 ? "bg-amber-500" : "bg-slate-500";

  return (
    <Link
      to={`/papers/${paper.id}`}
      className="group relative block overflow-hidden rounded-xl bg-ink-800 ring-1 ring-white/5 transition hover:ring-accent/60"
    >
      <div className="aspect-[3/4] w-full bg-ink-700">
        {paper.has_thumbnail ? (
          <img
            src={api.thumbnailUrl(paper.id)}
            alt={paper.title}
            loading="lazy"
            className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
          />
        ) : (
          <div className="flex h-full items-center justify-center p-4 text-center text-sm text-slate-500">
            {paper.title}
          </div>
        )}
      </div>

      {/* Score pill */}
      <div
        className={clsx(
          "absolute right-2 top-2 rounded-full px-2 py-0.5 text-xs font-semibold text-white shadow-lg",
          scoreColor
        )}
      >
        {Math.round(paper.score)}
      </div>

      {/* Metadata overlay */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/60 to-transparent p-3 pt-8">
        <h3 className="line-clamp-2 text-sm font-semibold leading-snug text-white">
          {paper.title}
        </h3>
        <p className="mt-1 line-clamp-1 text-xs text-slate-300">{paper.authors || "—"}</p>
        {paper.tags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {paper.tags.slice(0, 3).map((t) => (
              <span
                key={t}
                className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-200"
              >
                {t}
              </span>
            ))}
          </div>
        )}
      </div>
    </Link>
  );
}
