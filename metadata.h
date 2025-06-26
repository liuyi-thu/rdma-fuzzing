#ifndef METADATA_H
#define METADATA_H
#include <stdint.h>
#include <cjson/cJSON.h>
struct metadata_global {
    uint16_t lid;
    uint8_t gid[16];
};

struct metadata_qp {
    uint32_t qpn;
    uintptr_t addr;
    uint32_t rkey;  
};

struct metadata_mr {
    uintptr_t addr;
    uint32_t rkey;
};

struct metadata_pair {
    uint32_t remote_qpn;
    uint32_t local_qpn;
};
#endif // METADATA_H