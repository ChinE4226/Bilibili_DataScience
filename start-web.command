#!/bin/bash
# Double-click to run the dashboard with development reloads.
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/scripts/mac_launcher.sh"
launch_application main-development "$@"
