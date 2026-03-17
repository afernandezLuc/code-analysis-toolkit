#include "string_utils.h"

int32_t str_copy_safe(char *destination, size_t destination_size, const char *source)
{
    size_t index = 0U;

    if ((destination == (char *)0) || (source == (const char *)0) || (destination_size == 0U))
    {
        return -1;
    }

    while ((source[index] != '\0') && ((index + 1U) < destination_size))
    {
        destination[index] = source[index];
        ++index;
    }

    destination[index] = '\0';

    if (source[index] != '\0')
    {
        return 1;
    }

    return 0;
}

int32_t str_count_char(const char *text, char target, size_t *out_count)
{
    size_t count = 0U;
    size_t index = 0U;

    if ((text == (const char *)0) || (out_count == (size_t *)0))
    {
        return -1;
    }

    while (text[index] != '\0')
    {
        if (text[index] == target)
        {
            ++count;
        }
        ++index;
    }

    *out_count = count;
    return 0;
}
