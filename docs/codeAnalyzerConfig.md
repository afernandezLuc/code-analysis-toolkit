# codeAnalyzerConfig.json Reference

`codeAnalyzerConfig.json` is the input file consumed by `staticCodeAnalysis.sh`.
It tells the analyzer where the project lives, where the compilation database is located, which reports to generate, and how optional features such as coverage and the Clang Static Analyzer should behave.

In most cases, the best workflow is:

1. Generate the file with `./generateCodeAnalyzerConfig.sh /path/to/project`
2. Edit only the fields you need to customize
3. Run `./staticCodeAnalysis.sh /path/to/project/codeAnalyzerConfig.json`

## How the file is interpreted

- Most path fields can be absolute or relative.
- Relative path fields are resolved against the directory that contains `codeAnalyzerConfig.json`, not against `project_root`.
- Command fields are executed with `bash -lc` from `project_root`.
- Array fields such as exclude directories also accept relative paths and are resolved the same way.
- Empty or missing optional fields disable the related feature or allow the script to fall back to its built-in defaults.

## Typical generated config

A freshly generated file usually looks similar to this:

```json
{
  "project_name": "projectExample",
  "build_dir": "build",
  "compile_db": "build/compile_commands.json",
  "c_version": "c11",
  "report_dir": "code_analysis_result",
  "suppressions": ".cppcheck-suppress",
  "cppcheck_suppressions_entries": [],
  "cppcheck_exclude_dirs": [".venv", "codeAnalysisAddons", "code_analysis_result", "build"],
  "clang_tidy_report": "code_analysis_result/clang_tidy_summary.txt",
  "clang_tidy_exclude_dirs": [".venv", "codeAnalysisAddons", "code_analysis_result", "build"],
  "clang_analyzer_enabled": true,
  "clang_analyzer_build_cmd": "cmake --build \"build\" --clean-first",
  "clang_analyzer_output_dir": "code_analysis_result/scan-build",
  "summary_pdf": "code_analysis_result/analysis_summary.pdf",
  "addons_dir": "/absolute/path/to/codeAnalysisAddons",
  "misra_rules_url": "https://gitlab.com/MISRA/MISRA-C/MISRA-C-2012/-/raw/main/tools/misra_c_2023__headlines_for_cppcheck.txt",
  "misra_rules_filename": "misra_rules.txt",
  "extra_defines": ["-D__GNUC__"],
  "coverage_enabled": true,
  "coverage_capture_dir": "build",
  "coverage_base_dir": ".",
  "coverage_info": "code_analysis_result/coverage.info",
  "coverage_html_dir": "code_analysis_result/coverage-html"
}
```

## Field-by-field reference

The analyzer supports a few advanced optional keys that are not emitted by `generateCodeAnalyzerConfig.sh` by default, such as `project_root`, `coverage_build_dir`, `coverage_configure_cmd`, `coverage_build_cmd`, and `coverage_run_cmd`.

### `project_root`

- Type: `string`
- Required: No
- Used for: Defines the root directory of the analyzed project and the working directory used for generated reports, automatic coverage commands, and `scan-build`.
- Configure it: Leave it unset when the JSON file is stored in the project root. Set it when the JSON file lives somewhere else.

### `project_name`

- Type: `string`
- Required: No
- Used for: Sets the display name shown in generated reports, especially the PDF summary and report titles.
- Configure it: Use a short human-readable project name. If omitted, the script falls back to `Unknown`.

### `build_dir`

- Type: `string`
- Required: Yes
- Used for: Points to the main build directory. The script also uses it to store temporary helper files such as filtered compilation databases and generated suppression files.
- Configure it: Set it to the build directory that matches your current `compile_commands.json`.

### `compile_db`

- Type: `string`
- Required: Yes
- Used for: Path to `compile_commands.json`, which drives `cppcheck` and `clang-tidy`.
- Configure it: Point it to a valid compilation database. For CMake, generate it with `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON`.

### `c_version`

- Type: `string`
- Required: Yes
- Used for: Passed to `cppcheck` as `--std`.
- Configure it: Use a value supported by `cppcheck`, such as `c99`, `c11`, or `c17`, matching the language level of your project.

### `report_dir`

- Type: `string`
- Required: Yes
- Used for: Root output directory for the XML, HTML, logs, coverage files, and the PDF summary.
- Configure it: Usually set this to `code_analysis_result` inside the analyzed project.

### `suppressions`

- Type: `string`
- Required: No
- Used for: Optional input file containing persistent `cppcheck` suppressions.
- Configure it: Use this when you want a version-controlled suppression file. The analyzer copies its contents into a temporary generated suppression file under `build_dir`, so this path is treated as input, not as the final runtime file used by `cppcheck`.

### `cppcheck_suppressions_entries`

- Type: `array[string]`
- Required: No
- Used for: Adds extra `cppcheck` suppressions without needing a separate file.
- Configure it: Each array item becomes one line in the generated suppression file. Use the same syntax accepted by `cppcheck --suppressions-list`, for example `missingIncludeSystem` or a file-specific suppression.

### `cppcheck_exclude_dirs`

- Type: `array[string]`
- Required: No
- Used for: Removes directories from the filtered compilation database used by `cppcheck`.
- Configure it: Add generated code, vendor code, or external directories that you do not want `cppcheck` to analyze.

### `clang_tidy_report`

- Type: `string`
- Required: Yes
- Used for: Output file that stores the raw `clang-tidy` text report.
- Configure it: Keep it inside `report_dir`, for example `code_analysis_result/clang_tidy_summary.txt`.

### `clang_tidy_exclude_dirs`

- Type: `array[string]`
- Required: No
- Used for: Excludes files and directories from the `clang-tidy` file list.
- Configure it: Use it for third-party code, generated sources, or directories that should not be linted.

### `clang_analyzer_enabled`

- Type: `boolean`
- Required: No
- Used for: Enables or disables the Clang Static Analyzer stage run through `scan-build`.
- Configure it: Set it to `true` only when the project can be rebuilt successfully with the command defined in `clang_analyzer_build_cmd`.

### `clang_analyzer_build_cmd`

- Type: `string`
- Required: Yes when `clang_analyzer_enabled` is `true`
- Used for: Build command wrapped by `scan-build`.
- Configure it: Use a command that can rebuild the project from `project_root`, for example `cmake --build "build" --clean-first` or `make -C "build" clean all`.

### `clang_analyzer_output_dir`

- Type: `string`
- Required: Yes when `clang_analyzer_enabled` is `true`
- Used for: Output directory where `scan-build` writes its HTML report.
- Configure it: Keep it inside `report_dir`, typically `code_analysis_result/scan-build`.

### `summary_pdf`

- Type: `string`
- Required: Yes
- Used for: Destination path of the consolidated PDF summary generated at the end of the analysis.
- Configure it: Usually keep it in `report_dir`, for example `code_analysis_result/analysis_summary.pdf`.

### `addons_dir`

- Type: `string`
- Required: Yes
- Used for: Directory that stores helper scripts and assets such as `generate_summary_pdf.py`, `clang_tidy_to_html.py`, and the MISRA rules file.
- Configure it: Point it to the repository `codeAnalysisAddons` directory unless you have moved those helper files elsewhere.

### `misra_rules_url`

- Type: `string`
- Required: Yes
- Used for: Download URL for the MISRA guideline headlines file when it is not already present in `addons_dir`.
- Configure it: Leave the default value unless you intentionally host the MISRA file somewhere else.

### `misra_rules_filename`

- Type: `string`
- Required: Yes
- Used for: File name expected inside `addons_dir` for the MISRA guideline headlines used by the `misra.py` addon.
- Configure it: Normally keep the default `misra_rules.txt`.

### `extra_defines`

- Type: `array[string]`
- Required: No
- Used for: Appends extra compiler flags or preprocessor definitions to the temporary compilation database used by the analysis pipeline.
- Configure it: Add entries such as `-D__GNUC__`, `-DMY_FEATURE=1`, or other flags needed so the analyzers see the same preprocessor environment as your build.

### `coverage_enabled`

- Type: `boolean`
- Required: No
- Used for: Enables the coverage preparation and LCOV report generation stages.
- Configure it: Set it to `true` only when you want LCOV output and your project can produce coverage artifacts.

### `coverage_capture_dir`

- Type: `string`
- Required: Yes when `coverage_enabled` is `true`
- Used for: Directory scanned by `lcov --capture` to collect `.gcda` and `.gcno` files.
- Configure it: Point it to the build directory that actually contains coverage artifacts. If you use a dedicated automatic coverage build, set this to the same directory as `coverage_build_dir`.

### `coverage_base_dir`

- Type: `string`
- Required: Recommended when `coverage_enabled` is `true`
- Used for: Passed to `lcov --base-directory` so paths in the report are normalized against the project source tree.
- Configure it: Use `.` when the JSON file lives in the project root, or set it explicitly to the project root path.

### `coverage_info`

- Type: `string`
- Required: Yes when `coverage_enabled` is `true`
- Used for: Output path of the generated LCOV `.info` file.
- Configure it: Keep it inside `report_dir`, for example `code_analysis_result/coverage.info`.

### `coverage_html_dir`

- Type: `string`
- Required: Yes when `coverage_enabled` is `true`
- Used for: Output directory for the HTML coverage site generated by `genhtml`.
- Configure it: Keep it inside `report_dir`, for example `code_analysis_result/coverage-html`.

### `coverage_build_dir`

- Type: `string`
- Required: No
- Used for: Optional dedicated build directory used when the script needs to prepare a separate coverage-enabled build automatically.
- Configure it: Set it when you want coverage to be built in a dedicated tree such as `build/coverage_auto`.

### `coverage_configure_cmd`

- Type: `string`
- Required: No
- Used for: Optional configure command executed before an automatic coverage build.
- Configure it: Leave it empty to let the script generate a default CMake command for CMake projects, or set a custom command for your build system.

### `coverage_build_cmd`

- Type: `string`
- Required: No
- Used for: Optional build command executed during automatic coverage preparation.
- Configure it: Leave it empty to let the script use a default CMake build command, or provide your own command.

### `coverage_run_cmd`

- Type: `string`
- Required: No
- Used for: Optional command used to run tests or binaries that generate coverage data.
- Configure it: For CMake projects, leaving it empty lets the script use `ctest`. For custom projects, set it to the exact command that must be run to produce `.gcda` files.

## Practical recommendations

- Generate the file first and edit it instead of writing it from scratch.
- If the JSON file is stored outside the project root, set `project_root` explicitly.
- Keep `report_dir` and most output files inside the analyzed project so results are easy to find.
- For third-party code, tune both `cppcheck_exclude_dirs` and `clang_tidy_exclude_dirs`.
- If you use a separate coverage build directory, make sure `coverage_capture_dir` points to that same directory.
- Review `clang_analyzer_build_cmd` manually for non-CMake or unusual build systems.
