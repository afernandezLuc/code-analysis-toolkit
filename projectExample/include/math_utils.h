#ifndef MATH_UTILS_H
#define MATH_UTILS_H

#include <stddef.h>
#include <stdint.h>

int32_t math_sum_array(const int32_t *values, size_t length);
int32_t math_max(const int32_t *values, size_t length, int32_t *out_max);
int32_t math_average_rounded(const int32_t *values, size_t length, int32_t *out_average);

#endif
