#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
output="$here/../bin"
compiler="${CC:-x86_64-w64-mingw32-gcc}"
resource_compiler="${WINDRES:-x86_64-w64-mingw32-windres}"
mkdir -p "$output"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

"$resource_compiler" -O coff -i "$here/planet_native.rc" -o "$scratch/planet_native_resources.o"

common=(-O3 -ffast-math -fopenmp -shared -static -s -Wall -Wextra -Wl,--export-all-symbols
        "$here/globe_render.c" "$here/switcher_native.c" "$scratch/planet_native_resources.o" -lm)

"$compiler" -march=x86-64-v2 -mavx2 -mfma --param max-completely-peeled-insns=2000 -mtune-ctrl=use_gather \
    -o "$output/planet_native_avx2.dll" "${common[@]}"
"$compiler" -march=x86-64-v2 -o "$output/planet_native.dll" "${common[@]}"
