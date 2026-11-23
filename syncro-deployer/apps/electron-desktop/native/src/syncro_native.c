#include "syncro_native.h"

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32) || defined(__CYGWIN__)
  #define SYNCRO_PLATFORM_NAME "windows"
#elif defined(__APPLE__)
  #define SYNCRO_PLATFORM_NAME "macos"
#else
  #define SYNCRO_PLATFORM_NAME "linux"
#endif

SYNCRO_API const char *syncro_native_version(void) {
    return "0.2.0-syncro-native";
}

SYNCRO_API const char *syncro_native_platform(void) {
    return SYNCRO_PLATFORM_NAME;
}

SYNCRO_API int syncro_native_guardrail_check(const char *arg) {
    if (arg == NULL || arg[0] == '\0') {
        return 1;
    }
    for (size_t i = 0; arg[i] != '\0'; ++i) {
        unsigned char c = (unsigned char)arg[i];
        if (c == ';' || c == '|' || c == '`' || c == '<' || c == '>' ||
            c == '\n' || c == '\r') {
            return 1;
        }
        if (c == '$' && arg[i + 1] == '(') {
            return 1;
        }
        if (c == '&' && arg[i + 1] == '&') {
            return 1;
        }
    }
    return 0;
}

SYNCRO_API uint64_t syncro_native_fnv1a64(const char *data, size_t len) {
    uint64_t hash = 14695981039346656037ULL;
    if (data == NULL) {
        return hash;
    }
    for (size_t i = 0; i < len; ++i) {
        hash ^= (uint64_t)(unsigned char)data[i];
        hash *= 1099511628211ULL;
    }
    return hash;
}
