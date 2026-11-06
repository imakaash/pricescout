#!/bin/zsh
# Install (or with --remove, uninstall) the weekly launchd job for PriceScout.
set -eu
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="$HOME/Library/LaunchAgents/com.pricescout.weekly.plist"

if [[ "${1:-}" == "--remove" ]]; then
  launchctl bootout "gui/$(id -u)" "$TARGET" 2>/dev/null || true
  rm -f "$TARGET"
  echo "Removed weekly schedule."
  exit 0
fi

mkdir -p "$PROJECT_DIR/logs" "$HOME/Library/LaunchAgents"
chmod +x "$PROJECT_DIR/scripts/run_weekly.sh"
sed "s#__PROJECT_DIR__#$PROJECT_DIR#g" "$PROJECT_DIR/deploy/com.pricescout.weekly.plist" > "$TARGET"
launchctl bootout "gui/$(id -u)" "$TARGET" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
echo "Installed: runs Sundays 22:00 (or on next wake). Logs: $PROJECT_DIR/logs/"
echo "Run now:   launchctl kickstart gui/$(id -u)/com.pricescout.weekly"
echo "Remove:    scripts/install_schedule.sh --remove"
