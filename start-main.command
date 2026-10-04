#!/bin/bash
# Double-click to run the main dashboard with browser updates and stable Python.
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/scripts/mac_launcher.sh"
launch_application main "$@"
