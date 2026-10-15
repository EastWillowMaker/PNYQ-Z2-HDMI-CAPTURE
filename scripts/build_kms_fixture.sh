#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
build_dir=artifacts/kms-fixture
mkdir -p "$build_dir"
cc -std=c11 -O2 -Wall -Wextra -Werror \
  $(pkg-config --cflags libdrm) tools/hdmi_pattern_kms.c \
  $(pkg-config --libs libdrm) -o "$build_dir/hdmi-pattern-kms"
