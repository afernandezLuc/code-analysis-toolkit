#include "platform.h"

const char *platform_name(void)
{
#if defined(_WIN32)
    return "Windows";
#elif defined(__linux__)
    return "Linux";
#elif defined(__APPLE__)
    return "Apple";
#else
    return "Unknown";
#endif
}

int32_t platform_is_little_endian(void)
{
    const uint16_t value = 0x0001U;
    const unsigned char *bytes = (const unsigned char *)&value;

    return (bytes[0] == 0x01U) ? 1 : 0;
}
