#include <assert.h>
#include <stdint.h>
#include "math_utils.h"

int main(void)
{
    const int32_t values[] = {1, 2, 3, 4};
    int32_t max_value = 0;
    int32_t average = 0;

    assert(math_sum_array(values, 4U) == 10);
    assert(math_max(values, 4U, &max_value) == 0);
    assert(max_value == 4);
    assert(math_average_rounded(values, 4U, &average) == 0);
    assert(average == 2);

    return 0;
}
