#!/bin/bash
# One-time environment setup for the main dashboard.
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/scripts/mac_launcher.sh"
setup_application main
