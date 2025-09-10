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

# 视图/更新文件统一放在 build/ 下（更干净）
SERVER_UPDATE := $(BUILD_DIR)/server_update.json
CLIENT_UPDATE := $(BUILD_DIR)/client_update.json
SERVER_VIEW   := $(BUILD_DIR)/server_view.json
CLIENT_VIEW   := $(BUILD_DIR)/client_view.json

# 运行命令
COORD_CMD := python3 coordinator.py --server-update $(SERVER_UPDATE) --client-update $(CLIENT_UPDATE) --server-view $(SERVER_VIEW) --client-view $(CLIENT_VIEW)
SERVER_CMD := RDMA_FUZZ_RUNTIME=$(abspath $(SERVER_VIEW)) $(BIN_SERVER)
CLIENT_CMD := RDMA_FUZZ_RUNTIME=$(abspath $(CLIENT_VIEW)) $(BIN_CLIENT)

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

# ====== JSON files (ensure they exist) ======
jsons: $(SERVER_UPDATE) $(CLIENT_UPDATE) $(SERVER_VIEW) $(CLIENT_VIEW)

$(SERVER_UPDATE) $(CLIENT_UPDATE) $(SERVER_VIEW) $(CLIENT_VIEW): | $(BUILD_DIR)
	@touch $@

# ====== Run (tmux split panes) ======
# 说明：
# make run       -> 构建 + 启动 tmux 会话（横竖分三窗格：coordinator / server / client）
# make tmux-kill -> 结束该 tmux 会话
TMUX_SESSION := rdma-fuzz

run: all prepare tmux-run

prepare: jsons
	@echo "Prepared view/update JSONs in $(BUILD_DIR)/"

# tmux-run:
# 	@command -v tmux >/dev/null 2>&1 || { echo "Error: tmux 未安装。请先安装 tmux 或自行手动运行三条命令。"; exit 1; }
# 	@echo "Starting tmux session '$(TMUX_SESSION)' ..."
# 	@tmux new-session -d -s $(TMUX_SESSION) '$(COORD_CMD)'
# 	@tmux split-window -h -t $(TMUX_SESSION) '$(SERVER_CMD)'
# 	@tmux split-window -v -t $(TMUX_SESSION):0.1 '$(CLIENT_CMD)'
# 	@tmux select-layout -t $(TMUX_SESSION) tiled
# 	@tmux set-option -t $(TMUX_SESSION) mouse on >/dev/null 2>&1 || true
# 	@tmux attach -t $(TMUX_SESSION)

tmux-run:
	@command -v tmux >/dev/null 2>&1 || { echo "Error: 未安装 tmux。使用 NO_TMUX=1 切换为后台运行模式：make run NO_TMUX=1"; exit 1; }
	@echo "Starting tmux session '$(TMUX_SESSION)' ..."
	# 1) 启动空会话与第一个 pane（左侧），再发送 coordinator 命令
	@tmux new-session -d -s $(TMUX_SESSION)
	@tmux send-keys  -t $(TMUX_SESSION):0 '$(COORD_CMD)' C-m

	# 2) 水平切一刀得到右侧 pane，并在右侧启动 server
	@tmux split-window -h -t $(TMUX_SESSION):0
	@tmux send-keys   -t $(TMUX_SESSION):0.1 '$(SERVER_CMD)' C-m

	# 3) 选中右侧 pane，再垂直切一刀得到右上/右下，在右下启动 client
	@tmux select-pane  -t $(TMUX_SESSION):0.1
	@tmux split-window -v -t $(TMUX_SESSION):0.1
	@tmux send-keys    -t $(TMUX_SESSION):0.2 '$(CLIENT_CMD)' C-m

	# 4) 美化布局 & 可选日志
	@tmux select-layout -t $(TMUX_SESSION) tiled
	@tmux set-option -t $(TMUX_SESSION) mouse on >/dev/null 2>&1 || true
ifeq ($(LOG),1)
	@$(MAKE) logs-dir >/dev/null
	@tmux pipe-pane  -t $(TMUX_SESSION):0.0 -o "cat > $(LOG_DIR)/coordinator.log"
	@tmux pipe-pane  -t $(TMUX_SESSION):0.1 -o "cat > $(LOG_DIR)/server.log"
	@tmux pipe-pane  -t $(TMUX_SESSION):0.2 -o "cat > $(LOG_DIR)/client.log"
	@echo "日志: $(LOG_DIR)/coordinator.log  $(LOG_DIR)/server.log  $(LOG_DIR)/client.log"
endif
	@tmux attach -t $(TMUX_SESSION)


tmux-kill:
	-@tmux kill-session -t $(TMUX_SESSION) 2>/dev/null || true

# ====== Cleaning ======
clean:
	@$(RM) $(OBJS_CPP) $(OBJS_C) $(DEPS) $(BIN_SERVER) $(BIN_CLIENT)

distclean: clean
	@$(RM) -r $(BUILD_DIR)

# 自动依赖
-include $(DEPS)
