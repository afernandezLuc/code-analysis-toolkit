# Example C Project

This directory contains a small C project used to validate the static analysis toolkit included in the repository root.

It is intentionally simple, quick to build, and easy to understand. The example is designed to provide:

- a valid `compile_commands.json` workflow
- a small reusable library
- a demo executable
- a couple of unit tests
- a target project for `cppcheck`, `clang-tidy`, `scan-build`, and coverage generation

## Purpose

This example exists to answer two practical questions:

1. Can the analysis pipeline run end to end on a real C project?
2. Does the pipeline produce useful findings and reports?

The project is small enough to use as a smoke test for the analyzer, but structured enough to exercise the main features of the toolchain.

## Project Layout

```text
projectExample/
|-- include/
|   |-- math_utils.h
|   |-- platform.h
|   `-- string_utils.h
|-- src/
|   |-- main.c
|   |-- math_utils.c
|   |-- platform.c
|   `-- string_utils.c
|-- tests/
|   |-- test_math.c
|   `-- test_string.c
|-- CMakeLists.txt
`-- codeAnalyzerConfig.json
```

## Components

### `project_core`

The static library defined by CMake is `project_core`. It groups three small modules:

- `math_utils`: array sum, maximum value, and integer average helpers
- `string_utils`: bounded string copy and character counting helpers
- `platform`: platform name detection and little-endian detection

### `app_demo`

The `app_demo` executable exercises the library functions and also includes intentionally unsafe logic in `src/main.c`.

This is useful because it gives the static analyzers something realistic to report. In particular, the demo contains intentionally problematic code such as:

- an out-of-bounds array access
- a possible null pointer dereference

These deliberate issues help verify that the analysis pipeline is actually catching defects.

### Tests

Two small test executables are built when `BUILD_TESTS=ON`:

- `test_math`
- `test_string`

They use simple `assert`-based checks and are registered with CTest.

## Build Requirements

The example project uses CMake and a C99-compatible compiler.

Typical requirements are:

- `cmake`
- `gcc` or `clang`
- `make` or another CMake-supported generator

## Build the Example

From the repository root:

```bash
cmake -S projectExample -B projectExample/build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DBUILD_TESTS=ON
cmake --build projectExample/build
```

This produces:

- `projectExample/build/app_demo`
- `projectExample/build/test_math`
- `projectExample/build/test_string`
- `projectExample/build/compile_commands.json`

## Run the Tests

```bash
ctest --test-dir projectExample/build --output-on-failure
```

## Run the Demo Application

```bash
./projectExample/build/app_demo
```

Note that `app_demo` contains intentionally unsafe code for analysis purposes, so it is not meant to be treated as production-quality behavior.

## Build With Coverage

If you want to generate coverage data manually:

```bash
cmake -S projectExample -B projectExample/build-coverage \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
  -DBUILD_TESTS=ON \
  -DENABLE_COVERAGE=ON
cmake --build projectExample/build-coverage
ctest --test-dir projectExample/build-coverage --output-on-failure
```

## Use the Example With the Analyzer

From the repository root:

```bash
./generateCodeAnalyzerConfig.sh projectExample
./staticCodeAnalysis.sh projectExample/codeAnalyzerConfig.json
```

The generated reports are written under:

```text
projectExample/code_analysis_result/
```

Typical outputs include:

- `cppcheck.xml`
- `html/index.html`
- `clang_tidy_summary.txt`
- `analysis_summary.pdf`
- `coverage.info` when coverage is enabled
- `scan-build/.../index.html` when Clang Static Analyzer is enabled

## Why This Example Is Useful

This sample project is intentionally small, but it still demonstrates:

- a multi-file C library
- header and source separation
- a normal CMake build
- a generated compilation database
- unit-test integration through CTest
- optional coverage instrumentation
- static-analysis findings from intentionally unsafe demo code

If you want to validate changes to the analyzer before running it on a larger codebase, this is the recommended first target.
