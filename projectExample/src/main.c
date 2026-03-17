#include <stdio.h>
#include <stdint.h>
#include "math_utils.h"
#include "string_utils.h"
#include "platform.h"

static void demo_buggy_logic(int trigger)
{
    int values[2] = {10, 20};
    int *ptr = 0;

    /* Acceso fuera de rango */
    printf("Out of bounds value: %d\n", values[5]);

    /* Posible null dereference */
    if (trigger != 0)
    {
        ptr = &values[0];
    }

    printf("Pointer value: %d\n", *ptr);
}

int main(void)
{
    const int32_t values[] = {4, 8, 15, 16, 23, 42};
    int32_t max_value = 0;
    int32_t average = 0;
    char buffer[8];
    size_t underscore_count = 0U;

    (void)str_copy_safe(buffer, sizeof(buffer), "code_analyzer_template");
    (void)str_count_char(buffer, '_', &underscore_count);
    (void)math_max(values, (sizeof(values) / sizeof(values[0])), &max_value);
    (void)math_average_rounded(values, (sizeof(values) / sizeof(values[0])), &average);

    demo_buggy_logic(0);

    (void)printf("Platform: %s\n", platform_name());
    (void)printf("Little endian: %d\n", platform_is_little_endian());
    (void)printf("Max value: %d\n", max_value);
    (void)printf("Average: %d\n", average);
    (void)printf("Buffer: %s\n", buffer);
    (void)printf("Underscore count: %zu\n", underscore_count);

    return 0;
}