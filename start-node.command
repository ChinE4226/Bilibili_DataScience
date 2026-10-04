#!/bin/bash
# Double-click to run the local fetching node web GUI.
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/scripts/mac_launcher.sh"
launch_application node "$@"
