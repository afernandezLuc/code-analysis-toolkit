#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 project_path [json_output_path]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(realpath "$1")"
CONFIG_OUT="${2:-$PROJECT_ROOT/codeAnalyzerConfig.json}"
ADDONS_DIR_ABS="$SCRIPT_DIR/codeAnalysisAddons"

if [[ ! -d "$PROJECT_ROOT" ]]; then
    echo "Error: project root $PROJECT_ROOT does not exist or is not a directory"
    exit 1
fi

PROJECT_NAME="$(basename "$PROJECT_ROOT")"

json_array() {
    local first=1
    printf "["
    for item in "$@"; do
        [[ -z "$item" ]] && continue
        if [[ $first -eq 0 ]]; then
            printf ", "
        fi
        printf '%s' "$(printf '%s' "$item" | jq -Rs .)"
        first=0
    done
    printf "]"
}

find_compile_db() {
    find "$PROJECT_ROOT" \
        \( -path "*/build/compile_commands.json" \
        -o -path "*/build-*/*compile_commands.json" \
        -o -path "*/cmake-build*/compile_commands.json" \
        -o -path "*/out/compile_commands.json" \) \
        2>/dev/null | head -n1 || true
}

generate_compile_db_if_possible() {
    local existing_db
    local build_dir

    existing_db="$(find_compile_db)"

    if [[ -n "$existing_db" ]]; then
        printf '%s\n' "$existing_db"
        return 0
    fi

    if [[ -f "$PROJECT_ROOT/CMakeLists.txt" ]]; then
        build_dir="$PROJECT_ROOT/build"
        mkdir -p "$build_dir"

        echo "compile_commands.json was not found. Generating it with CMake in $build_dir..." >&2

        if ! cmake -S "$PROJECT_ROOT" -B "$build_dir" -DCMAKE_EXPORT_COMPILE_COMMANDS=ON >&2; then
            echo "Error: failed to generate compile_commands.json with CMake" >&2
            printf '\n'
            return 1
        fi

        if [[ -f "$build_dir/compile_commands.json" ]]; then
            printf '%s\n' "$build_dir/compile_commands.json"
            return 0
        fi

        echo "Error: CMake finished, but it did not generate $build_dir/compile_commands.json" >&2
    fi

    printf '\n'
    return 0
}

COMPILE_DB_ABS="$(generate_compile_db_if_possible)"
BUILD_DIR_ABS="$PROJECT_ROOT/build"

if [[ -n "$COMPILE_DB_ABS" ]]; then
    BUILD_DIR_ABS="$(dirname "$COMPILE_DB_ABS")"
fi

BUILD_DIR_REL="$(realpath --relative-to="$PROJECT_ROOT" "$BUILD_DIR_ABS" 2>/dev/null || echo "build")"
COMPILE_DB_REL=""
if [[ -n "$COMPILE_DB_ABS" ]]; then
    COMPILE_DB_REL="$(realpath --relative-to="$PROJECT_ROOT" "$COMPILE_DB_ABS")"
fi

CPP_EXCLUDE_DIRS=(
    ".venv"
    "codeAnalysisAddons"
    "code_analysis_result"
    "build"
)

CLANG_TIDY_EXCLUDE_DIRS=(
    ".venv"
    "codeAnalysisAddons"
    "code_analysis_result"
    "build"
)

for d in third_party external extern vendor vendors; do
    [[ -d "$PROJECT_ROOT/$d" ]] && CPP_EXCLUDE_DIRS+=("$d")
    [[ -d "$PROJECT_ROOT/$d" ]] && CLANG_TIDY_EXCLUDE_DIRS+=("$d")
done

COVERAGE_ENABLED=false
[[ -d "$PROJECT_ROOT/tests" || -d "$PROJECT_ROOT/test" ]] && COVERAGE_ENABLED=true

CLANG_ANALYZER_ENABLED=false
CLANG_ANALYZER_BUILD_CMD="make -C \"$BUILD_DIR_REL\" clean all"

if [[ -f "$PROJECT_ROOT/CMakeLists.txt" ]]; then
    CLANG_ANALYZER_BUILD_CMD="cmake --build \"$BUILD_DIR_REL\" --clean-first"
fi

[[ -n "$COMPILE_DB_REL" ]] && CLANG_ANALYZER_ENABLED=true

mkdir -p "$(dirname "$CONFIG_OUT")"
mkdir -p "$ADDONS_DIR_ABS"

cat > "$CONFIG_OUT" <<EOF
{
  "project_name": "$PROJECT_NAME",
  "build_dir": "$BUILD_DIR_REL",
  "compile_db": "$COMPILE_DB_REL",
  "c_version": "c11",
  "report_dir": "code_analysis_result",
  "suppressions": ".cppcheck-suppress",
  "cppcheck_suppressions_entries": [],
  "cppcheck_exclude_dirs": $(json_array "${CPP_EXCLUDE_DIRS[@]}"),
  "clang_tidy_report": "code_analysis_result/clang_tidy_summary.txt",
  "clang_tidy_exclude_dirs": $(json_array "${CLANG_TIDY_EXCLUDE_DIRS[@]}"),
  "clang_analyzer_enabled": $CLANG_ANALYZER_ENABLED,
  "clang_analyzer_build_cmd": $(printf '%s' "$CLANG_ANALYZER_BUILD_CMD" | jq -Rs .),
  "clang_analyzer_output_dir": "code_analysis_result/scan-build",
  "summary_pdf": "code_analysis_result/analysis_summary.pdf",
  "addons_dir": $(printf '%s' "$ADDONS_DIR_ABS" | jq -Rs .),
  "misra_rules_url": "https://gitlab.com/MISRA/MISRA-C/MISRA-C-2012/-/raw/main/tools/misra_c_2023__headlines_for_cppcheck.txt",
  "misra_rules_filename": "misra_rules.txt",
  "extra_defines": ["-D__GNUC__"],
  "coverage_enabled": $COVERAGE_ENABLED,
  "coverage_capture_dir": "$BUILD_DIR_REL",
  "coverage_base_dir": ".",
  "coverage_info": "code_analysis_result/coverage.info",
  "coverage_html_dir": "code_analysis_result/coverage-html"
}
EOF

echo "Configuration generated at: $CONFIG_OUT"
echo "Analyzed project         : $PROJECT_ROOT"
echo "build_dir                : $BUILD_DIR_REL"
echo "compile_db               : ${COMPILE_DB_REL:-not generated}"
echo "addons_dir               : $ADDONS_DIR_ABS"