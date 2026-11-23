#ifndef SYNCRO_NATIVE_H
#define SYNCRO_NATIVE_H

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32) || defined(__CYGWIN__)
  #define SYNCRO_API __declspec(dllexport)
#else
  #define SYNCRO_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* Returns semantic version string of the Syncro native shared library. */
SYNCRO_API const char *syncro_native_version(void);

/* Returns compile-time target platform identifier ("linux", "windows", "macos"). */
SYNCRO_API const char *syncro_native_platform(void);

/* Fast C-level shell-metacharacter guardrail check. Returns 0 if safe, 1 if unsafe. */
SYNCRO_API int syncro_native_guardrail_check(const char *arg);

/* Deterministic 64-bit FNV-1a fingerprint for deployment idempotency & audit hashes. */
SYNCRO_API uint64_t syncro_native_fnv1a64(const char *data, size_t len);

#ifdef __cplusplus
}
#endif

#endif /* SYNCRO_NATIVE_H */
