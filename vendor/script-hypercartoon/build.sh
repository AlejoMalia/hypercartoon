#!/bin/bash
# Rebuild engines.mjs from the vendored sources (only needed after editing them). Needs esbuild: npx esbuild
set -e
cd "$(dirname "$0")"
npx --yes esbuild entry.ts --bundle --platform=node --format=esm --tsconfig=tsconfig.json --outfile=engines.mjs --log-level=warning
