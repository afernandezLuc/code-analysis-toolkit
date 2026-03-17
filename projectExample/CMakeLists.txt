cmake_minimum_required(VERSION 3.16)
project(code_analyzer_template VERSION 1.0.0 LANGUAGES C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(ENABLE_WARNINGS "Enable strict compiler warnings" ON)
option(ENABLE_COVERAGE "Enable coverage instrumentation" OFF)
option(BUILD_TESTS "Build unit tests" ON)

if(ENABLE_WARNINGS)
    if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        add_compile_options(-Wall -Wextra -Wpedantic -Wshadow -Wconversion)
    endif()
endif()

if(ENABLE_COVERAGE)
    if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        add_compile_options(--coverage -O0 -g)
        add_link_options(--coverage)
    endif()
endif()

include_directories(${PROJECT_SOURCE_DIR}/include)

add_library(project_core
    src/math_utils.c
    src/string_utils.c
    src/platform.c
)

target_include_directories(project_core PUBLIC ${PROJECT_SOURCE_DIR}/include)

add_executable(app_demo src/main.c)
target_link_libraries(app_demo PRIVATE project_core)

if(BUILD_TESTS)
    enable_testing()

    add_executable(test_math tests/test_math.c)
    target_link_libraries(test_math PRIVATE project_core)
    add_test(NAME test_math COMMAND test_math)

    add_executable(test_string tests/test_string.c)
    target_link_libraries(test_string PRIVATE project_core)
    add_test(NAME test_string COMMAND test_string)
endif()
