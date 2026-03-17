#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
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

@file    generate_clang_tidy_html.py
@brief   Parse a raw clang-tidy text report and generate structured JSON
         and HTML outputs.

@author  Alejandro Fernández Rodríguez
@date    16 mar 2026
@version 1.0.0
"""

import argparse
import html
import json
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List


DIAG_RE = re.compile(
    r'^(?P<file>/.*?|[A-Za-z]:\\.*?):'
    r'(?P<line>\d+):'
    r'(?P<col>\d+): '
    r'(?P<severity>warning|error|note): '
    r'(?P<message>.*?)(?: \[(?P<check>[^\]]+)\])?$'
)

IGNORE_LINE_RES = [
    re.compile(r'^\d+\s+warnings?\s+generated\.$'),
    re.compile(r"^warning: '__GNUC__' macro redefined"),
    re.compile(r'^note: previous definition is here$'),
]

CODE_LINE_RE = re.compile(r'^\s*\d+\s*\|')
CARET_LINE_RE = re.compile(r'^\s*\|?\s*\^')
INCLUDE_SUMMARY_RE = re.compile(r"Include file: '.*?' not found\.")
CHECKERS_REPORT_RE = re.compile(r'^Active checkers: ')


def should_ignore_line(line: str) -> bool:
    stripped = line.strip()

    for rx in IGNORE_LINE_RES:
        if rx.match(stripped):
            return True

    return False


def relpath_safe(path: str, root: str) -> str:
    if not root:
        return path

    try:
        return os.path.relpath(path, root)
    except Exception:
        return path


def normalize_path(path: str) -> str:
    return os.path.normpath(path)


def parse_report(text: str) -> List[Dict[str, Any]]:
    diagnostics: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        if should_ignore_line(line):
            continue

        match = DIAG_RE.match(line)
        if match:
            current = {
                "file": normalize_path(match.group("file")),
                "line": int(match.group("line")),
                "column": int(match.group("col")),
                "severity": match.group("severity"),
                "message": (match.group("message") or "").strip(),
                "check": (match.group("check") or "").strip(),
                "notes": [],
                "code": [],
            }
            diagnostics.append(current)
            continue

        if current is None:
            continue

        stripped = line.strip()
        if not stripped:
            continue

        if CODE_LINE_RE.match(line) or CARET_LINE_RE.match(line):
            current["code"].append(line)
            continue

        current["notes"].append(stripped)

    return diagnostics


def escape_attr(value: str) -> str:
    return html.escape(value, quote=True)


def build_summary_tables(
    diagnostics: List[Dict[str, Any]],
    project_root: str,
) -> Dict[str, Any]:
    by_file: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    severity_counter: Counter[str] = Counter()
    check_counter: Counter[str] = Counter()

    for diag in diagnostics:
        by_file[diag["file"]].append(diag)
        severity_counter[diag["severity"]] += 1
        if diag["check"]:
            check_counter[diag["check"]] += 1

    sorted_files = dict(
        sorted(by_file.items(), key=lambda item: relpath_safe(item[0], project_root).lower())
    )

    sorted_checks = sorted(check_counter.items(), key=lambda item: (-item[1], item[0].lower()))

    return {
        "by_file": sorted_files,
        "severity_counter": severity_counter,
        "check_counter": check_counter,
        "sorted_checks": sorted_checks,
    }


def build_diagnostics_rows(
    by_file: Dict[str, List[Dict[str, Any]]],
    project_root: str,
) -> str:
    rows: List[str] = []

    for file_path, file_diags in by_file.items():
        rel_file = relpath_safe(file_path, project_root)

        rows.append(
            (
                '<tr class="group-row">'
                f'<td colspan="7"><strong>{html.escape(rel_file)}</strong></td>'
                '</tr>'
            )
        )

        sorted_diags = sorted(
            file_diags,
            key=lambda diag: (diag["line"], diag["column"], diag["severity"], diag["message"])
        )

        for diag in sorted_diags:
            severity = diag["severity"]
            check_name = diag["check"] if diag["check"] else "-"
            base_name = os.path.basename(file_path)
            vscode_link = f'vscode://file/{file_path}:{diag["line"]}:{diag["column"]}'

            notes_html = ""
            if diag["notes"]:
                rendered_notes = "<br>".join(html.escape(note) for note in diag["notes"])
                notes_html = f'<div class="notes">{rendered_notes}</div>'

            code_html = ""
            if diag["code"]:
                rendered_code = "\n".join(diag["code"])
                code_html = f'<pre>{html.escape(rendered_code)}</pre>'

            rows.append(
                (
                    f'<tr class="diag-row sev-{escape_attr(severity)}" '
                    f'data-file="{escape_attr(rel_file.lower())}" '
                    f'data-check="{escape_attr(check_name.lower())}" '
                    f'data-severity="{escape_attr(severity.lower())}">'
                    f'<td><a href="{escape_attr(vscode_link)}">{html.escape(rel_file)}:{diag["line"]}</a></td>'
                    f'<td>{diag["line"]}</td>'
                    f'<td>{diag["column"]}</td>'
                    f'<td>{html.escape(severity)}</td>'
                    f'<td>{html.escape(check_name)}</td>'
                    f'<td>{html.escape(base_name)}</td>'
                    '<td>'
                    f'<div>{html.escape(diag["message"])}</div>'
                    f'{notes_html}'
                    f'{code_html}'
                    '</td>'
                    '</tr>'
                )
            )

    return "\n".join(rows)


def build_checks_rows(sorted_checks: List[Any]) -> str:
    if not sorted_checks:
        return "<tr><td colspan=\"2\">No checks detected</td></tr>"

    rows: List[str] = []
    for check_name, count in sorted_checks:
        rows.append(
            f"<tr><td>{html.escape(check_name)}</td><td>{count}</td></tr>"
        )

    return "\n".join(rows)


def make_bar_chart_svg(title: str, data: list[tuple[str, int]], max_width: int = 900) -> str:
    if not data:
        return (
            f'<div class="chart-block">'
            f'<h3>{html.escape(title)}</h3>'
            f'<p>No data available.</p>'
            f'</div>'
        )

    max_value = max(value for _, value in data)
    if max_value <= 0:
        max_value = 1

    left_label_width = 220
    right_margin = 80
    bar_area_width = max_width - left_label_width - right_margin
    row_height = 36
    top_margin = 20
    chart_height = top_margin + len(data) * row_height + 10

    rows = []
    y = top_margin

    for label, value in data:
        bar_width = int((value / max_value) * bar_area_width)
        safe_label = html.escape(label)

        bar_x = left_label_width
        bar_y = y
        bar_h = 18

        value_text = str(value)

        # Posición por defecto: fuera de la barra
        value_x = bar_x + bar_width + 8
        value_fill = "#111827"
        text_anchor = "start"

        # Si la barra es suficientemente ancha, mete el número dentro
        if bar_width >= 40:
            value_x = bar_x + bar_width - 8
            value_fill = "#ffffff"
            text_anchor = "end"

        # Clamp para que nunca se salga por la derecha
        max_text_x = max_width - 10
        if value_x > max_text_x:
            value_x = max_text_x
            text_anchor = "end"
            value_fill = "#111827"

        rows.append(
            f'<text x="10" y="{y + 14}" font-size="13" fill="#111827">{safe_label}</text>'
            f'<rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_h}" rx="4" ry="4" fill="#60a5fa"></rect>'
            f'<text x="{value_x}" y="{y + 14}" font-size="13" fill="{value_fill}" text-anchor="{text_anchor}">{html.escape(value_text)}</text>'
        )

        y += row_height

    return (
        f'<div class="chart-block">'
        f'<h3>{html.escape(title)}</h3>'
        f'<svg width="{max_width}" height="{chart_height}" viewBox="0 0 {max_width} {chart_height}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{html.escape(title)}">'
        f'{"".join(rows)}'
        f'</svg>'
        f'</div>'
    )

def build_charts_html(
    diagnostics: List[Dict[str, Any]],
    project_root: str,
) -> str:
    severity_counter: Counter[str] = Counter()
    check_counter: Counter[str] = Counter()
    file_counter: Counter[str] = Counter()

    for diag in diagnostics:
        severity_counter[diag["severity"]] += 1
        if diag["check"]:
            check_counter[diag["check"]] += 1
        rel_file = relpath_safe(diag["file"], project_root)
        file_counter[rel_file] += 1

    severity_data = [
        ("warning", severity_counter.get("warning", 0)),
        ("error", severity_counter.get("error", 0)),
        ("note", severity_counter.get("note", 0)),
    ]

    top_checks = sorted(check_counter.items(), key=lambda x: (-x[1], x[0]))[:10]
    top_files = sorted(file_counter.items(), key=lambda x: (-x[1], x[0]))[:10]

    return (
        '<div class="section">'
        '<h2>Charts</h2>'
        '<div class="charts">'
        f'{make_bar_chart_svg("Diagnostics by severity", severity_data)}'
        f'{make_bar_chart_svg("Top checks", top_checks)}'
        f'{make_bar_chart_svg("Top files", top_files)}'
        '</div>'
        '</div>'
    )

def build_html(
    diagnostics: List[Dict[str, Any]],
    project_root: str = "",
    title: str = "Clang-Tidy report",
) -> str:
    summary = build_summary_tables(diagnostics, project_root)

    by_file = summary["by_file"]
    severity_counter = summary["severity_counter"]
    sorted_checks = summary["sorted_checks"]

    diagnostics_rows = build_diagnostics_rows(by_file, project_root)
    checks_rows = build_checks_rows(sorted_checks)

    total = len(diagnostics)
    warning_count = severity_counter.get("warning", 0)
    error_count = severity_counter.get("error", 0)
    note_count = severity_counter.get("note", 0)
    file_count = len(by_file)

    charts_html = build_charts_html(diagnostics, project_root)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
body {{
    font-family: Arial, Helvetica, sans-serif;
    margin: 0;
    background: #f3f4f6;
    color: #111827;
}}

header {{
    background: #111827;
    color: #ffffff;
    padding: 16px 24px;
}}

header h1 {{
    margin: 0;
    font-size: 28px;
}}

main {{
    padding: 20px;
}}

.cards {{
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 20px;
}}

.card {{
    background: #ffffff;
    border-radius: 8px;
    padding: 12px 16px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
    min-width: 140px;
}}

.filters {{
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 20px;
}}

input, select {{
    padding: 8px 10px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    background: #ffffff;
}}

.section {{
    margin-top: 24px;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    background: #ffffff;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
}}

th, td {{
    border: 1px solid #e5e7eb;
    padding: 8px;
    text-align: left;
    vertical-align: top;
}}

th {{
    background: #e5e7eb;
}}

.group-row td {{
    background: #dbeafe;
}}

.sev-warning {{
    background: #fef3c7;
}}

.sev-error {{
    background: #fee2e2;
}}

.sev-note {{
    background: #e0f2fe;
}}

.notes {{
    margin-top: 8px;
    color: #374151;
    font-size: 0.95em;
}}

pre {{
    background: #111827;
    color: #f9fafb;
    padding: 10px;
    border-radius: 6px;
    overflow-x: auto;
    white-space: pre-wrap;
    margin-top: 8px;
}}

a {{
    color: #2563eb;
    text-decoration: none;
}}

a:hover {{
    text-decoration: underline;
}}
</style>
</head>
<body>
<header>
  <h1>{html.escape(title)}</h1>
</header>

<main>
  <div class="cards">
    <div class="card"><strong>Total:</strong> {total}</div>
    <div class="card"><strong>Warnings:</strong> {warning_count}</div>
    <div class="card"><strong>Errors:</strong> {error_count}</div>
    <div class="card"><strong>Notes:</strong> {note_count}</div>
    <div class="card"><strong>Files:</strong> {file_count}</div>
  </div>

  {charts_html}

  <div class="filters">
    <input id="fileFilter" type="text" placeholder="Filter by file">
    <input id="checkFilter" type="text" placeholder="Filter by check">
    <select id="severityFilter">
      <option value="">All severities</option>
      <option value="warning">warning</option>
      <option value="error">error</option>
      <option value="note">note</option>
    </select>
  </div>

  <div class="section">
    <h2>Diagnostics</h2>
    <table id="diagTable">
      <thead>
        <tr>
          <th>Location</th>
          <th>Line</th>
          <th>Column</th>
          <th>Severity</th>
          <th>Check</th>
          <th>File</th>
          <th>Message</th>
        </tr>
      </thead>
      <tbody>
        {diagnostics_rows}
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2>Summary by check</h2>
    <table>
      <thead>
        <tr>
          <th>Check</th>
          <th>Count</th>
        </tr>
      </thead>
      <tbody>
        {checks_rows}
      </tbody>
    </table>
  </div>
</main>

<script>
const fileFilter = document.getElementById('fileFilter');
const checkFilter = document.getElementById('checkFilter');
const severityFilter = document.getElementById('severityFilter');
const rows = Array.from(document.querySelectorAll('tr.diag-row'));

function applyFilters() {{
    const fileVal = fileFilter.value.toLowerCase();
    const checkVal = checkFilter.value.toLowerCase();
    const severityVal = severityFilter.value.toLowerCase();

    rows.forEach((row) => {{
        const file = row.dataset.file || '';
        const check = row.dataset.check || '';
        const severity = row.dataset.severity || '';

        const visible =
            file.includes(fileVal) &&
            check.includes(checkVal) &&
            (!severityVal || severity === severityVal);

        row.style.display = visible ? '' : 'none';
    }});
}}

fileFilter.addEventListener('input', applyFilters);
checkFilter.addEventListener('input', applyFilters);
severityFilter.addEventListener('change', applyFilters);
</script>
</body>
</html>
"""


def validate_input_file(path: str) -> None:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Input file not found: {path}")


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)



def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate JSON and HTML reports from a raw clang-tidy text report."
    )
    parser.add_argument("--input", required=True, help="Raw clang-tidy report text file")
    parser.add_argument("--json-out", required=True, help="Output JSON file")
    parser.add_argument("--html-out", required=True, help="Output HTML file")
    parser.add_argument("--project-root", default="", help="Project root for relative paths")
    parser.add_argument("--title", default="Clang-Tidy report", help="HTML report title")

    args = parser.parse_args()

    try:
        validate_input_file(args.input)

        with open(args.input, "r", encoding="utf-8", errors="replace") as input_file:
            text = input_file.read()

        diagnostics = parse_report(text)

        ensure_parent_dir(args.json_out)
        ensure_parent_dir(args.html_out)

        with open(args.json_out, "w", encoding="utf-8") as json_file:
            json.dump(diagnostics, json_file, indent=2, ensure_ascii=False)

        html_doc = build_html(
            diagnostics=diagnostics,
            project_root=args.project_root,
            title=args.title,
        )

        with open(args.html_out, "w", encoding="utf-8") as html_file:
            html_file.write(html_doc)

        return 0

    except Exception as exc:
        print(f"Error generating clang-tidy HTML report: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())