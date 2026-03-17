#!/usr/bin/env bash
############################################################################
# Copyright (C) 2026 Alejandro Fernández Rodríguez                         #
#                                                                          #
# Permission is hereby granted, free of charge, to any person obtaining a  #
# copy of this software and associated documentation files (the "Software"),#
# to deal in the Software without restriction, including without limitation#
# the rights to use, copy, modify, merge, publish, distribute, sublicense, #
# and/or sell copies of the Software, and to permit persons to whom the    #
# Software is furnished to do so, subject to the following conditions:     #
#                                                                          #
# The above copyright notice and this permission notice shall be included  #
# in all copies or substantial portions of the Software.                   #
#                                                                          #
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS  #
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF               #
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.   #
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY     #
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,     #
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE        #
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.                   #
############################################################################

# @file   staticCodeAnalysis.sh
# @brief  Static analysis tool for C projects using Cppcheck + MISRA + clang-tidy
#         + Clang Static Analyzer + LCOV coverage reports.
#
# @author Alejandro Fernández Rodríguez <afernandez@lucernasoftware.com>
# @date   17 mar 2026
# @version 1.0.0
# @see    https://github.com/afernandezLuc/

set -uo pipefail

START_TIME=$(date +%s)

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <config.json>"
    exit 1
fi

CONFIG_FILE="$(realpath "$1")"
CONFIG_DIR="$(dirname "$CONFIG_FILE")"

echo "Init static code analyzer tool"

#-------------------------------------------------------------------------------
# Cleaning up temporary artefacts
#-------------------------------------------------------------------------------
TMP_FILES=()
TMP_DIRS=()
ANALYSIS_ERRORS=0

cleanup_cppcheck_generated_artifacts() {
    local root="${PROJECT_ROOT:-}"

    [[ -n "$root" && -d "$root" ]] || return 0

    find "$root" -type f \( -name '*.dump' -o -name '*.ctu-info' \) -exec rm -f {} + 2>/dev/null || true
}

cleanup_legacy_suppressions_file() {
    local suppressions_file="${SUPPRESSIONS_FILE:-}"

    [[ -n "$suppressions_file" && -f "$suppressions_file" ]] || return 0
    [[ "$(basename "$suppressions_file")" == ".cppcheck-suppress" ]] || return 0
    [[ -s "$suppressions_file" ]] && return 0

    rm -f "$suppressions_file"
}

cleanup() {
    echo -e "\n🧹 Cleaning up temporary artefacts …"

    if jobs -p >/dev/null 2>&1; then
        kill $(jobs -p) 2>/dev/null || true
    fi

    for f in "${TMP_FILES[@]}"; do
        [[ -e "$f" ]] && rm -f "$f"
    done

    for d in "${TMP_DIRS[@]}"; do
        [[ -d "$d" ]] && rm -rf "$d"
    done

    cleanup_cppcheck_generated_artifacts
    cleanup_legacy_suppressions_file
}

trap cleanup EXIT
trap "exit 130" INT TERM

#-------------------------------------------------------------------------------
# Helpers
#-------------------------------------------------------------------------------
spinner_wait_pid() {
    local pid="$1"
    local msg="$2"
    local spin='-/|\'
    local i=0

    tput civis 2>/dev/null || true
    while kill -0 "$pid" 2>/dev/null; do
        printf "\r%s %s" "${spin:i++%4:1}" "$msg"
        sleep 0.1
    done
    tput cnorm 2>/dev/null || true

    wait "$pid"
    local rc=$?

    if [[ $rc -eq 0 ]]; then
        printf "\r✔ %s\n" "$msg"
    else
        printf "\r✘ %s\n" "$msg"
    fi

    return $rc
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Required command not found: $1"
        exit 1
    }
}

resolve_path_from_config() {
    local p="$1"

    [[ -z "$p" || "$p" == "null" ]] && {
        echo ""
        return
    }

    if [[ "$p" = /* ]]; then
        echo "$p"
    else
        echo "$CONFIG_DIR/$p"
    fi
}

append_link_if_exists() {
    local target_file="$1"
    local label="$2"
    local index_file="$REPORT_DIR/html/index.html"

    if [[ -f "$target_file" && -f "$index_file" ]]; then
        local rel_path
        rel_path="$(realpath --relative-to="$(dirname "$index_file")" "$target_file" 2>/dev/null || true)"

        if [[ -n "$rel_path" ]]; then
            local escaped_label
            local escaped_path

            escaped_label="$(printf '%s' "$label" | sed 's/[\/&]/\\&/g')"
            escaped_path="$(printf '%s' "$rel_path" | sed 's/[\/&]/\\&/g')"

            if grep -Fq "href=\"$rel_path\"" "$index_file"; then
                return 0
            fi

            if grep -q '<p><a href="stats.html">Statistics</a></p>' "$index_file"; then
                sed -i "/<p><a href=\"stats.html\">Statistics<\/a><\/p>/a <p><a href=\"$escaped_path\">$escaped_label<\/a><\/p>" "$index_file"
            elif grep -q '<div id="menu_index">' "$index_file"; then
                sed -i "/<div id=\"menu_index\">/a <p><a href=\"$escaped_path\">$escaped_label<\/a><\/p>" "$index_file"
            else
                sed -i "\#</body>#i <p><a href=\"$escaped_path\">$escaped_label</a></p>" "$index_file"
            fi
        fi
    fi
}

json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    printf '%s' "$s"
}

filter_compile_db() {
    local input_db="$1"
    local output_db="$2"
    shift 2
    local excludes=("$@")

    if [[ ${#excludes[@]} -eq 0 ]]; then
        cp "$input_db" "$output_db"
        return
    fi

    local jq_expr='map(select(true'
    local ex

    for ex in "${excludes[@]}"; do
        ex="${ex%/}"
        local ex_escaped
        ex_escaped="$(json_escape "$ex")"
        jq_expr+=" and ((.file | startswith(\"${ex_escaped}/\")) | not)"
    done

    jq_expr+='))'
    jq "$jq_expr" "$input_db" > "$output_db"
}

mark_error() {
    ANALYSIS_ERRORS=1
    echo "⚠️  $1"
}

has_coverage_artifacts() {
    local dir="$1"
    [[ -n "$dir" && -d "$dir" ]] || return 1
    find "$dir" -type f \( -name "*.gcda" -o -name "*.gcno" \) -print -quit 2>/dev/null | grep -q .
}

has_ctest_tests() {
    local dir="$1"
    [[ -n "$dir" && -d "$dir" ]] || return 1
    find "$dir" -name CTestTestfile.cmake -print -quit 2>/dev/null | grep -q .
}

run_shell_cmd() {
    local cmd="$1"
    local workdir="${2:-$PROJECT_ROOT}"

    [[ -n "$cmd" ]] || return 0
    (
        cd "$workdir"
        bash -lc "$cmd"
    )
}

#-------------------------------------------------------------------------------
# Python check
#-------------------------------------------------------------------------------
if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    echo "Python not found"
    exit 1
fi

#-------------------------------------------------------------------------------
# Config from JSON
#-------------------------------------------------------------------------------
[[ -f "$CONFIG_FILE" ]] || { echo "File $CONFIG_FILE not found"; exit 1; }

require_cmd jq

PROJECT_ROOT="$(resolve_path_from_config "$(jq -r '.project_root // ""' "$CONFIG_FILE")")"
[[ -n "$PROJECT_ROOT" ]] || PROJECT_ROOT="$CONFIG_DIR"

BUILD_DIR="$(resolve_path_from_config "$(jq -r '.build_dir' "$CONFIG_FILE")")"
COMPILE_DB="$(resolve_path_from_config "$(jq -r '.compile_db' "$CONFIG_FILE")")"
C_VERSION="$(jq -r '.c_version' "$CONFIG_FILE")"
REPORT_DIR="$(resolve_path_from_config "$(jq -r '.report_dir' "$CONFIG_FILE")")"
SUPPRESSIONS_FILE="$(resolve_path_from_config "$(jq -r '.suppressions' "$CONFIG_FILE")")"
CLANG_TIDY_REPORT="$(resolve_path_from_config "$(jq -r '.clang_tidy_report' "$CONFIG_FILE")")"
SUMMARY_PDF="$(resolve_path_from_config "$(jq -r '.summary_pdf' "$CONFIG_FILE")")"

ADDONS_DIR="$(resolve_path_from_config "$(jq -r '.addons_dir' "$CONFIG_FILE")")"
MISRA_RULES_URL="$(jq -r '.misra_rules_url' "$CONFIG_FILE")"
MISRA_RULES_FILENAME="$(jq -r '.misra_rules_filename' "$CONFIG_FILE")"

COVERAGE_ENABLED="$(jq -r '.coverage_enabled // false' "$CONFIG_FILE")"
COVERAGE_CAPTURE_DIR="$(resolve_path_from_config "$(jq -r '.coverage_capture_dir // ""' "$CONFIG_FILE")")"
COVERAGE_BASE_DIR="$(resolve_path_from_config "$(jq -r '.coverage_base_dir // "."' "$CONFIG_FILE")")"
COVERAGE_INFO="$(resolve_path_from_config "$(jq -r '.coverage_info // ""' "$CONFIG_FILE")")"
COVERAGE_HTML_DIR="$(resolve_path_from_config "$(jq -r '.coverage_html_dir // ""' "$CONFIG_FILE")")"

COVERAGE_BUILD_DIR="$(resolve_path_from_config "$(jq -r '.coverage_build_dir // ""' "$CONFIG_FILE")")"
COVERAGE_CONFIGURE_CMD="$(jq -r '.coverage_configure_cmd // ""' "$CONFIG_FILE")"
COVERAGE_BUILD_CMD="$(jq -r '.coverage_build_cmd // ""' "$CONFIG_FILE")"
COVERAGE_RUN_CMD="$(jq -r '.coverage_run_cmd // ""' "$CONFIG_FILE")"

CLANG_ANALYZER_ENABLED="$(jq -r '.clang_analyzer_enabled // false' "$CONFIG_FILE")"
CLANG_ANALYZER_BUILD_CMD="$(jq -r '.clang_analyzer_build_cmd // ""' "$CONFIG_FILE")"
CLANG_ANALYZER_OUTPUT_DIR="$(resolve_path_from_config "$(jq -r '.clang_analyzer_output_dir // ""' "$CONFIG_FILE")")"

PROJECT_NAME="$(jq -r '.project_name // "Unknown"' "$CONFIG_FILE")"

mapfile -t EXTRA_DEFINES           < <(jq -r '.extra_defines[]?' "$CONFIG_FILE")
mapfile -t SUPPRESSIONS_ENTRIES    < <(jq -r '.cppcheck_suppressions_entries[]?' "$CONFIG_FILE")
mapfile -t CPP_EXCLUDE_DIRS        < <(jq -r '.cppcheck_exclude_dirs[]?' "$CONFIG_FILE")
mapfile -t CLANG_TIDY_EXCLUDE_DIRS < <(jq -r '.clang_tidy_exclude_dirs[]?' "$CONFIG_FILE")

MISRA_RULES="$ADDONS_DIR/$MISRA_RULES_FILENAME"
PDF_SUMMARY_PY="$ADDONS_DIR/generate_summary_pdf.py"
CLANG_TIDY_HTML_PY="$ADDONS_DIR/clang_tidy_to_html.py"
TMP_COMPILE_DB="$BUILD_DIR/compile_commands_tmp.json"
FILTERED_COMPILE_DB="$BUILD_DIR/compile_commands_filtered.json"
MISRA_JSON="$BUILD_DIR/misra.json"
TMP_DB_DIR="$BUILD_DIR/clang_tmp_db"
CPPCHECK_SUPPRESSIONS_FILE="$BUILD_DIR/.cppcheck-suppress.generated"

mkdir -p "$REPORT_DIR" "$ADDONS_DIR" "$TMP_DB_DIR" "$REPORT_DIR/html" "$BUILD_DIR"

if [[ "$COVERAGE_ENABLED" == "true" ]]; then
    [[ -n "$COVERAGE_INFO" ]] && mkdir -p "$(dirname "$COVERAGE_INFO")"
    [[ -n "$COVERAGE_HTML_DIR" ]] && mkdir -p "$COVERAGE_HTML_DIR"
fi

if [[ "$CLANG_ANALYZER_ENABLED" == "true" && -n "$CLANG_ANALYZER_OUTPUT_DIR" ]]; then
    mkdir -p "$CLANG_ANALYZER_OUTPUT_DIR"
fi

TMP_FILES+=("$TMP_COMPILE_DB" "$FILTERED_COMPILE_DB" "$MISRA_JSON" "$CPPCHECK_SUPPRESSIONS_FILE")
TMP_DIRS+=("$TMP_DB_DIR")

#-------------------------------------------------------------------------------
# Coverage defaults / auto configuration
#-------------------------------------------------------------------------------
if [[ "$COVERAGE_ENABLED" == "true" ]]; then
    if [[ -z "$COVERAGE_BUILD_DIR" ]]; then
        COVERAGE_BUILD_DIR="$BUILD_DIR/coverage_auto"
    fi

    if [[ -z "$COVERAGE_BASE_DIR" ]]; then
        COVERAGE_BASE_DIR="$PROJECT_ROOT"
    fi

    if [[ -f "$PROJECT_ROOT/CMakeLists.txt" ]]; then
        [[ -n "$COVERAGE_CAPTURE_DIR" ]] || COVERAGE_CAPTURE_DIR="$COVERAGE_BUILD_DIR"

        if [[ -z "$COVERAGE_CONFIGURE_CMD" ]]; then
            COVERAGE_CONFIGURE_CMD="cmake -S \"$PROJECT_ROOT\" -B \"$COVERAGE_BUILD_DIR\" -DCMAKE_BUILD_TYPE=Debug -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DCMAKE_C_FLAGS=\"--coverage -O0 -g\" -DCMAKE_CXX_FLAGS=\"--coverage -O0 -g\""
        fi

        if [[ -z "$COVERAGE_BUILD_CMD" ]]; then
            COVERAGE_BUILD_CMD="cmake --build \"$COVERAGE_BUILD_DIR\" --clean-first"
        fi

        if [[ -z "$COVERAGE_RUN_CMD" ]]; then
            COVERAGE_RUN_CMD="ctest --test-dir \"$COVERAGE_BUILD_DIR\" --output-on-failure"
        fi
    fi
fi

#-------------------------------------------------------------------------------
# Download addons
#-------------------------------------------------------------------------------
_download() {
    local f="$1"
    local u="$2"
    local dst="$ADDONS_DIR/$f"

    if [[ -f "$dst" && -s "$dst" ]]; then
        return
    fi

    echo "Downloading $f"
    wget -q "$u" -O "$dst"

    [[ -s "$dst" ]] || {
        echo "Downloaded file is empty or invalid: $dst"
        exit 1
    }

    chmod +x "$dst" 2>/dev/null || true
}

require_cmd wget
SYSTEM_CPPCHECK_ADDONS_DIR="/usr/lib/x86_64-linux-gnu/cppcheck/addons"

if [[ -f "$SYSTEM_CPPCHECK_ADDONS_DIR/misra.py" ]]; then
    MISRA_PY="$SYSTEM_CPPCHECK_ADDONS_DIR/misra.py"
    echo "Using system MISRA addon: $MISRA_PY"
else
    echo "System MISRA addon not found in $SYSTEM_CPPCHECK_ADDONS_DIR"
    exit 1
fi

_download "$MISRA_RULES_FILENAME" "$MISRA_RULES_URL"

cat > "$MISRA_JSON" <<EOF
{ "script": "$MISRA_PY", "args": [ "--rule-texts=$MISRA_RULES" ] }
EOF

#-------------------------------------------------------------------------------
# Generate tmp compile_commands database with extra flags
#-------------------------------------------------------------------------------
[[ -f "$COMPILE_DB" ]] || { echo "$COMPILE_DB not found"; exit 1; }

EXTRA_CFLAGS="${EXTRA_DEFINES[*]:-}"
jq --arg defs "$EXTRA_CFLAGS" \
   'map(if has("command") and ($defs | length > 0) then .command += " " + $defs else . end)' \
   "$COMPILE_DB" > "$TMP_COMPILE_DB"

[[ -s "$TMP_COMPILE_DB" ]] || { echo "Failed to create tmp compile DB"; exit 1; }

cp "$TMP_COMPILE_DB" "$TMP_DB_DIR/compile_commands.json"

CPP_EXCLUDE_DIRS_RESOLVED=()
for d in "${CPP_EXCLUDE_DIRS[@]}"; do
    [[ -n "$d" ]] && CPP_EXCLUDE_DIRS_RESOLVED+=("$(resolve_path_from_config "$d")")
done

filter_compile_db "$TMP_COMPILE_DB" "$FILTERED_COMPILE_DB" "${CPP_EXCLUDE_DIRS_RESOLVED[@]}"
[[ -s "$FILTERED_COMPILE_DB" ]] || { echo "Failed to create filtered compile DB"; exit 1; }

#-------------------------------------------------------------------------------
# Check paths from filtered DB
#-------------------------------------------------------------------------------
missing=0
while read -r f; do
    [[ -z "$f" ]] && continue
    [[ -f "$f" ]] || { echo "⚠️  $f missing"; missing=1; }
done < <(jq -r '.[].file' "$FILTERED_COMPILE_DB" | sort -u)

(( missing == 0 )) || { echo "Errors detected in defined paths"; exit 1; }

#-------------------------------------------------------------------------------
# Creating cppcheck suppression file
#-------------------------------------------------------------------------------
mkdir -p "$(dirname "$CPPCHECK_SUPPRESSIONS_FILE")"
: > "$CPPCHECK_SUPPRESSIONS_FILE"

if [[ -n "$SUPPRESSIONS_FILE" && -f "$SUPPRESSIONS_FILE" ]]; then
    cat "$SUPPRESSIONS_FILE" >> "$CPPCHECK_SUPPRESSIONS_FILE"
fi

if [[ -s "$CPPCHECK_SUPPRESSIONS_FILE" && ${#SUPPRESSIONS_ENTRIES[@]} -gt 0 ]]; then
    printf '\n' >> "$CPPCHECK_SUPPRESSIONS_FILE"
fi

for e in "${SUPPRESSIONS_ENTRIES[@]}"; do
    echo "$e" >> "$CPPCHECK_SUPPRESSIONS_FILE"
done

#-------------------------------------------------------------------------------
# Tool checks
#-------------------------------------------------------------------------------
require_cmd cppcheck
require_cmd cppcheck-htmlreport
require_cmd xargs
require_cmd sed
require_cmd grep

command -v clang-tidy >/dev/null 2>&1 || {
    echo "clang-tidy not found"
    exit 1
}

if [[ "$COVERAGE_ENABLED" == "true" ]]; then
    require_cmd lcov
    require_cmd genhtml
fi

if [[ "$CLANG_ANALYZER_ENABLED" == "true" ]]; then
    require_cmd scan-build
fi

#-------------------------------------------------------------------------------
# Cppcheck
#-------------------------------------------------------------------------------
run_cppcheck() {
    cppcheck \
        --project="$FILTERED_COMPILE_DB" \
        --enable=all \
        --inconclusive \
        --force \
        --std="$C_VERSION" \
        --inline-suppr \
        --addon="$MISRA_JSON" \
        --addon=y2038 \
        --addon=threadsafety \
        --addon=naming \
        --addon=misc \
        --suppressions-list="$CPPCHECK_SUPPRESSIONS_FILE" \
        --xml 2> "$REPORT_DIR/cppcheck.xml"
}

run_cppcheck &
spinner_wait_pid $! "🕵️ Running Cppcheck …" || mark_error "Cppcheck failed"

if [[ ! -s "$REPORT_DIR/cppcheck.xml" ]]; then
    mark_error "cppcheck.xml was not generated or is empty"
fi

#-------------------------------------------------------------------------------
# clang-tidy
#-------------------------------------------------------------------------------
EXCLUDE_REGEX=""
if [[ ${#CLANG_TIDY_EXCLUDE_DIRS[@]} -gt 0 ]]; then
    CLANG_EXCLUDES_RESOLVED=()
    for d in "${CLANG_TIDY_EXCLUDE_DIRS[@]}"; do
        [[ -n "$d" ]] && CLANG_EXCLUDES_RESOLVED+=("$(resolve_path_from_config "$d")")
    done

    if [[ ${#CLANG_EXCLUDES_RESOLVED[@]} -gt 0 ]]; then
        EXCLUDE_REGEX=$(printf "%s|" "${CLANG_EXCLUDES_RESOLVED[@]}")
        EXCLUDE_REGEX=${EXCLUDE_REGEX%|}
    fi
fi

run_clang_tidy() {
    if [[ -n "$EXCLUDE_REGEX" ]]; then
        jq -r '.[].file' "$TMP_DB_DIR/compile_commands.json" \
            | grep -Ev "^($EXCLUDE_REGEX)(/|$)" \
            | sort -u \
            | xargs -r -P"$(nproc)" -I{} clang-tidy -p="$TMP_DB_DIR" "{}" 2>&1 \
            | tee "$CLANG_TIDY_REPORT"
    else
        jq -r '.[].file' "$TMP_DB_DIR/compile_commands.json" \
            | sort -u \
            | xargs -r -P"$(nproc)" -I{} clang-tidy -p="$TMP_DB_DIR" "{}" 2>&1 \
            | tee "$CLANG_TIDY_REPORT"
    fi
}

run_clang_tidy &
spinner_wait_pid $! "🕵️ Running clang-tidy …" || mark_error "clang-tidy failed"

if [[ ! -f "$CLANG_TIDY_REPORT" ]]; then
    mark_error "clang-tidy report was not generated"
fi

#-------------------------------------------------------------------------------
# Clang Static Analyzer (scan-build)
#-------------------------------------------------------------------------------
SCAN_BUILD_LOG="$REPORT_DIR/scan-build.log"
CTEST_LOG="$REPORT_DIR/ctest.log"


if [[ "$CLANG_ANALYZER_ENABLED" == "true" ]]; then
    run_scan_build() {
        rm -rf "$CLANG_ANALYZER_OUTPUT_DIR"/* 2>/dev/null || true
        (
            cd "$PROJECT_ROOT"
            bash -c "scan-build --status-bugs -o \"$CLANG_ANALYZER_OUTPUT_DIR\" $CLANG_ANALYZER_BUILD_CMD" \
                2>&1 | tee "$SCAN_BUILD_LOG"
        )
    }

    run_scan_build &
    spinner_wait_pid $! "🕵️ Running Clang Static Analyzer …" || mark_error "Clang Static Analyzer failed"
fi

#-------------------------------------------------------------------------------
# Cppcheck HTML report
#-------------------------------------------------------------------------------
if [[ -s "$REPORT_DIR/cppcheck.xml" ]]; then
    run_cppcheck_html() {
        cppcheck-htmlreport \
            --file="$REPORT_DIR/cppcheck.xml" \
            --report-dir="$REPORT_DIR/html" \
            --source-dir="$PROJECT_ROOT" \
            --title="Static analysis report"
    }

    run_cppcheck_html &
    spinner_wait_pid $! "Creating Cppcheck HTML report …" || mark_error "Cppcheck HTML report generation failed"
else
    mark_error "Skipping Cppcheck HTML report because cppcheck.xml is empty"
fi

#-------------------------------------------------------------------------------
# clang-tidy HTML report
#-------------------------------------------------------------------------------
CLANG_TIDY_HTML="$REPORT_DIR/html/clang_tidy.html"
CLANG_TIDY_JSON="$REPORT_DIR/clang_tidy.json"
mkdir -p "$(dirname "$CLANG_TIDY_HTML")"

run_clang_tidy_html() {
    "$PYTHON_BIN" "$CLANG_TIDY_HTML_PY" \
        --input "$CLANG_TIDY_REPORT" \
        --html-out "$CLANG_TIDY_HTML" \
        --json-out "$CLANG_TIDY_JSON" \
        --project-root "$PROJECT_ROOT" \
        --title "$PROJECT_NAME - Clang-Tidy Report"
}

if [[ ! -f "$CLANG_TIDY_HTML_PY" ]]; then
    mark_error "generate_clang_tidy_html.py not found in $ADDONS_DIR"
else
    if [[ -f "$CLANG_TIDY_REPORT" && -s "$CLANG_TIDY_REPORT" ]]; then
        if [[ -f "$CLANG_TIDY_HTML_PY" ]]; then
            run_clang_tidy_html &
            spinner_wait_pid $! "Creating Clang-Tidy HTML report …" || mark_error "Clang-Tidy HTML report generation failed"

            append_link_if_exists "$CLANG_TIDY_HTML" "Clang-Tidy Report"
        else
            mark_error "Skipping clang-tidy HTML report because parser script does not exist"
        fi
    else
        mark_error "Skipping clang-tidy HTML report because raw report does not exist or is empty"
    fi
fi



#-------------------------------------------------------------------------------
# Automatic coverage preparation
#-------------------------------------------------------------------------------
if [[ "$COVERAGE_ENABLED" == "true" ]]; then
    if [[ -z "$COVERAGE_CAPTURE_DIR" || -z "$COVERAGE_INFO" || -z "$COVERAGE_HTML_DIR" ]]; then
        mark_error "Coverage is enabled but coverage paths are incomplete in JSON"
    elif ! has_coverage_artifacts "$COVERAGE_CAPTURE_DIR"; then
        echo "No coverage artefacts found. Preparing automatic coverage build …"

        if [[ -n "$COVERAGE_BUILD_DIR" ]]; then
            mkdir -p "$COVERAGE_BUILD_DIR"
        fi

        if [[ -n "$COVERAGE_CONFIGURE_CMD" ]]; then
            run_shell_cmd "$COVERAGE_CONFIGURE_CMD" "$PROJECT_ROOT" &
            spinner_wait_pid $! "🧪 Configuring coverage build …" || mark_error "Coverage configure step failed"
        fi

        if [[ -n "$COVERAGE_BUILD_CMD" ]]; then
            run_shell_cmd "$COVERAGE_BUILD_CMD" "$PROJECT_ROOT" &
            spinner_wait_pid $! "🧪 Building project with coverage …" || mark_error "Coverage build step failed"
        fi

        if [[ -n "$COVERAGE_RUN_CMD" ]]; then
            if [[ "$COVERAGE_RUN_CMD" == ctest* ]]; then
                if has_ctest_tests "$COVERAGE_BUILD_DIR"; then
                    (
                        run_shell_cmd "$COVERAGE_RUN_CMD" "$PROJECT_ROOT" 2>&1 | tee "$CTEST_LOG"
                    ) &
                    spinner_wait_pid $! "🧪 Running tests for coverage …" || mark_error "Coverage test execution failed"
                else
                    echo "⚠️  No CTest tests found in $COVERAGE_BUILD_DIR. Skipping automatic test execution."
                fi
            else
                (
                    run_shell_cmd "$COVERAGE_RUN_CMD" "$PROJECT_ROOT" 2>&1 | tee "$CTEST_LOG"
                ) &
                spinner_wait_pid $! "🧪 Running coverage command …" || mark_error "Coverage run command failed"
            fi
        fi
    fi
fi

#-------------------------------------------------------------------------------
# LCOV coverage report
#-------------------------------------------------------------------------------
if [[ "$COVERAGE_ENABLED" == "true" ]]; then
    if has_coverage_artifacts "$COVERAGE_CAPTURE_DIR"; then
        run_coverage() {
            lcov \
                --capture \
                --directory "$COVERAGE_CAPTURE_DIR" \
                --base-directory "$COVERAGE_BASE_DIR" \
                --output-file "$COVERAGE_INFO" \
                --rc branch_coverage=1

            lcov \
                --remove "$COVERAGE_INFO" \
                '/usr/*' \
                '*/tests/*' \
                '*/test/*' \
                '*/third_party/*' \
                '*/external/*' \
                --output-file "$COVERAGE_INFO" \
                --rc branch_coverage=1

            genhtml \
                "$COVERAGE_INFO" \
                --output-directory "$COVERAGE_HTML_DIR" \
                --branch-coverage \
                --title "$PROJECT_NAME - Coverage Report"
        }

        run_coverage &
        spinner_wait_pid $! "📈 Generating LCOV coverage report …" || mark_error "LCOV coverage generation failed"
    else
        mark_error "Coverage enabled, but no .gcda/.gcno files were found in $COVERAGE_CAPTURE_DIR after automatic preparation"
    fi
fi

#-------------------------------------------------------------------------------
# Clang Static Analyzer HTML index discovery
#-------------------------------------------------------------------------------
CLANG_ANALYZER_INDEX=""
if [[ "$CLANG_ANALYZER_ENABLED" == "true" ]]; then
    CLANG_ANALYZER_INDEX="$(find "$CLANG_ANALYZER_OUTPUT_DIR" -type f -name index.html | sort | tail -n 1 || true)"
    if [[ -n "$CLANG_ANALYZER_INDEX" && -f "$REPORT_DIR/html/index.html" ]]; then
        append_link_if_exists "$CLANG_ANALYZER_INDEX" "Clang Static Analyzer Report"
    fi
fi

#-------------------------------------------------------------------------------
# Coverage link in main HTML
#-------------------------------------------------------------------------------
if [[ "$COVERAGE_ENABLED" == "true" && -n "$COVERAGE_HTML_DIR" ]]; then
    append_link_if_exists "$COVERAGE_HTML_DIR/index.html" "LCOV Coverage Report"
fi

#-------------------------------------------------------------------------------
# PDF report
#-------------------------------------------------------------------------------
END_TIME=$(date +%s)
ELAPSED_SEC=$((END_TIME - START_TIME))

ANALYST="$(whoami)"
MACHINE="$(hostname)"
CPU_CORES="$(nproc)"
TOTAL_MEM="$(awk '/MemTotal/ {printf("%.0f MB", $2/1024)}' /proc/meminfo)"
CPU_MODEL="$(grep -m1 'model name' /proc/cpuinfo | cut -d':' -f2 | xargs)"
OS_INFO="$(command -v lsb_release >/dev/null 2>&1 && lsb_release -ds || uname -srmo)"

SCAN_BUILD_LOG_ARG=""
[[ -f "$SCAN_BUILD_LOG" ]] && SCAN_BUILD_LOG_ARG="$SCAN_BUILD_LOG"

run_pdf_summary() {
    local cmd=(
        "$PYTHON_BIN" "$PDF_SUMMARY_PY"
        --cppcheck-xml "$REPORT_DIR/cppcheck.xml"
        --clang-tidy-report "$CLANG_TIDY_REPORT"
        --output-pdf "$SUMMARY_PDF"
        --project-name "$PROJECT_NAME"
        --analyst "$ANALYST"
        --machine "$MACHINE"
        --cpu-model "$CPU_MODEL"
        --os-info "$OS_INFO"
        --elapsed-seconds "$ELAPSED_SEC"
        --cpu-cores "$CPU_CORES"
        --total-memory "$TOTAL_MEM"
        --compile-db "$FILTERED_COMPILE_DB"
        --project-root "$PROJECT_ROOT"
        --main-html-report "$REPORT_DIR/html/index.html"
        --clang-tidy-html "$CLANG_TIDY_HTML"
    )

    [[ -f "$COVERAGE_INFO" ]] && cmd+=(--lcov-info "$COVERAGE_INFO")
    [[ -n "$SCAN_BUILD_LOG_ARG" ]] && cmd+=(--scan-build-log "$SCAN_BUILD_LOG_ARG")
    [[ -f "$CTEST_LOG" ]] && cmd+=(--ctest-log "$CTEST_LOG")
    [[ -f "$COVERAGE_HTML_DIR/index.html" ]] && cmd+=(--coverage-html "$COVERAGE_HTML_DIR/index.html")
    [[ -n "$CLANG_ANALYZER_INDEX" ]] && cmd+=(--clang-analyzer-html "$CLANG_ANALYZER_INDEX")

    "${cmd[@]}"
}

if [[ -f "$PDF_SUMMARY_PY" ]]; then
    run_pdf_summary &
    spinner_wait_pid $! "Generating PDF summary …" || mark_error "PDF summary generation failed"
else
    mark_error "generate_summary_pdf.py not found in $ADDONS_DIR"
fi




#-------------------------------------------------------------------------------
# Final summary
#-------------------------------------------------------------------------------
echo -e "\n✅ Static analysis finished."
echo "Results:"
echo "📝 Cppcheck XML              : $REPORT_DIR/cppcheck.xml"
echo "🌐 Main HTML report          : $REPORT_DIR/html/index.html"
echo "📄 Clang-Tidy HTML           : $CLANG_TIDY_HTML"

if [[ "$CLANG_ANALYZER_ENABLED" == "true" ]]; then
    if [[ -n "$CLANG_ANALYZER_INDEX" ]]; then
        echo "🧠 Clang Static Analyzer     : $CLANG_ANALYZER_INDEX"
    else
        echo "🧠 Clang Static Analyzer     : Not found"
    fi
fi

if [[ "$COVERAGE_ENABLED" == "true" ]]; then
    echo "📈 LCOV info                 : $COVERAGE_INFO"
    echo "📊 LCOV HTML                 : $COVERAGE_HTML_DIR/index.html"
    echo "🧪 Coverage capture dir      : $COVERAGE_CAPTURE_DIR"
fi

[[ -f "$CTEST_LOG" ]] && echo "🧪 Test execution log         : $CTEST_LOG"
echo "📊 PDF summary               : $SUMMARY_PDF"

if [[ $ANALYSIS_ERRORS -ne 0 ]]; then
    echo
    echo "⚠️  The analysis finished with errors or incomplete stages."
    exit 1
fi

exit 0