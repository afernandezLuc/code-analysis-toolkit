# Project Structure Requirements

The project being analyzed does not need to follow one rigid directory layout.

The analyzer does expect a few technical inputs, and some optional features work better when the target project follows common conventions.

## What is strictly required

A project can be analyzed successfully if all of the following are true:

- It is a C project, or at least provides C translation units that appear in `compile_commands.json`.
- A valid `compile_commands.json` exists and points to real source files.
- The paths configured in `codeAnalyzerConfig.json` are correct.
- The project can be built in a way that matches the compilation database.

That means the analyzer does not require fixed folders such as `src/`, `include/`, or `tests/`.
Those are recommended conventions, not mandatory requirements.

## What the tool auto-detects

`generateCodeAnalyzerConfig.sh` tries to find `compile_commands.json` automatically in common build locations such as:

- `build/compile_commands.json`
- `build-*/compile_commands.json`
- `cmake-build*/compile_commands.json`
- `out/compile_commands.json`

If your project stores the compilation database somewhere else, that is still fine, but you may need to set `build_dir` and `compile_db` manually in `codeAnalyzerConfig.json`.

## Recommended project layout

The following layout is recommended because it works well with the defaults and is easier to understand for new users:

```text
my-project/
|-- include/
|-- src/
|-- tests/
|-- build/
|-- CMakeLists.txt
`-- codeAnalyzerConfig.json
```

This is only a recommendation. The analyzer can work with other layouts as long as the configuration is correct.

## CMake is recommended, but not mandatory

CMake-based projects integrate more smoothly because:

- `generateCodeAnalyzerConfig.sh` can try to generate `compile_commands.json` automatically when `CMakeLists.txt` exists.
- Default commands for Clang Static Analyzer and automatic coverage are generated for CMake projects.
- `ctest` can be used automatically for coverage test execution.

If your project does not use CMake, you can still analyze it, but you will usually need to configure more fields manually, especially:

- `compile_db`
- `build_dir`
- `clang_analyzer_build_cmd`
- `coverage_configure_cmd`
- `coverage_build_cmd`
- `coverage_run_cmd`

## Source tree requirements

There is no hardcoded requirement for source files to live under `src/`.
The real requirement is that the files to analyze must appear in `compile_commands.json` and must exist on disk.

So these layouts are all valid if the compilation database is correct:

- `src/*.c`
- `source/**/*.c`
- `app/**/*.c`
- mixed directories across multiple modules

## Header layout requirements

There is no mandatory header layout either.
Headers can live in `include/`, next to source files, or anywhere else used by your build system.

The important part is that your build flags and include paths are already reflected in `compile_commands.json`.

## Build directory expectations

The analyzer does not force the build directory to be named `build`, but many defaults assume a conventional build tree.

Using a standard build directory is recommended because:

- the config generator searches common build folder patterns first
- temporary analysis files are stored under `build_dir`
- default Clang Static Analyzer commands are easier to generate
- default coverage build directories are derived from `build_dir`

If your build output lives elsewhere, set `build_dir` explicitly in `codeAnalyzerConfig.json`.

## Test directory expectations

A `tests/` or `test/` directory is not required for static analysis itself.

It only matters for automatic coverage behavior:

- the config generator enables coverage by default when it sees `tests/` or `test/`
- LCOV post-processing excludes files under `tests/` and `test/`
- automatic CTest execution works best when the project actually defines tests in the coverage build

If your project stores tests somewhere else, the analyzer can still work, but you may want to adjust the coverage settings manually.

## Third-party code conventions

The generator automatically excludes some common external-code directories when they exist:

- `third_party`
- `external`
- `extern`
- `vendor`
- `vendors`

This is only a convenience feature. If your project uses different names, add them manually to:

- `cppcheck_exclude_dirs`
- `clang_tidy_exclude_dirs`

## Where the config file should live

The easiest setup is to store `codeAnalyzerConfig.json` in the project root.

If the file lives somewhere else, the analyzer can still work, but you should usually set:

- `project_root`
- any relative output paths carefully
- any relative build or report paths carefully

This matters because relative paths are resolved against the directory that contains `codeAnalyzerConfig.json`.

## When the project will not work without extra setup

You will probably need manual configuration if one or more of these are true:

- the project does not provide `compile_commands.json`
- the project is not built with CMake
- the build directory uses a nonstandard location
- tests are run through a custom command instead of `ctest`
- coverage artifacts are generated in a different directory than the main build
- the project mixes generated code, vendor code, or unusual folder names that should be excluded

In those cases, the analyzer can still be used, but you will need to customize `codeAnalyzerConfig.json`.

## Practical conclusion

The analyzer does not require a fixed project structure.
What it really requires is a valid build description through `compile_commands.json` and correct paths in `codeAnalyzerConfig.json`.

A conventional structure like this is recommended:

- source code in `src/`
- public headers in `include/`
- tests in `tests/`
- build output in `build/`
- `CMakeLists.txt` in the project root

But it is only a recommended layout, not a hard requirement.
