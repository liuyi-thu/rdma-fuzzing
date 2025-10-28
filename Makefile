# ====== Config ======
CXX       := g++
CC        := gcc
CXXFLAGS  := -O2 -std=c++17 -MMD -MP
CFLAGS    := -O2 -std=c11  -MMD -MP
LDFLAGS   :=
LDLIBS    := -lcjson -libverbs

BUILD_DIR := build
BIN_DIR   := $(BUILD_DIR)
BIN_SERVER:= $(BIN_DIR)/server
BIN_CLIENT:= $(BIN_DIR)/client

# 视图/更新文件放在当前目录（与代码中的路径一致）
SERVER_UPDATE := $(BUILD_DIR)/server_update.json
CLIENT_UPDATE := $(BUILD_DIR)/client_update.json
SERVER_VIEW   := server_view.json
CLIENT_VIEW   := client_view.json

# ---- Sanitizer Switches ----
# 用法： make SAN=asan        # 开启 AddressSanitizer 构建到 build/asan
SAN ?=
ASAN_OPTIONS ?= halt_on_error=1,detect_leaks=1,detect_stack_use_after_return=1,allocator_may_return_null=1,fast_unwind_on_malloc=0
LSAN_OPTIONS ?= report_objects=1

# 根据 SAN 改写构建目录，避免和非SAN产物混淆
# JSON文件始终保持在当前目录
ifneq ($(SAN),)
BUILD_DIR := build/$(SAN)
BIN_DIR   := $(BUILD_DIR)
BIN_SERVER:= $(BIN_DIR)/server
BIN_CLIENT:= $(BIN_DIR)/client

SERVER_UPDATE := $(BUILD_DIR)/server_update.json
CLIENT_UPDATE := $(BUILD_DIR)/client_update.json
SERVER_VIEW   := server_view.json
CLIENT_VIEW   := client_view.json
endif

# 运行命令前缀：把工作目录切到 BIN_DIR 再执行
RUN_PREFIX := cd $(BIN_DIR) &&

# 默认运行命令（coordinator在项目根目录，server/client在BIN_DIR下运行）
COORD_CMD := python3 coordinator.py --server-update $(SERVER_UPDATE) --client-update $(CLIENT_UPDATE) --server-view $(SERVER_VIEW) --client-view $(CLIENT_VIEW)
SERVER_CMD := $(RUN_PREFIX) RDMA_FUZZ_RUNTIME=$(abspath $(SERVER_VIEW)) ./server
CLIENT_CMD := $(RUN_PREFIX) RDMA_FUZZ_RUNTIME=$(abspath $(CLIENT_VIEW)) ./client

# 注入 ASan 编译/链接参数 + 覆盖运行命令（仍在 BIN_DIR 下运行）
ifeq ($(SAN),asan)
CXXFLAGS += -fsanitize=address -fno-omit-frame-pointer -g -O1
CFLAGS   += -fsanitize=address -fno-omit-frame-pointer -g -O1
LDFLAGS  += -fsanitize=address
SERVER_CMD := $(RUN_PREFIX) env ASAN_OPTIONS=$(ASAN_OPTIONS) LSAN_OPTIONS=$(LSAN_OPTIONS) RDMA_FUZZ_RUNTIME=$(abspath $(SERVER_VIEW)) ./server
CLIENT_CMD := $(RUN_PREFIX) env ASAN_OPTIONS=$(ASAN_OPTIONS) LSAN_OPTIONS=$(LSAN_OPTIONS) RDMA_FUZZ_RUNTIME=$(abspath $(CLIENT_VIEW)) ./client
endif

# ====== Sources & Objects ======
SRCS_CPP  := server.cpp client.cpp pair_runtime.cpp
SRCS_C    := runtime_resolver.c

OBJS_CPP  := $(patsubst %.cpp,$(BUILD_DIR)/%.o,$(SRCS_CPP))
OBJS_C    := $(patsubst %.c,$(BUILD_DIR)/%.o,$(SRCS_C))
DEPS      := $(OBJS_CPP:.o=.d) $(OBJS_C:.o=.d)

# ====== Phony targets ======
.PHONY: all clean distclean run tmux-run tmux-kill prepare jsons

all: $(BIN_SERVER) $(BIN_CLIENT)

# ====== Build rules ======
$(BUILD_DIR):
	@mkdir -p $(BUILD_DIR)

# C++
$(BUILD_DIR)/%.o: %.cpp | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -c $< -o $@

# C
$(BUILD_DIR)/%.o: %.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

# Link server/client
$(BIN_SERVER): $(BUILD_DIR)/server.o $(BUILD_DIR)/pair_runtime.o $(BUILD_DIR)/runtime_resolver.o | $(BUILD_DIR)
	$(CXX) $(LDFLAGS) $^ $(LDLIBS) -o $@

$(BIN_CLIENT): $(BUILD_DIR)/client.o $(BUILD_DIR)/pair_runtime.o $(BUILD_DIR)/runtime_resolver.o | $(BUILD_DIR)
	$(CXX) $(LDFLAGS) $^ $(LDLIBS) -o $@

# ====== JSON files (ensure they exist in current directory) ======
jsons: $(SERVER_UPDATE) $(CLIENT_UPDATE) $(SERVER_VIEW) $(CLIENT_VIEW)

$(SERVER_UPDATE) $(CLIENT_UPDATE) $(SERVER_VIEW) $(CLIENT_VIEW):
	@touch $@

# ====== Run (tmux split panes) ======
TMUX_SESSION := rdma-fuzz

run: all prepare tmux-run

prepare: jsons
	@echo "Prepared view/update JSONs in current directory"

tmux-run:
	@command -v tmux >/dev/null 2>&1 || { echo "Error: 未安装 tmux。使用 NO_TMUX=1 切换为后台运行模式：make run NO_TMUX=1"; exit 1; }
	@echo "Starting tmux session '$(TMUX_SESSION)' ..."
	# 1) 启动空会话与第一个 pane（左侧），再发送 coordinator 命令（在项目根运行）
	@tmux new-session -d -s $(TMUX_SESSION)
	@tmux send-keys  -t $(TMUX_SESSION):0 '$(COORD_CMD)' C-m

	@sleep 1

	# 2) 右侧 pane 运行 server（在 BIN_DIR 下执行）
	@tmux split-window -h -t $(TMUX_SESSION):0
	@tmux send-keys   -t $(TMUX_SESSION):0.1 '$(SERVER_CMD)' C-m

	@sleep 1  # 等待 server 启动
	
	# 3) 右下 pane 运行 client（在 BIN_DIR 下执行）
	@tmux select-pane  -t $(TMUX_SESSION):0.1
	@tmux split-window -v -t $(TMUX_SESSION):0.1
	@tmux send-keys    -t $(TMUX_SESSION):0.2 '$(CLIENT_CMD)' C-m

	# 4) 美化布局
	@tmux select-layout -t $(TMUX_SESSION) tiled
	@tmux set-option -t $(TMUX_SESSION) mouse on >/dev/null 2>&1 || true
	@tmux attach -t $(TMUX_SESSION)

tmux-kill:
	-@tmux kill-session -t $(TMUX_SESSION) 2>/dev/null || true

kill: tmux-kill

# ====== Cleaning ======
clean:
	@$(RM) $(OBJS_CPP) $(OBJS_C) $(DEPS) $(BIN_SERVER) $(BIN_CLIENT)

distclean: clean
	@$(RM) -r $(BUILD_DIR)

# 自动依赖
-include $(DEPS)
