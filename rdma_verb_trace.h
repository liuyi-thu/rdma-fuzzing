
#ifndef RDMA_VERB_TRACE_H
#define RDMA_VERB_TRACE_H

#include <stdio.h>
#include <time.h>

#define VERB_TRACE_LOGFILE "/tmp/rdma_verb_trace.log"

static inline void _verb_log(const char *func_name) {
    FILE *f = fopen(VERB_TRACE_LOGFILE, "a");
    if (f) {
        time_t t = time(NULL);
        struct tm *tm_info = localtime(&t);
        char buf[32];
        strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S", tm_info);
        fprintf(f, "[%s] %s\n", buf, func_name);
        fclose(f);
    }
}

#define LOG_VERB_CALL(func, ...) do { \
    FILE *f = fopen("rdma_trace.log", "a"); \
    fprintf(f, "[%s] " #func "(%s) → %p\n", __FUNCTION__, #__VA_ARGS__, (void*)func(__VA_ARGS__)); \
    fclose(f); \
} while(0)

#define TRACE_VERB(name) do { _verb_log(name); } while (0)

#endif
