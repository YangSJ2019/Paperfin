#!/usr/bin/env bash
# Start the Paperfin backend with a sanitized env.
#
# Background: the host shell often has ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY /
# ANTHROPIC_MODEL already exported by IDE/agent tooling (Claude Code, internal
# CodeBuddy proxy, etc.). pydantic-settings prefers shell env over .env, so
# those leak in and override what you actually put in backend/.env.
#
# This script strips ANTHROPIC_* from the subprocess environment and lets the
# .env file be the single source of truth. Run from any directory.

set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "error: .venv not set up. Run: python3.12 -m venv .venv && .venv/bin/pip install -e ." >&2
  exit 1
fi

exec env \
  -u ANTHROPIC_API_KEY \
  -u ANTHROPIC_BASE_URL \
  -u ANTHROPIC_MODEL \
  .venv/bin/uvicorn app.main:app --reload --port 8000 "$@"
