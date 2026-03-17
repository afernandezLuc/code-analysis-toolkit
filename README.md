# C Static Code Analysis Toolkit

This repository provides a Bash-based static analysis workflow for C projects on Linux/WSL. It combines `cppcheck`, `clang-tidy`, the Clang Static Analyzer, optional LCOV coverage reporting, and a PDF summary generator into a single analysis pipeline.

The toolkit is designed for projects that already have, or can generate, a `compile_commands.json` database. A small sample project is included in `projectExample` so the workflow can be tested end to end.

## Features

- Runs `cppcheck` with XML and HTML output
- Applies the `misra.py` addon together with MISRA guideline headlines
- Runs `clang-tidy` in parallel across the compilation database
- Optionally runs the Clang Static Analyzer through `scan-build`
- Optionally builds and captures LCOV coverage reports
- Generates a consolidated PDF summary report
- Produces a browsable main HTML report with links to additional reports

## Repository Layout

- `staticCodeAnalysis.sh`: main analysis pipeline
- `generateCodeAnalyzerConfig.sh`: generates a JSON configuration for a target project
- `installRequisites.sh`: installs the required Ubuntu/WSL dependencies
- `codeAnalysysAddons/`: helper assets and Python report generators
- `projectExample/`: sample C project used to validate the workflow, documented in `projectExample/README.md`

## Requirements

The scripts target Ubuntu/WSL and expect the following tools to be available:

- `bash`
- `cmake`, `make`, `gcc`, `g++`
- `jq`, `wget`, `curl`, `graphviz`
- `cppcheck`, `cppcheck-htmlreport`
- `clang`, `clang-tidy`, `scan-build`
- `lcov`, `genhtml` for coverage
- `python3`, `python3-venv`, `pip`

You can install the base toolchain with:

```bash
./installRequisites.sh
source .venv/bin/activate
```

## Quick Start With the Example Project

Build the sample project and generate its compilation database:

```bash
cmake -S projectExample -B projectExample/build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DBUILD_TESTS=ON
cmake --build projectExample/build
ctest --test-dir projectExample/build --output-on-failure
```

Generate an analyzer configuration file:

```bash
./generateCodeAnalyzerConfig.sh projectExample
```

Run the full analysis:

```bash
./staticCodeAnalysis.sh projectExample/codeAnalyzerConfig.json
```

## Analyze Your Own Project

1. Make sure your project has a valid `compile_commands.json`.
   If the project uses CMake, `generateCodeAnalyzerConfig.sh` will try to create it automatically in `build/` when possible.
   If it is not a CMake-based project, generate `compile_commands.json` with your own build system before running the analyzer.

2. Generate a configuration file:

```bash
./generateCodeAnalyzerConfig.sh /path/to/your/project
```

You can also choose a custom output path:

```bash
./generateCodeAnalyzerConfig.sh /path/to/your/project /path/to/output/codeAnalyzerConfig.json
```

3. Review and adjust the generated JSON if needed.
   Common fields to tune are:

- `cppcheck_exclude_dirs`
- `clang_tidy_exclude_dirs`
- `cppcheck_suppressions_entries`
- `coverage_*`
- `clang_analyzer_*`

4. Run the analyzer:

```bash
./staticCodeAnalysis.sh /path/to/your/project/codeAnalyzerConfig.json
```

For a full description of every configuration key, see [`docs/codeAnalyzerConfig.md`](docs/codeAnalyzerConfig.md).
For project layout expectations and auto-detected conventions, see [`docs/projectStructureRequirements.md`](docs/projectStructureRequirements.md).

## Generated Output

With the default configuration, results are written to `code_analysis_result/` inside the analyzed project. Typical outputs include:

- `code_analysis_result/cppcheck.xml`
- `code_analysis_result/html/index.html`
- `code_analysis_result/html/clang_tidy.html`
- `code_analysis_result/scan-build/.../index.html` when Clang Static Analyzer is enabled
- `code_analysis_result/coverage.info` when coverage is enabled
- `code_analysis_result/coverage-html/index.html` when coverage is enabled
- `code_analysis_result/analysis_summary.pdf`
- `code_analysis_result/ctest.log` and `code_analysis_result/scan-build.log` when applicable

The main HTML report links to the auxiliary reports when they are available.

## Typical Workflow

```bash
./installRequisites.sh
source .venv/bin/activate

cmake -S /path/to/project -B /path/to/project/build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build /path/to/project/build

./generateCodeAnalyzerConfig.sh /path/to/project
./staticCodeAnalysis.sh /path/to/project/codeAnalyzerConfig.json
```

## Credits and Third-Party Material

This project orchestrates well-known analysis tools such as `cppcheck`, `clang-tidy`, `scan-build`, `lcov`, `genhtml`, Graphviz, and Python-based report generation.

The repository also includes third-party MISRA material:

- `codeAnalysysAddons/misra_rules.txt` contains `MISRA C:2023 Guideline Headlines for CPPcheck`.
- Copyright `(C) 2023 The MISRA Consortium Limited ("MISRA"), all rights reserved`.
- The file header states that it is provided under the `Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International` license:
  `https://creativecommons.org/licenses/by-nc-nd/4.0/`
- The same header states that requests for commercial licensing or derivative works should be directed to `enquiries@misra.org.uk`.
- The MISRA guidelines themselves can be obtained from `https://misra.org.uk/`.

This third-party MISRA file is not released under the MIT License of this repository.

## License

Unless otherwise noted, the source code in this repository is released under the MIT License. See `LICENSE`.
