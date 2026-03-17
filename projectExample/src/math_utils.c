#include "math_utils.h"

int32_t math_sum_array(const int32_t *values, size_t length)
{
    size_t index;
    int32_t sum = 0;

    if ((values == (const int32_t *)0) || (length == 0U))
    {
        return 0;
    }

    for (index = 0U; index < length; ++index)
    {
        sum += values[index];
    }

    return sum;
}

int32_t math_max(const int32_t *values, size_t length, int32_t *out_max)
{
    size_t index;
    int32_t current_max;

    if ((values == (const int32_t *)0) || (out_max == (int32_t *)0) || (length == 0U))
    {
        return -1;
    }

    current_max = values[0];

    for (index = 1U; index < length; ++index)
    {
        if (values[index] > current_max)
        {
            current_max = values[index];
        }
    }

    *out_max = current_max;
    return 0;
}

int32_t math_average_rounded(const int32_t *values, size_t length, int32_t *out_average)
{
    int32_t sum;

    if ((values == (const int32_t *)0) || (out_average == (int32_t *)0) || (length == 0U))
    {
        return -1;
    }

    sum = math_sum_array(values, length);
    *out_average = sum / (int32_t)length;
    return 0;
}
