#!/usr/bin/env bash
# V35.7 TypeScript CLI wrapper
# Usage: bash bridge/run.sh "topic"
# Runs from project root, auto-loads bridge/.env
set -a
source "$(dirname "$0")/.env"
set +a
cd "$(dirname "$0")/.."
npx --prefix bridge/official_core tsx bridge/official_core/src/cli.ts "$@"
