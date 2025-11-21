# rdma_exec/Makefile
#
# 基础版：
#   make            # 编译 rdma_exec
#   make run        # 用样例 JSON 和 rxe0 设备跑一下
#   make clean      # 清理

# 编译器和基本选项
CC      ?= gcc
CFLAGS  ?= -Wall -Wextra -O2 -g
# CFLAGS  ?= -Wall -Wextra -O2 -g -fsanitize=address
LDFLAGS ?=
LIBS    ?= -libverbs -lcjson

# 源文件和目标文件
SRCS = \
    rdma_executor.c \
    verb_dispatch.c \
    verb_pd.c \
    verb_dm.c \
    verb_qp.c \
    verb_mw.c \
    verb_mr.c \
    verb_td.c \
    verb_srq.c \
    verb_cq.c \
    verb_flow.c \
    server_conn.c \
    json_utils.c \
    resource_env.c

OBJS = $(SRCS:.c=.o)

# 生成的可执行文件名
TARGET = rdma_exec

# 默认目标
all: $(TARGET)

# 连接
$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) $(LIBS)

# 通用 .c -> .o 规则
%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

# 运行示例：
#  - JSON_PATH 可覆写： make run JSON=xxx.json
#  - DEV_NAME 可覆写：  make run DEV=mlx5_0
JSON ?= program.json
DEV  ?= rxe0

run: $(TARGET)
	./$(TARGET) $(JSON) $(DEV)

# 清理
clean:
	rm -f $(OBJS) $(TARGET)

.PHONY: all run clean