# Contributing to Paperfin

Thanks for your interest! Paperfin is an open-source project maintained by
Tencent. Issues and pull requests are welcome.

## Before you file a PR

- Discuss non-trivial changes in an issue first — especially anything that
  touches the data model, the LLM prompt contracts, or the public API
  surface. This saves everyone a round of rework.
- Every PR should be focused. If you're adding a feature and also fixing
  three unrelated typos, split it.
- New behaviour needs a smoke test path in the PR description: "here's the
  curl command that proves this works end-to-end."

## Local setup

See [README → Quick start](./README.md#quick-start). Short version:

```bash
# Backend
cd backend
cp .env.example .env      # fill in your LLM config
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

## Coding standards

### Backend (Python)

- **Python 3.11+** — we use modern union syntax (`int | None`, `list[str]`)
  and don't import `from __future__` anywhere except for TYPE_CHECKING.
- Every LLM call goes through `app/services/llm.chat_json`. Don't call the
  SDK directly from other modules — the wrapper handles retries, JSON
  parsing, and schema validation in one place.
- Every new piece of persisted state belongs in a SQLModel class under
  `app/models/` with an explicit migration story in the PR description
  (even if it's "wipe the DB, this is pre-1.0").
- Prefer `httpx` over `requests` (already a dep).
- Lint with `ruff` if you have it:
  ```bash
  cd backend && .venv/bin/ruff check .
  ```

### Frontend (TypeScript)

- **React 18 + TypeScript strict**. No `any` unless commented.
- Use `@tanstack/react-query` for server state; never `useEffect +
  setState` for data fetching.
- API calls go through `src/lib/api.ts` — don't scatter `fetch()` calls
  across components.
- Typecheck before pushing:
  ```bash
  cd frontend && npx tsc --noEmit
  ```

## Commit messages

Short imperative, explain the *why* not the *what*:

```
Stream PDF downloads with size cap

The previous implementation bufferered the entire response in memory,
which OOMs on theses. Use httpx.stream and bail at 100 MB with a
typed error that the API layer surfaces as HTTP 413.
```

## Security

**Never commit real `.env` content, API keys, or anything with personal
paths.** The repo-level `.gitignore` catches `.env` and `*.key`; double-check
before running `git add -A`. If you accidentally commit a secret,
report it privately and rotate the key immediately.

## Scope & roadmap

The current milestones live in the README's [Roadmap](./README.md#roadmap)
section. Contributions that advance M2–M4 are especially welcome. Out of
scope for now:

- Multi-user / auth (Paperfin is intentionally single-user local-first).
- Non-arXiv paper sources beyond "any direct PDF URL" until we have a
  clear integration pattern.

## License

By contributing, you agree that your contributions will be licensed under
the project's [MIT License](./LICENSE).
