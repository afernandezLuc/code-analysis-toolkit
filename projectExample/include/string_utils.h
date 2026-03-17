#ifndef STRING_UTILS_H
#define STRING_UTILS_H

#include <stddef.h>
#include <stdint.h>

int32_t str_copy_safe(char *destination, size_t destination_size, const char *source);
int32_t str_count_char(const char *text, char target, size_t *out_count);

#endif
