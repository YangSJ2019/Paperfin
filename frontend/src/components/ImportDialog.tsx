import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link as LinkIcon, Loader2, X } from "lucide-react";

import { api, ApiError, type ImportUrlResponse } from "../lib/api";
import { clsx } from "../lib/utils";

interface Props {
  open: boolean;
  onClose: () => void;
}

/**
 * Modal for importing a paper by URL (arXiv link or direct PDF URL).
 *
 * The backend accepts the URL, does a synchronous validation + dedup check,
 * and returns one of:
 *   - "queued"        — background task running; papers list will update soon
 *   - "deduplicated"  — paper already in library; no work done
 *   - 400 error       — URL is obviously bad (empty, wrong scheme, etc.)
 *
 * On success (queued or deduplicated) we close the modal and refetch papers.
 * For "queued" we schedule a second refetch after 45s — that's roughly when
 * the LLM round-trip finishes, so the new paper pops into view without the
 * user having to manually reload.
 */
export function ImportDialog({ open, onClose }: Props) {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  const mutation = useMutation({
    mutationFn: (u: string) => api.importUrl(u),
    onSuccess: (data: ImportUrlResponse) => {
      queryClient.invalidateQueries({ queryKey: ["papers"] });
      if (data.status === "queued") {
        // Give the background pipeline a chance to finish, then refetch so
        // the new poster appears without a manual refresh.
        window.setTimeout(
          () => queryClient.invalidateQueries({ queryKey: ["papers"] }),
          45_000,
        );
      }
      setUrl("");
      onClose();
    },
  });

  // Reset state each time the modal opens, autofocus the input.
  useEffect(() => {
    if (open) {
      mutation.reset();
      setUrl("");
      // Defer focus until the element is on-screen.
      window.requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  // Esc to close.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !mutation.isPending) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, mutation.isPending]);

  if (!open) return null;

  const errorMessage =
    mutation.error instanceof ApiError
      ? mutation.error.detail
      : mutation.error instanceof Error
        ? mutation.error.message
        : null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = url.trim();
    if (!trimmed || mutation.isPending) return;
    mutation.mutate(trimmed);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="import-dialog-title"
      // Backdrop: click to close (unless busy).
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 backdrop-blur-sm p-4 pt-[15vh]"
      onClick={() => !mutation.isPending && onClose()}
    >
      <div
        // Stop clicks inside the panel from bubbling up to the backdrop.
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-xl overflow-hidden rounded-2xl bg-ink-800 shadow-2xl ring-1 ring-white/10"
      >
        <div className="flex items-center justify-between border-b border-white/5 px-5 py-3">
          <h2
            id="import-dialog-title"
            className="flex items-center gap-2 text-sm font-semibold text-white"
          >
            <LinkIcon className="h-4 w-4 text-accent-soft" />
            Import paper from URL
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={mutation.isPending}
            className="rounded-md p-1 text-slate-400 transition hover:bg-white/5 hover:text-white disabled:opacity-50"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 px-5 py-4">
          <div>
            <label htmlFor="url-input" className="mb-1 block text-xs font-medium text-slate-400">
              arXiv link or direct PDF URL
            </label>
            <input
              id="url-input"
              ref={inputRef}
              type="url"
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://arxiv.org/abs/2005.11401"
              disabled={mutation.isPending}
              className="w-full rounded-lg border border-white/10 bg-ink-900 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-accent focus:outline-none disabled:opacity-60"
            />
            <p className="mt-2 text-xs text-slate-500">
              Works with <code className="text-slate-400">arxiv.org/abs/…</code>,{" "}
              <code className="text-slate-400">arxiv.org/pdf/…</code>, or any HTTPS URL ending in a
              PDF. Processing takes 20–40 seconds after you submit.
            </p>
          </div>

          {errorMessage && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
              {errorMessage}
            </div>
          )}

          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={mutation.isPending}
              className="rounded-lg px-3 py-2 text-sm text-slate-300 transition hover:bg-white/5 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={mutation.isPending || !url.trim()}
              className={clsx(
                "inline-flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white shadow transition",
                "hover:bg-accent-soft disabled:opacity-60",
              )}
            >
              {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {mutation.isPending ? "Importing…" : "Import"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
