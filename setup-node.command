#!/bin/bash
# One-time environment setup for a fetching Mac, without chart dependencies.
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/scripts/mac_launcher.sh"
setup_application node
