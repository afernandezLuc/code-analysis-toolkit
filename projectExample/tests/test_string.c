#include <assert.h>
#include <stddef.h>
#include "string_utils.h"

int main(void)
{
    char buffer[8];
    size_t count = 0U;

    assert(str_copy_safe(buffer, sizeof(buffer), "hello") == 0);
    assert(str_count_char(buffer, 'l', &count) == 0);
    assert(count == 2U);

    assert(str_copy_safe(buffer, sizeof(buffer), "toolongvalue") == 1);

    return 0;
}
