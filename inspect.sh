#!/usr/bin/env bash
set -uo pipefail

cd "$(dirname "$0")" || exit 1

objdump_tool="${OBJDUMP:-x86_64-w64-mingw32-objdump}"
dlls=(bin/planet_native.dll bin/planet_native_avx2.dll)
expected_exports=(globe_bind globe_grade globe_prepare globe_render hook_start hook_stop hook_heartbeat
                  hook_set_capture hook_alt_held unlock_foreground cpu_supports_avx2_fma)
errors=0
warnings=0

error() {
    echo "error: $*"
    errors=$((errors + 1))
}

warning() {
    echo "warning: $*"
    warnings=$((warnings + 1))
}

build_log="$(mktemp)"
trap 'rm -f "$build_log"' EXIT

echo "==> Building native DLLs"
if ! ./native/build-native.sh >"$build_log" 2>&1; then
    error "native build failed: $(grep -m1 -E 'error' "$build_log" || echo 'see build output')"
fi
while IFS= read -r line; do
    warning "gcc: $line"
done < <(grep -E 'warning:' "$build_log")

echo "==> Checking DLL exports"
for dll in "${dlls[@]}"; do
    if [[ ! -f "$dll" ]]; then
        error "$dll was not built"
        continue
    fi
    headers="$("$objdump_tool" -p "$dll")"
    exports="$(sed -n '/\[Ordinal\/Name Pointer\] Table/,/^$/p' <<<"$headers")"
    for name in "${expected_exports[@]}"; do
        if ! grep -qE "[[:space:]]$name$" <<<"$exports"; then
            error "$dll does not export $name"
        fi
    done
    if grep -qE "[[:space:]]normalize_icon_pixels$" <<<"$exports"; then
        error "$dll still exports normalize_icon_pixels"
    fi
    if ! grep -q 'Resource Directory \[\.rsrc\]' <<<"$headers"; then
        error "$dll has no version resource"
    fi
    bmi_count="$("$objdump_tool" -d "$dll" | grep -cE '\b(shlx|sarx|shrx|rorx|movbe|andn|pdep|pext)\b')"
    if [[ "$bmi_count" -ne 0 ]]; then
        error "$dll contains $bmi_count BMI/MOVBE instructions"
    fi
done

echo "==> Compiling Python"
for source in app/*.py; do
    if ! output="$(python3 -c 'import ast, sys; ast.parse(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1])' "$source" 2>&1)"; then
        error "python: $source: $(tail -n1 <<<"$output")"
    fi
done

echo "==> Running selfcheck"
if ! output="$(PYTHONDONTWRITEBYTECODE=1 python3 app/selfcheck.py 2>&1)"; then
    error "selfcheck failed: $(grep -m1 -E 'Error|assert' <<<"$output" || tail -n1 <<<"$output")"
else
    echo "$output"
fi

echo "==> Checking PowerShell"
if command -v pwsh >/dev/null 2>&1; then
    while IFS= read -r line; do
        [[ -n "$line" ]] && warning "PSScriptAnalyzer: $line"
    done < <(pwsh -NoProfile -Command \
        'Get-ChildItem -Filter *.ps1 | Invoke-ScriptAnalyzer | ForEach-Object { "{0}:{1}: {2} {3}" -f $_.ScriptName, $_.Line, $_.RuleName, $_.Message }' 2>&1)
else
    echo "pwsh not installed, PSScriptAnalyzer skipped"
fi

echo "==> Checking shell"
if command -v shellcheck >/dev/null 2>&1; then
    while IFS= read -r line; do
        warning "shellcheck: $line"
    done < <(shellcheck -f gcc inspect.sh native/build-native.sh)
fi

echo "==> Checking sources"
while IFS= read -r line; do
    warning "comment: $line"
done < <(grep -nE '^\s*(//|/\*)' native/switcher_native.c native/planet_native.rc;
         grep -nE '^\s*#' app/*.py;
         grep -nE '^\s*(#|<#)' ./*.ps1)
while IFS= read -r line; do
    warning "unfinished: $line"
done < <(grep -nE 'TODO|FIXME|XXX' app/*.py native/switcher_native.c native/planet_native.rc native/build-native.sh ./*.ps1)
while IFS= read -r line; do
    error "bytecode left behind: $line"
done < <(find app -name '__pycache__' -o -name '*.pyc')

echo "==> $errors error(s), $warnings warning(s)"
[[ $errors -eq 0 && $warnings -eq 0 ]]
