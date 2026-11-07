#!/bin/sh
# Runs on the web server (cron): fetches the artifact of the latest finished validation run.
# Usage: fetch-validation-report.sh <workflow-file> <artifact-name> <dest-dir>
# Needs GH_TOKEN (fine-grained PAT, Actions: read on this repo), gh, and write access to <dest-dir>.
set -eu
REPO=Muspah/netex-belgium
WORKFLOW=$1
ARTIFACT=$2
DEST=$3
STATE_DIR=/var/lib/validation-report
STATE=$STATE_DIR/$WORKFLOW.last-run

# Latest completed run with a report (success = valid, failure = errors found; cancelled runs are skipped)
run=$(gh run list -R "$REPO" -w "$WORKFLOW" -s completed -L5 --json databaseId,conclusion \
  -q '[.[] | select(.conclusion=="success" or .conclusion=="failure")][0].databaseId // empty')
[ -n "$run" ] || exit 0
[ "$run" = "$(cat "$STATE" 2>/dev/null || true)" ] && exit 0

# Download first, so a failed download leaves the current report in place
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
gh run download "$run" -R "$REPO" -n "$ARTIFACT" -D "$tmp"

mkdir -p "$DEST" "$STATE_DIR"
find "$DEST" -mindepth 1 -delete
cp -R "$tmp"/. "$DEST"/
chmod -R a+rX "$DEST"
echo "$run" > "$STATE"
