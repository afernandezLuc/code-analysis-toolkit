#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime

import matplotlib.pyplot as plt
from graphviz import Digraph
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from collections import defaultdict
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ACCENT = colors.HexColor("#1F4E79")
ACCENT_2 = colors.HexColor("#D9EAF7")
TEXT = colors.HexColor("#22313F")
MUTED = colors.HexColor("#6B7785")
SUCCESS = colors.HexColor("#D9F2E6")
WARNING_BG = colors.HexColor("#FFF4CC")
ERROR_BG = colors.HexColor("#FDE2E1")
NOTE_BG = colors.HexColor("#EDF5FF")
GRID = colors.HexColor("#D7DEE5")
WHITE = colors.white


# -----------------------------------------------------------------------------
# Parsing helpers
# -----------------------------------------------------------------------------
def normalize_path(path):
    return path.replace("\\", "/") if path else path


SEVERITY_ORDER = ["error", "warning", "information", "style", "portability", "performance", "note", "unknown"]


def parse_cppcheck(xml_path):
    summary = Counter()
    issues = []
    files = defaultdict(lambda: Counter())
    checks = Counter()

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for error in root.findall(".//error"):
            sev = (error.get("severity") or "unknown").lower()
            msg = error.get("msg") or error.get("verbose") or ""
            check_id = error.get("id") or "unknown"
            locations = error.findall("location")
            file_path = ""
            line = ""
            if locations:
                file_path = normalize_path(locations[0].get("file") or "")
                line = locations[0].get("line") or ""
            summary[sev] += 1
            checks[check_id] += 1
            if file_path:
                files[file_path][sev] += 1
                files[file_path]["total"] += 1
            issues.append(
                {
                    "tool": "Cppcheck",
                    "severity": sev,
                    "check": check_id,
                    "file": file_path,
                    "line": line,
                    "message": msg,
                }
            )
    except FileNotFoundError:
        print(f"WARNING: Cppcheck XML report file not found: {xml_path}")
    except ET.ParseError:
        print(f"ERROR: Cppcheck XML parse failed: {xml_path}")
    except Exception as e:
        print(f"ERROR: Cppcheck XML processing failed: {e}")

    return {
        "summary": dict(summary),
        "issues": issues,
        "files": {k: dict(v) for k, v in files.items()},
        "checks": dict(checks),
    }


CLANG_LINE_RE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):(?P<column>\d+):\s*(?P<severity>warning|error|note):\s*(?P<message>.*?)(?:\s*\[(?P<check>[^\]]+)\])?\s*$",
    re.IGNORECASE,
)


def parse_clang_tidy(txt_path):
    summary = Counter()
    issues = []
    files = defaultdict(lambda: Counter())
    checks = Counter()

    try:
        with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.rstrip("\n")
                m = CLANG_LINE_RE.match(line)
                if not m:
                    continue
                sev = m.group("severity").lower()
                file_path = normalize_path(m.group("file"))
                check = m.group("check") or "-"
                message = m.group("message").strip()
                line_no = m.group("line")
                col_no = m.group("column")

                summary[sev] += 1
                files[file_path][sev] += 1
                files[file_path]["total"] += 1
                checks[check] += 1
                issues.append(
                    {
                        "tool": "Clang-Tidy",
                        "severity": sev,
                        "check": check,
                        "file": file_path,
                        "line": line_no,
                        "column": col_no,
                        "message": message,
                    }
                )
    except FileNotFoundError:
        print(f"WARNING: Clang-Tidy report file not found: {txt_path}")
    except Exception as e:
        print(f"ERROR: Clang-Tidy report parse failed: {e}")

    return {
        "summary": dict(summary),
        "issues": issues,
        "files": {k: dict(v) for k, v in files.items()},
        "checks": dict(checks),
    }


def parse_lcov_info(info_path):
    summary = {
        "lines_found": 0,
        "lines_hit": 0,
        "branches_found": 0,
        "branches_hit": 0,
        "line_coverage": 0.0,
        "branch_coverage": 0.0,
        "files": {},
    }
    if not info_path:
        return summary

    current_file = None
    current_stats = None

    def finalize_current_file():
        nonlocal current_file, current_stats
        if not current_file or current_stats is None:
            return
        lf = current_stats.get("lines_found", 0)
        lh = current_stats.get("lines_hit", 0)
        brf = current_stats.get("branches_found", 0)
        brh = current_stats.get("branches_hit", 0)
        current_stats["line_coverage"] = 100.0 * lh / lf if lf else 0.0
        current_stats["branch_coverage"] = 100.0 * brh / brf if brf else 0.0
        summary["files"][normalize_path(current_file)] = current_stats

    try:
        with open(info_path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                if line.startswith("SF:"):
                    finalize_current_file()
                    current_file = line.split(":", 1)[1]
                    current_stats = {
                        "lines_found": 0,
                        "lines_hit": 0,
                        "branches_found": 0,
                        "branches_hit": 0,
                        "line_coverage": 0.0,
                        "branch_coverage": 0.0,
                    }
                elif line.startswith("LF:"):
                    value = int(line.split(":", 1)[1])
                    summary["lines_found"] += value
                    if current_stats is not None:
                        current_stats["lines_found"] = value
                elif line.startswith("LH:"):
                    value = int(line.split(":", 1)[1])
                    summary["lines_hit"] += value
                    if current_stats is not None:
                        current_stats["lines_hit"] = value
                elif line.startswith("BRF:"):
                    value = int(line.split(":", 1)[1])
                    summary["branches_found"] += value
                    if current_stats is not None:
                        current_stats["branches_found"] = value
                elif line.startswith("BRH:"):
                    value = int(line.split(":", 1)[1])
                    summary["branches_hit"] += value
                    if current_stats is not None:
                        current_stats["branches_hit"] = value
                elif line == "end_of_record":
                    finalize_current_file()
                    current_file = None
                    current_stats = None

        finalize_current_file()

        if summary["lines_found"]:
            summary["line_coverage"] = 100.0 * summary["lines_hit"] / summary["lines_found"]
        if summary["branches_found"]:
            summary["branch_coverage"] = 100.0 * summary["branches_hit"] / summary["branches_found"]
    except FileNotFoundError:
        print(f"WARNING: LCOV info file not found: {info_path}")
    except Exception as e:
        print(f"ERROR: LCOV info parse failed: {e}")

    return summary


def parse_scan_build_log(log_path):
    summary = {"bugs": 0}
    if not log_path:
        return summary

    bug_regex = re.compile(r"\b([0-9]+)\s+bug(s)?\s+found\b", re.IGNORECASE)
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                match = bug_regex.search(line)
                if match:
                    summary["bugs"] = int(match.group(1))
    except FileNotFoundError:
        print(f"WARNING: scan-build log file not found: {log_path}")
    except Exception as e:
        print(f"ERROR: scan-build log parse failed: {e}")
    return summary


def parse_ctest_log(log_path):
    result = {
        "available": False,
        "total": 0,
        "passed": 0,
        "failed": 0,
        "pass_rate": 0.0,
        "failed_tests": [],
        "passed_tests": [],
        "summary_line": "",
        "raw_overview": [],
    }
    if not log_path or not os.path.isfile(log_path):
        return result

    result["available"] = True
    summary_re = re.compile(r"(\d+)% tests passed,\s*(\d+) tests failed out of (\d+)")
    listing_re = re.compile(r"^\s*(\d+)/(\d+)\s+Test\s+#\d+:\s+(.+?)\s+\.{2,}\s+(Passed|Failed|\*\*\*Failed)\s+", re.IGNORECASE)
    failed_re = re.compile(r"^\s*\d+\s*-\s*(.+?)\s*\(Failed\)")

    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                s = line.strip()
                m = summary_re.search(s)
                if m:
                    result["failed"] = int(m.group(2))
                    result["total"] = int(m.group(3))
                    result["passed"] = result["total"] - result["failed"]
                    result["pass_rate"] = 100.0 * result["passed"] / result["total"] if result["total"] else 0.0
                    result["summary_line"] = s
                    continue

                m_list = listing_re.search(line)
                if m_list:
                    current_idx = int(m_list.group(1))
                    total_seen = int(m_list.group(2))
                    test_name = m_list.group(3).strip()
                    status = m_list.group(4).lower()
                    if total_seen > result["total"]:
                        result["total"] = total_seen
                    result["raw_overview"].append({
                        "index": current_idx,
                        "name": test_name,
                        "status": "passed" if "pass" in status else "failed",
                    })
                    if "pass" in status:
                        result["passed_tests"].append(test_name)
                    else:
                        result["failed_tests"].append(test_name)
                    continue

                m2 = failed_re.search(line)
                if m2:
                    name = m2.group(1).strip()
                    if name not in result["failed_tests"]:
                        result["failed_tests"].append(name)

        if result["raw_overview"]:
            result["passed"] = sum(1 for t in result["raw_overview"] if t["status"] == "passed")
            result["failed"] = sum(1 for t in result["raw_overview"] if t["status"] == "failed")
            result["total"] = max(result["total"], len(result["raw_overview"]))
            result["pass_rate"] = 100.0 * result["passed"] / result["total"] if result["total"] else 0.0
            if not result["summary_line"]:
                result["summary_line"] = f"{result['passed']} passed / {result['failed']} failed / {result['total']} total"
    except Exception as e:
        print(f"ERROR: ctest log parse failed: {e}")

    return result


# -----------------------------------------------------------------------------
# Charts and diagrams
# -----------------------------------------------------------------------------
def draw_bar_chart(data_cpp, data_clang, data_scan, output_img):
    labels = [
        "Cppcheck Error",
        "Cppcheck Warning",
        "Cppcheck Style",
        "Cppcheck Portability",
        "Clang Error",
        "Clang Warning",
        "Scan-Build Bugs",
    ]
    values = [
        data_cpp.get("error", 0),
        data_cpp.get("warning", 0),
        data_cpp.get("style", 0),
        data_cpp.get("portability", 0),
        data_clang.get("error", 0),
        data_clang.get("warning", 0),
        data_scan.get("bugs", 0),
    ]
    fig, ax = plt.subplots(figsize=(8.6, 3.8))
    ax.bar(labels, values)
    ax.set_ylabel("Count")
    ax.set_title("Static Analysis Summary")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    fig.savefig(output_img, dpi=180)
    plt.close(fig)


def draw_coverage_chart(data_lcov, output_img):
    labels = ["Line Coverage", "Branch Coverage"]
    values = [data_lcov.get("line_coverage", 0.0), data_lcov.get("branch_coverage", 0.0)]
    fig, ax = plt.subplots(figsize=(5.2, 3.2))
    ax.bar(labels, values)
    ax.set_ylabel("Coverage (%)")
    ax.set_ylim(0, 100)
    ax.set_title("Coverage Summary")
    plt.tight_layout()
    fig.savefig(output_img, dpi=180)
    plt.close(fig)


def draw_tools_pie(cpp_total, clang_total, scan_total, output_img):
    labels = []
    sizes = []
    if cpp_total:
        labels.append("Cppcheck")
        sizes.append(cpp_total)
    if clang_total:
        labels.append("Clang-Tidy")
        sizes.append(clang_total)
    if scan_total:
        labels.append("Scan-Build")
        sizes.append(scan_total)
    if not labels:
        labels, sizes = ["No findings"], [1]
    fig, ax = plt.subplots(figsize=(3.9, 3.9))
    ax.pie(sizes, labels=labels, autopct="%1.0f%%", startangle=90)
    ax.axis("equal")
    ax.set_title("Findings by tool")
    plt.tight_layout()
    fig.savefig(output_img, dpi=180)
    plt.close(fig)


def collect_source_files_from_compile_db(compile_db_path):
    try:
        with open(compile_db_path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
    except Exception as e:
        print(f"ERROR: reading compile DB failed {compile_db_path}: {e}")
        return [], None

    project_root = os.path.dirname(os.path.abspath(compile_db_path))
    source_files = set()
    for entry in data:
        dir_work = entry.get("directory", project_root)
        file_path = entry.get("file", "")
        if not file_path:
            continue
        abs_path = os.path.normpath(file_path if os.path.isabs(file_path) else os.path.join(dir_work, file_path))
        if os.path.isfile(abs_path):
            source_files.add(abs_path)
    return list(source_files), project_root


def parse_includes(source_files, project_root, exclude_patterns=None):
    include_regex = re.compile(r'^\s*#\s*include\s*"(.+?)"')
    exclude_patterns = exclude_patterns or []

    def norm(path):
        return path.replace("\\", "/")

    def is_excluded(rel_path):
        rel_path = norm(rel_path)
        return any(p in rel_path for p in exclude_patterns)

    includes_map = {}
    rel_to_abs = {}

    for full_path in source_files:
        rel = norm(os.path.relpath(full_path, project_root))
        if is_excluded(rel):
            continue
        rel_to_abs[rel] = full_path
        includes_map[rel] = []

    for rel_src, full_path in rel_to_abs.items():
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    m = include_regex.search(line)
                    if not m:
                        continue

                    inc_raw = m.group(1)
                    inc_full = os.path.normpath(os.path.join(os.path.dirname(full_path), inc_raw))

                    try:
                        in_project = os.path.commonpath(
                            [os.path.abspath(project_root), os.path.abspath(inc_full)]
                        ) == os.path.abspath(project_root)
                    except ValueError:
                        in_project = False

                    if not in_project or not os.path.isfile(inc_full):
                        continue

                    rel_inc = norm(os.path.relpath(inc_full, project_root))
                    if is_excluded(rel_inc):
                        continue

                    if rel_inc not in includes_map:
                        includes_map[rel_inc] = []

                    includes_map[rel_src].append(rel_inc)
        except Exception:
            continue

    return includes_map

def file_to_module(rel_path):
    rel_path = rel_path.replace("\\", "/")
    base = os.path.basename(rel_path)
    stem, _ = os.path.splitext(base)

    if rel_path.startswith("tests/"):
        return f"tests::{stem}"

    return stem

from collections import defaultdict

def build_module_dependency_map(includes_map):
    module_deps = defaultdict(set)
    module_files = defaultdict(set)

    for src, targets in includes_map.items():
        src_mod = file_to_module(src)
        module_files[src_mod].add(src)

        for tgt in targets:
            tgt_mod = file_to_module(tgt)
            module_files[tgt_mod].add(tgt)

            if src_mod == tgt_mod:
                continue

            module_deps[src_mod].add(tgt_mod)

    all_modules = set(module_files.keys()) | set(module_deps.keys())
    for mod in all_modules:
        module_deps.setdefault(mod, set())
        module_files.setdefault(mod, set())

    return module_deps, module_files

def compute_module_layers(module_deps):
    memo = {}
    visiting = set()

    def depth(node):
        if node in memo:
            return memo[node]
        if node in visiting:
            return 0

        visiting.add(node)
        deps = module_deps.get(node, set())

        if not deps:
            d = 0
        else:
            d = 1 + max(depth(dep) for dep in deps)

        visiting.remove(node)
        memo[node] = d
        return d

    for node in module_deps:
        depth(node)

    max_depth = max(memo.values()) if memo else 0

    adjusted = {}
    for mod, d in memo.items():
        if mod == "main":
            adjusted[mod] = max_depth + 1
        elif mod.startswith("tests::"):
            adjusted[mod] = max_depth + 2
        else:
            adjusted[mod] = d

    return adjusted

def generate_layer_diagram(includes_map, output_png, graph_name="Project_Layer_Diagram"):
    module_deps, module_files = build_module_dependency_map(includes_map)
    layers_by_module = compute_module_layers(module_deps)

    grouped_layers = defaultdict(list)
    for mod, layer in layers_by_module.items():
        grouped_layers[layer].append(mod)

    ordered_layers = sorted(grouped_layers.keys(), reverse=True)

    dot = Digraph(name=graph_name, format="png")
    dot.attr(
        "graph",
        rankdir="TB",
        splines="ortho",
        nodesep="0.35",
        ranksep="0.65",
        pad="0.2",
        dpi="220",
        bgcolor="white",
    )
    dot.attr(
        "node",
        shape="box",
        style="rounded,filled",
        fillcolor="#EDF5FF",
        color="#1F4E79",
        fontname="Helvetica",
        fontsize="9",
        margin="0.08,0.06",
    )
    dot.attr(
        "edge",
        color="#6B7785",
        arrowsize="0.7",
        penwidth="1.0",
    )

    previous_anchor = None

    for layer in ordered_layers:
        layer_name = f"cluster_layer_{layer}"
        anchor_name = f"layer_anchor_{layer}"

        with dot.subgraph(name=layer_name) as sub:
            sub.attr(
                label=f"Layer {layer}",
                color="#D7DEE5",
                style="rounded",
                fontname="Helvetica-Bold",
                fontsize="11",
                rank="same",
            )

            mods = sorted(grouped_layers[layer])

            for mod in mods:
                files = sorted(module_files.get(mod, []))
                label = f"{mod}\n({len(files)} file{'s' if len(files) != 1 else ''})"
                sub.node(mod, label=label)

            # anchor invisible para forzar apilado vertical entre clusters
            sub.node(anchor_name, label="", shape="point", width="0.01", style="invis")

        if previous_anchor is not None:
            dot.edge(previous_anchor, anchor_name, style="invis")
        previous_anchor = anchor_name

    for src, deps in module_deps.items():
        for dst in deps:
            dot.edge(src, dst)

    tmp_dir = os.path.dirname(output_png)
    tmp_name = os.path.splitext(os.path.basename(output_png))[0]
    rendered = dot.render(filename=os.path.join(tmp_dir, tmp_name), cleanup=True)
    if os.path.exists(rendered):
        os.replace(rendered, output_png)

# -----------------------------------------------------------------------------
# PDF helpers
# -----------------------------------------------------------------------------
def format_duration(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def sev_bg(sev):
    sev = (sev or "").lower()
    if sev == "error":
        return ERROR_BG
    if sev == "warning":
        return WARNING_BG
    return NOTE_BG
def compute_quality_status(cpp_data, clang_data, summary_lcov, summary_scan, test_data):
    cpp_summary = cpp_data.get("summary", {})
    clang_summary = clang_data.get("summary", {})

    cpp_errors = cpp_summary.get("error", 0)
    cpp_warnings = cpp_summary.get("warning", 0)
    clang_errors = clang_summary.get("error", 0)
    clang_warnings = clang_summary.get("warning", 0)
    scan_bugs = summary_scan.get("bugs", 0)
    line_cov = summary_lcov.get("line_coverage", 0.0)
    failed_tests = test_data.get("failed", 0) if test_data.get("available") else 0

    score = 100
    score -= cpp_errors * 8
    score -= clang_errors * 8
    score -= scan_bugs * 12
    score -= cpp_warnings * 2
    score -= clang_warnings * 2
    score -= failed_tests * 10

    if line_cov < 80:
        score -= int((80 - line_cov) * 0.8)

    score = max(0, min(100, score))

    if score >= 80:
        return {
            "label": "GOOD",
            "color": SUCCESS,
            "score": score,
            "message": "The codebase shows a good overall quality level with controlled findings and acceptable validation signals.",
        }
    elif score >= 55:
        return {
            "label": "WARNING",
            "color": WARNING_BG,
            "score": score,
            "message": "The codebase is in an intermediate state. Review of key findings is recommended before release.",
        }
    else:
        return {
            "label": "CRITICAL",
            "color": ERROR_BG,
            "score": score,
            "message": "The codebase presents relevant quality risks that should be addressed before considering it stable.",
        }

def quality_gate_table(status, styles):
    rows = [
        ["Quality gate", "Score", "Assessment"],
        [
            status["label"],
            f"{status['score']}/100",
            Paragraph(status["message"], styles["BodySmall"]),
        ],
    ]
    tbl = make_summary_table(rows, [1.2 * inch, 0.9 * inch, 4.4 * inch], header_bg=ACCENT)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 1), (0, 1), status["color"]),
        ("BACKGROUND", (1, 1), (1, 1), status["color"]),
    ]))
    return tbl

def build_top_problems(cpp_data, clang_data, summary_scan, limit=10):
    severity_weight = {
        "error": 100,
        "warning": 60,
        "style": 25,
        "information": 20,
        "portability": 35,
        "performance": 40,
        "note": 15,
        "unknown": 10,
    }

    grouped = {}

    for item in cpp_data.get("issues", []) + clang_data.get("issues", []):
        check = item.get("check", "unknown")
        sev = item.get("severity", "unknown").lower()
        tool = item.get("tool", "-")
        key = (tool, check, sev)

        if key not in grouped:
            grouped[key] = {
                "tool": tool,
                "check": check,
                "severity": sev,
                "count": 0,
                "sample_file": item.get("file", "-"),
                "sample_line": item.get("line", "-"),
                "sample_message": item.get("message", "-"),
            }

        grouped[key]["count"] += 1

    ranked = []
    for _, entry in grouped.items():
        base = severity_weight.get(entry["severity"], 10)
        impact = base + (entry["count"] - 1) * 8
        entry["impact"] = impact
        ranked.append(entry)

    if summary_scan.get("bugs", 0) > 0:
        ranked.append({
            "tool": "Scan-Build",
            "check": "scan-build-bugs",
            "severity": "error",
            "count": summary_scan.get("bugs", 0),
            "sample_file": "-",
            "sample_line": "-",
            "sample_message": f"{summary_scan.get('bugs', 0)} bug(s) reported by scan-build",
            "impact": 120 + (summary_scan.get("bugs", 0) - 1) * 10,
        })

    ranked.sort(key=lambda x: (-x["impact"], -x["count"], x["tool"], x["check"]))
    return ranked[:limit]

def top_problems_table(top_problems, styles):
    rows = [["Impact", "Tool", "Severity", "Check", "Occurrences", "Sample location", "Message"]]

    if not top_problems:
        rows.append(["-", "-", "-", "No issues", "0", "-", "-"])
    else:
        for item in top_problems:
            location = item.get("sample_file", "-")
            if item.get("sample_line") not in ("", "-", None):
                location += f":{item.get('sample_line')}"
            rows.append([
                str(item.get("impact", 0)),
                item.get("tool", "-"),
                item.get("severity", "-"),
                Paragraph(trim_text(item.get("check", "-"), 28), styles["BodySmall"]),
                str(item.get("count", 0)),
                Paragraph(trim_text(location, 28), styles["BodySmall"]),
                Paragraph(trim_text(item.get("sample_message", "-"), 52), styles["BodySmall"]),
            ])

    return make_summary_table(
        rows,
        [0.6 * inch, 0.9 * inch, 0.7 * inch, 1.45 * inch, 0.7 * inch, 1.35 * inch, 1.95 * inch],
        header_bg=ACCENT,
    )

def trim_text(text, limit=115):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def make_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=23, leading=28, textColor=ACCENT, alignment=TA_CENTER, spaceAfter=8))
    styles.add(ParagraphStyle(name="ReportSubtitle", parent=styles["BodyText"], fontName="Helvetica", fontSize=10.5, leading=14, textColor=MUTED, alignment=TA_CENTER, spaceAfter=18))
    styles.add(ParagraphStyle(name="SectionTitle", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=ACCENT, spaceAfter=10, spaceBefore=4))
    styles.add(ParagraphStyle(name="SubTitle", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=TEXT, spaceAfter=6, spaceBefore=8))
    styles.add(ParagraphStyle(
        name="BodySmall",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.2,
        leading=9.5,
        textColor=TEXT,
        spaceAfter=0,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(name="Metric", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=ACCENT, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="MetricLabel", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.7, leading=11, textColor=MUTED, alignment=TA_CENTER))
    return styles


class NumberedCanvasMixin:
    pass


def on_page(canvas, doc):
    canvas.saveState()
    width, height = letter
    canvas.setStrokeColor(ACCENT)
    canvas.setLineWidth(0.8)
    canvas.line(doc.leftMargin, height - 0.62 * inch, width - doc.rightMargin, height - 0.62 * inch)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillColor(ACCENT)
    canvas.drawString(doc.leftMargin, height - 0.52 * inch, getattr(doc, "project_name", "Static analysis report"))
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(width - doc.rightMargin, 0.45 * inch, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def build_metric_row(metrics, styles):
    cells = []
    for value, label, bg in metrics:
        tbl = Table(
            [[Paragraph(str(value), styles["Metric"])], [Paragraph(label, styles["MetricLabel"])]],
            colWidths=[1.65 * inch],
        )
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("BOX", (0, 0), (-1, -1), 0.7, GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        cells.append(tbl)
    return Table([cells], colWidths=[1.75 * inch] * len(cells), hAlign="LEFT", style=TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))


def make_summary_table(rows, widths, header_bg=ACCENT):
    normalized_rows = []
    expected_len = len(rows[0]) if rows else 0
    for row in rows:
        new_row = list(row)
        if len(new_row) < expected_len:
            new_row.extend([""] * (expected_len - len(new_row)))
        elif len(new_row) > expected_len:
            new_row = new_row[:expected_len]
        normalized_rows.append(new_row)

    table = Table(normalized_rows, colWidths=widths, repeatRows=1)
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.7),
        ("LEADING", (0, 0), (-1, -1), 11),
        ("GRID", (0, 0), (-1, -1), 0.45, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("WORDWRAP", (0, 0), (-1, -1), "CJK"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ])
    for row_idx in range(1, len(normalized_rows)):
        bg = colors.whitesmoke if row_idx % 2 == 0 else WHITE
        style.add("BACKGROUND", (0, row_idx), (-1, row_idx), bg)
    table.setStyle(style)
    return table

def top_files_table(file_map, styles, title, limit=12):
    rows = [[title, "Total", "Errors", "Warnings", "Other"]]
    ranking = sorted(file_map.items(), key=lambda kv: (-kv[1].get("total", 0), kv[0]))[:limit]
    if not ranking:
        rows.append(["No findings", "0", "0", "0", "0"])
    else:
        for path, counts in ranking:
            other = counts.get("information", 0) + counts.get("style", 0) + counts.get("portability", 0) + counts.get("performance", 0) + counts.get("note", 0) + counts.get("unknown", 0)
            rows.append([
                Paragraph(trim_text(path, 58), styles["BodySmall"]),
                str(counts.get("total", 0)),
                str(counts.get("error", 0)),
                str(counts.get("warning", 0)),
                str(other),
            ])
    return make_summary_table(rows, [3.9 * inch, 0.65 * inch, 0.7 * inch, 0.75 * inch, 0.65 * inch], header_bg=ACCENT)


def top_checks_table(checks, styles, title, limit=12):
    rows = [[title, "Count"]]
    ranking = sorted(checks.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    if not ranking:
        rows.append(["No data", "0"])
    else:
        for name, count in ranking:
            rows.append([Paragraph(trim_text(name, 70), styles["BodySmall"]), str(count)])
    return make_summary_table(rows, [5.3 * inch, 1.1 * inch], header_bg=ACCENT)


def combined_top_checks_table(cpp_checks, clang_checks, styles, limit=12):
    rows = [["Cppcheck check", "Count", "Clang diagnostic", "Count"]]

    cpp_ranking = sorted(cpp_checks.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    clang_ranking = sorted(clang_checks.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]

    max_len = max(len(cpp_ranking), len(clang_ranking), 1)

    for i in range(max_len):
        cpp_name = ""
        cpp_count = ""
        clang_name = ""
        clang_count = ""

        if i < len(cpp_ranking):
            cpp_name, cpp_count = cpp_ranking[i]
            cpp_name = Paragraph(trim_text(str(cpp_name), 42), styles["BodySmall"])
            cpp_count = str(cpp_count)

        if i < len(clang_ranking):
            clang_name, clang_count = clang_ranking[i]
            clang_name = Paragraph(trim_text(str(clang_name), 42), styles["BodySmall"])
            clang_count = str(clang_count)

        rows.append([cpp_name, cpp_count, clang_name, clang_count])

    if max_len == 1 and not cpp_ranking and not clang_ranking:
        rows.append(["No data", "0", "No data", "0"])

    return make_summary_table(
        rows,
        [2.7 * inch, 0.6 * inch, 2.7 * inch, 0.6 * inch],
        header_bg=ACCENT,
    )


def issues_table(issues, styles, title, limit=18):
    rows = [[title, "Sev.", "Check", "Location", "Message"]]

    subset = sorted(
        issues,
        key=lambda x: (
            {"error": 0, "warning": 1}.get(x.get("severity"), 2),
            x.get("file", ""),
            int(x.get("line") or 0),
        ),
    )[:limit]

    if not subset:
        rows.append(["No findings", "-", "-", "-", "-"])
    else:
        for item in subset:
            location = item.get("file", "-")
            if item.get("line"):
                location += f":{item.get('line')}"

            rows.append([
                Paragraph(trim_text(item.get("tool", "-"), 14), styles["BodySmall"]),
                Paragraph(trim_text(item.get("severity", "-"), 12), styles["BodySmall"]),
                Paragraph(trim_text(item.get("check", "-"), 24), styles["BodySmall"]),
                Paragraph(trim_text(location, 28), styles["BodySmall"]),
                Paragraph(trim_text(item.get("message", "-"), 60), styles["BodySmall"]),
            ])

    tbl = Table(
        rows,
        colWidths=[0.9 * inch, 0.65 * inch, 1.45 * inch, 1.55 * inch, 2.25 * inch],
        repeatRows=1,
    )

    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("LEADING", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.45, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ])

    for row_idx in range(1, len(rows)):
        bg = colors.whitesmoke if row_idx % 2 == 0 else WHITE
        style.add("BACKGROUND", (0, row_idx), (-1, row_idx), bg)

    tbl.setStyle(style)
    return tbl

def make_relative_to_project(path, project_root):
    if not path:
        return "-"

    try:
        abs_path = os.path.abspath(path)
        abs_root = os.path.abspath(project_root) if project_root else ""

        if abs_root:
            common = os.path.commonpath([abs_root, abs_path])
            if common == abs_root:
                return os.path.relpath(abs_path, abs_root)
    except Exception:
        pass

    return path


def relativize_analysis_data(cpp_data, clang_data, project_root):
    for dataset in (cpp_data, clang_data):
        new_files = {}
        for path, counts in dataset.get("files", {}).items():
            new_files[make_relative_to_project(path, project_root)] = counts
        dataset["files"] = new_files

        for item in dataset.get("issues", []):
            item["file"] = make_relative_to_project(item.get("file", ""), project_root)
    return cpp_data, clang_data


def relativize_coverage_data(summary_lcov, project_root):
    new_files = {}
    for path, stats in summary_lcov.get("files", {}).items():
        new_files[make_relative_to_project(path, project_root)] = stats
    summary_lcov["files"] = new_files
    return summary_lcov


def coverage_by_file_table(coverage_files, styles, limit=15):
    rows = [["File", "Lines", "Line %", "Branches", "Branch %"]]
    ranking = sorted(
        coverage_files.items(),
        key=lambda kv: (kv[1].get("line_coverage", 0.0), kv[1].get("lines_found", 0), kv[0]),
    )[:limit]
    if not ranking:
        rows.append(["No coverage data", "-", "-", "-", "-"])
    else:
        for path, stats in ranking:
            rows.append([
                Paragraph(trim_text(path, 52), styles["BodySmall"]),
                f"{stats.get('lines_hit', 0)} / {stats.get('lines_found', 0)}",
                f"{stats.get('line_coverage', 0.0):.1f}%",
                f"{stats.get('branches_hit', 0)} / {stats.get('branches_found', 0)}",
                f"{stats.get('branch_coverage', 0.0):.1f}%" if stats.get('branches_found', 0) else "-",
            ])
    return make_summary_table(rows, [2.9 * inch, 0.95 * inch, 0.75 * inch, 1.0 * inch, 0.75 * inch], header_bg=ACCENT)

def scoring_methodology_text(styles):
    quality_text = (
        "<b>Quality scoring model.</b> "
        "The quality gate is computed from a weighted score initialized at 100 points. "
        "Penalties are applied based on static-analysis errors and warnings, scan-build bugs, "
        "failed automated tests, and line coverage below the target threshold. "
        "Errors and scan-build findings have a stronger negative impact than warnings. "
        "The resulting score is clamped to the range 0–100 and mapped to a qualitative gate: "
        "<b>GOOD</b> (score ≥ 80), <b>WARNING</b> (55–79), and <b>CRITICAL</b> (&lt; 55)."
    )

    quality_formula = (
        "<b>Quality formula:</b><br/>"
        "Score = 100"
        " - 8×Cppcheck errors"
        " - 8×Clang-Tidy errors"
        " - 12×scan-build bugs"
        " - 2×Cppcheck warnings"
        " - 2×Clang-Tidy warnings"
        " - 10×failed tests"
        " - coverage penalty if line coverage &lt; 80%<br/>"
        "Coverage penalty = (80 - line coverage) × 0.8"
    )

    problem_text = (
        "<b>Problem impact scoring model.</b> "
        "Top problems are ranked using an impact score that combines the base severity of a finding "
        "with its recurrence count. Higher-severity findings receive a larger base weight, and repeated "
        "occurrences increase the final score. This helps prioritize both critical findings and systematic issues."
    )

    problem_formula = (
        "<b>Problem impact formula:</b><br/>"
        "Impact = severity base weight + 8×(occurrences - 1)<br/>"
        "Base weights: error=100, warning=60, performance=40, portability=35, "
        "style=25, information=20, note=15, unknown=10.<br/>"
        "scan-build findings are treated as critical with Impact = 120 + 10×(bugs - 1)."
    )

    return [
        Paragraph("Scoring methodology", styles["SubTitle"]),
        Paragraph(quality_text, styles["BodySmall"]),
        Paragraph(quality_formula, styles["BodySmall"]),
        Spacer(1, 0.05 * inch),
        Paragraph(problem_text, styles["BodySmall"]),
        Paragraph(problem_formula, styles["BodySmall"]),
    ]


def create_pdf(
    project_name,
    analyst,
    machine,
    cpu_model,
    os_info,
    elapsed_sec,
    cpu_cores,
    total_memory,
    cpp_data,
    clang_data,
    summary_lcov,
    summary_scan,
    test_data,
    chart_img_path,
    coverage_chart_img_path,
    tool_mix_chart_path,
    layer_diagram_png,
    output_pdf,
    test_log_path=None,
    main_html_report=None,
    clang_tidy_html=None,
    coverage_html=None,
    clang_analyzer_html=None,
    company_name="My company",
    logo_path=None,
    report_version="1.0",
):
    styles = make_styles()
    doc = BaseDocTemplate(
        output_pdf,
        pagesize=letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.7 * inch,
    )
    doc.project_name = project_name
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=on_page)])

    cpp_summary = cpp_data["summary"]
    clang_summary = clang_data["summary"]
    cpp_total = len(cpp_data["issues"])
    clang_total = len(clang_data["issues"])
    scan_total = summary_scan.get("bugs", 0)
    total_findings = cpp_total + clang_total + scan_total
    quality_status = compute_quality_status(cpp_data, clang_data, summary_lcov, summary_scan, test_data)
    top_problems = build_top_problems(cpp_data, clang_data, summary_scan, limit=10)

    story = []

    if logo_path and os.path.isfile(logo_path):
        story.append(Image(logo_path, width=1.4 * inch, height=1.4 * inch, hAlign="CENTER"))
        story.append(Spacer(1, 0.08 * inch))
    story.append(Paragraph("Static Code Analysis Report", styles["ReportTitle"]))
    subtitle = f"{project_name} &nbsp;&nbsp;|&nbsp;&nbsp; Generated {datetime.now().strftime('%d %b %Y, %H:%M')} &nbsp;&nbsp;|&nbsp;&nbsp; Version {report_version}"
    story.append(Paragraph(subtitle, styles["ReportSubtitle"]))

    metrics = [
        (quality_status["label"], "Quality gate", quality_status["color"]),
        (total_findings, "Total findings", NOTE_BG),
        (clang_total + cpp_total, "Static findings", NOTE_BG),
        (f"{summary_lcov.get('line_coverage', 0.0):.1f}%", "Line coverage", SUCCESS if summary_lcov.get("line_coverage", 0.0) >= 80 else WARNING_BG),
    ]
    story.append(build_metric_row(metrics, styles))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Executive summary", styles["SectionTitle"]))
    summary_text = (
        f"This report consolidates the results from Cppcheck, Clang-Tidy, scan-build, coverage collection and automated test execution. "
        f"The analysis completed in {format_duration(elapsed_sec)} on <b>{machine}</b> by <b>{analyst}</b>. "
        f"Cppcheck reported <b>{cpp_total}</b> findings, Clang-Tidy reported <b>{clang_total}</b> findings and scan-build reported <b>{scan_total}</b> bug(s)."
    )
    story.append(Paragraph(summary_text, styles["BodySmall"]))
    story.append(Spacer(1, 0.08 * inch))

    env_rows = [
        [
            Paragraph("Project", styles["BodySmall"]),
            Paragraph(trim_text(project_name, 40), styles["BodySmall"]),
            Paragraph("Analyst", styles["BodySmall"]),
            Paragraph(trim_text(analyst, 28), styles["BodySmall"]),
        ],
        [
            Paragraph("Machine", styles["BodySmall"]),
            Paragraph(trim_text(machine, 40), styles["BodySmall"]),
            Paragraph("Execution time", styles["BodySmall"]),
            Paragraph(format_duration(elapsed_sec), styles["BodySmall"]),
        ],
        [
            Paragraph("CPU", styles["BodySmall"]),
            Paragraph(trim_text(cpu_model, 52), styles["BodySmall"]),
            Paragraph("CPU cores", styles["BodySmall"]),
            Paragraph(str(cpu_cores), styles["BodySmall"]),
        ],
        [
            Paragraph("Operating system", styles["BodySmall"]),
            Paragraph(trim_text(os_info, 45), styles["BodySmall"]),
            Paragraph("Total memory", styles["BodySmall"]),
            Paragraph(trim_text(total_memory, 20), styles["BodySmall"]),
        ],
        [
            Paragraph("Company", styles["BodySmall"]),
            Paragraph(trim_text(company_name, 40), styles["BodySmall"]),
            Paragraph("Report version", styles["BodySmall"]),
            Paragraph(trim_text(report_version, 12), styles["BodySmall"]),
        ],
    ]

    env_tbl = make_summary_table(
        [["Field", "Value", "Field", "Value"]] + env_rows,
        [1.15 * inch, 2.15 * inch, 1.15 * inch, 2.05 * inch],
    )
    story.append(env_tbl)
    story.append(Spacer(1, 0.16 * inch))

    if any([main_html_report, clang_tidy_html, coverage_html, clang_analyzer_html]):
        story.append(Paragraph("Direct links", styles["SubTitle"]))
        links = []
        for label, path in [
            ("Main HTML report", main_html_report),
            ("Clang-Tidy HTML report", clang_tidy_html),
            ("Coverage HTML report", coverage_html),
            ("Clang Static Analyzer HTML report", clang_analyzer_html),
        ]:
            if path:
                url = path
                if not re.match(r"^[a-zA-Z]+://", path):
                    url = "file://" + os.path.abspath(path)
                links.append(f"• <link href='{url}' color='blue'>{label}</link>")
        if links:
            story.append(Paragraph("<br/>".join(links), styles["BodySmall"]))

    story.append(PageBreak())

    story.append(Paragraph("Global results", styles["SectionTitle"]))
    result_rows = [["Tool", "Errors", "Warnings", "Info/Style/Other", "Total"]]
    result_rows.append([
        "Cppcheck",
        str(cpp_summary.get("error", 0)),
        str(cpp_summary.get("warning", 0)),
        str(sum(cpp_summary.get(k, 0) for k in ["information", "style", "portability", "performance", "note", "unknown"])),
        str(cpp_total),
    ])
    result_rows.append([
        "Clang-Tidy",
        str(clang_summary.get("error", 0)),
        str(clang_summary.get("warning", 0)),
        str(clang_summary.get("note", 0)),
        str(clang_total),
    ])
    result_rows.append([
        "Scan-Build",
        str(summary_scan.get("bugs", 0)),
        "0",
        "0",
        str(summary_scan.get("bugs", 0)),
    ])
    story.append(make_summary_table(result_rows, [2.2 * inch, 0.9 * inch, 0.9 * inch, 1.5 * inch, 0.8 * inch]))
    story.append(Spacer(1, 0.16 * inch))

    charts_row = []
    if chart_img_path and os.path.isfile(chart_img_path):
        charts_row.append(Image(chart_img_path, width=4.45 * inch, height=1.95 * inch))
    if tool_mix_chart_path and os.path.isfile(tool_mix_chart_path):
        charts_row.append(Image(tool_mix_chart_path, width=2.0 * inch, height=2.0 * inch))
    if charts_row:
        if len(charts_row) == 2:
            story.append(Table([charts_row], colWidths=[4.55 * inch, 2.0 * inch]))
        else:
            story.append(charts_row[0])
        story.append(Spacer(1, 0.14 * inch))

    story.append(Spacer(1, 0.14 * inch))
    story.append(Paragraph("Code quality gate", styles["SubTitle"]))
    story.append(quality_gate_table(quality_status, styles))
    story.append(Spacer(1, 0.14 * inch))

    story.append(Paragraph("Top problems by impact", styles["SubTitle"]))
    story.append(top_problems_table(top_problems, styles))
    story.append(Spacer(1, 0.12 * inch))

    for elem in scoring_methodology_text(styles):
        story.append(elem)
    story.append(Spacer(1, 0.12 * inch))


    story.append(Paragraph("Most affected files", styles["SubTitle"]))
    story.append(top_files_table(cpp_data["files"], styles, "Cppcheck file"))
    story.append(Spacer(1, 0.08 * inch))
    story.append(top_files_table(clang_data["files"], styles, "Clang file"))
    story.append(PageBreak())

    story.append(Paragraph("Checks and diagnostics", styles["SectionTitle"]))
    story.append(Paragraph("Top checks by frequency", styles["SubTitle"]))
    story.append(combined_top_checks_table(cpp_data["checks"], clang_data["checks"], styles, limit=12))
    story.append(Spacer(1, 0.12 * inch))

    story.append(Paragraph("Representative findings", styles["SubTitle"]))
    story.append(issues_table(cpp_data["issues"], styles, "Cppcheck"))
    story.append(Spacer(1, 0.08 * inch))
    story.append(issues_table(clang_data["issues"], styles, "Clang-Tidy"))
    story.append(PageBreak())

    story.append(Paragraph("Coverage and automated tests", styles["SectionTitle"]))
    cov_metrics = [
        (f"{summary_lcov.get('line_coverage', 0.0):.1f}%", "Line coverage", SUCCESS if summary_lcov.get("line_coverage", 0.0) >= 80 else WARNING_BG),
        (f"{summary_lcov.get('branch_coverage', 0.0):.1f}%", "Branch coverage", SUCCESS if summary_lcov.get("branch_coverage", 0.0) >= 70 else WARNING_BG),
        (test_data.get("passed", 0) if test_data.get("available") else "-", "Tests passed", SUCCESS if test_data.get("failed", 0) == 0 and test_data.get("available") else NOTE_BG),
        (test_data.get("failed", 0) if test_data.get("available") else "-", "Tests failed", ERROR_BG if test_data.get("failed", 0) else SUCCESS),
    ]
    story.append(build_metric_row(cov_metrics, styles))
    story.append(Spacer(1, 0.16 * inch))

    cov_rows = [
        ["Metric", "Value"],
        ["Covered lines", f"{summary_lcov.get('lines_hit', 0)} / {summary_lcov.get('lines_found', 0)}"],
        ["Line coverage", f"{summary_lcov.get('line_coverage', 0.0):.2f}%"],
        ["Covered branches", f"{summary_lcov.get('branches_hit', 0)} / {summary_lcov.get('branches_found', 0)}"],
        ["Branch coverage", f"{summary_lcov.get('branch_coverage', 0.0):.2f}%"],
        ["scan-build bugs", str(summary_scan.get("bugs", 0))],
    ]
    test_summary_text = "No automatic test execution log was found."
    if test_data.get("available"):
        test_summary_text = test_data.get("summary_line") or f"{test_data.get('passed', 0)} passed / {test_data.get('failed', 0)} failed / {test_data.get('total', 0)} total"
        cov_rows.append(["Automated tests", test_summary_text])
    story.append(make_summary_table(cov_rows, [2.3 * inch, 4.1 * inch]))
    story.append(Spacer(1, 0.14 * inch))

    coverage_files = summary_lcov.get("files", {})
    if coverage_files:
        story.append(Paragraph("Coverage by file", styles["SubTitle"]))
        story.append(coverage_by_file_table(coverage_files, styles, limit=18))
        story.append(Spacer(1, 0.14 * inch))

    if test_data.get("available") and test_data.get("raw_overview"):
        story.append(Paragraph("Detailed automatic test execution", styles["SubTitle"]))
        test_rows = [["#", "Test", "Status"]]
        for entry in test_data["raw_overview"][:20]:
            status_label = "Passed" if entry["status"] == "passed" else "Failed"
            test_rows.append([
                str(entry.get("index", "-")),
                Paragraph(trim_text(entry.get("name", "-"), 65), styles["BodySmall"]),
                status_label,
            ])
        test_tbl = make_summary_table(test_rows, [0.5 * inch, 4.9 * inch, 1.1 * inch])
        story.append(test_tbl)
        story.append(Spacer(1, 0.14 * inch))

    elements = []
    if coverage_chart_img_path and os.path.isfile(coverage_chart_img_path):
        elements.append(Image(coverage_chart_img_path, width=3.45 * inch, height=2.15 * inch))
    failed_rows = [["Failed tests"]]
    if test_data.get("available") and test_data.get("failed_tests"):
        for name in test_data["failed_tests"][:12]:
            failed_rows.append([Paragraph(trim_text(name, 55), styles["BodySmall"])])
    else:
        failed_rows.append([Paragraph("No failed tests recorded.", styles["BodySmall"])])
    failed_tbl = make_summary_table(failed_rows, [3.0 * inch])
    elements.append(failed_tbl)

    if len(elements) == 2:
        story.append(Table([elements], colWidths=[3.5 * inch, 2.8 * inch], style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")])))
    else:
        story.append(elements[0])

    story.append(PageBreak())
    story.append(Paragraph("Include dependency overview", styles["SectionTitle"]))
    story.append(Paragraph("This layered diagram groups project files into logical modules inferred from include relationships. Upper layers depend on lower layers according to the include structure detected in the project sources.", styles["BodySmall"]))
    story.append(Spacer(1, 0.08 * inch))
    if layer_diagram_png and os.path.isfile(layer_diagram_png):
        story.append(Image(layer_diagram_png, width=6.5 * inch, height=6.8 * inch))
    else:
        story.append(Paragraph("Include diagram not available.", styles["BodySmall"]))

    doc.build(story)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Static code analysis report PDF generator")
    parser.add_argument("--cppcheck-xml", required=True)
    parser.add_argument("--clang-tidy-report", required=True)
    parser.add_argument("--compile-db", required=True)
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--output-pdf", required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--analyst", required=True)
    parser.add_argument("--machine", required=True)
    parser.add_argument("--cpu-model", required=True)
    parser.add_argument("--os-info", required=True)
    parser.add_argument("--elapsed-seconds", type=int, required=True)
    parser.add_argument("--cpu-cores", required=True)
    parser.add_argument("--total-memory", required=True)
    parser.add_argument("--lcov-info", default=None)
    parser.add_argument("--scan-build-log", default=None)
    parser.add_argument("--ctest-log", default=None)
    parser.add_argument("--main-html-report", default=None)
    parser.add_argument("--clang-tidy-html", default=None)
    parser.add_argument("--coverage-html", default=None)
    parser.add_argument("--clang-analyzer-html", default=None)
    parser.add_argument("--company-name", default="My company")
    parser.add_argument("--logo-path", default=None)
    parser.add_argument("--report-version", default="1.0")
    args = parser.parse_args()

    cpp_data = parse_cppcheck(args.cppcheck_xml)
    clang_data = parse_clang_tidy(args.clang_tidy_report)
    summary_lcov = parse_lcov_info(args.lcov_info)
    summary_scan = parse_scan_build_log(args.scan_build_log)
    test_data = parse_ctest_log(args.ctest_log)

    cpp_data, clang_data = relativize_analysis_data(cpp_data, clang_data, args.project_root)
    summary_lcov = relativize_coverage_data(summary_lcov, args.project_root)

    tmpdir = tempfile.mkdtemp(prefix="summary_pdf_")
    chart_path = os.path.join(tmpdir, "summary_chart.png")
    coverage_chart_path = os.path.join(tmpdir, "coverage_chart.png")
    tool_mix_chart_path = os.path.join(tmpdir, "tool_mix_chart.png")

    draw_bar_chart(cpp_data["summary"], clang_data["summary"], summary_scan, chart_path)
    draw_coverage_chart(summary_lcov, coverage_chart_path)
    draw_tools_pie(len(cpp_data["issues"]), len(clang_data["issues"]), summary_scan.get("bugs", 0), tool_mix_chart_path)

    source_files, project_root = collect_source_files_from_compile_db(args.compile_db)
    layer_diagram_png = None
    if project_root and source_files:
        includes_map = parse_includes(
            source_files,
            project_root,
            exclude_patterns=[]
        )
        layer_diagram_png = os.path.join(tmpdir, "layer_diagram.png")
        try:
            generate_layer_diagram(includes_map, layer_diagram_png)
        except Exception as e:
            print(f"WARNING: unable to generate code diagram: {e}")
            layer_diagram_png = None

    create_pdf(
        project_name=args.project_name,
        analyst=args.analyst,
        machine=args.machine,
        cpu_model=args.cpu_model,
        os_info=args.os_info,
        elapsed_sec=args.elapsed_seconds,
        cpu_cores=args.cpu_cores,
        total_memory=args.total_memory,
        cpp_data=cpp_data,
        clang_data=clang_data,
        summary_lcov=summary_lcov,
        summary_scan=summary_scan,
        test_data=test_data,
        chart_img_path=chart_path,
        coverage_chart_img_path=coverage_chart_path,
        tool_mix_chart_path=tool_mix_chart_path,
        layer_diagram_png=layer_diagram_png,
        output_pdf=args.output_pdf,
        test_log_path=args.ctest_log,
        main_html_report=args.main_html_report,
        clang_tidy_html=args.clang_tidy_html,
        coverage_html=args.coverage_html,
        clang_analyzer_html=args.clang_analyzer_html,
        company_name=args.company_name,
        logo_path=args.logo_path,
        report_version=args.report_version,
    )

    shutil.rmtree(tmpdir, ignore_errors=True)
    print(f"PDF generated in: {args.output_pdf}")


if __name__ == "__main__":
    main()