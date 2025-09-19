# RDMA Fuzzing

## 目前支持的 verbs

- AllocDM
- AllocPD
- CreateCQ
- CreateQP
- CreateSRQ
- DeallocPD
- DeregMR
- DestroyCQ
- DestroyQP
- DestroySRQ
- FreeDM
- ModifyCQ
- ModifyQP
- ModifySRQ
- PollCQ
- PostRecv
- PostSend
- PostSRQRecv
- RegMR

## 用法

### 生成变异代码
`my_fuzz_test.py` 提供了一个示例，基于预定义的 `verbs` 进行变异，并生成 `client.cpp` 代码。`server.cpp`是通用的，无需变异。

### 编译`client`
变异完成后，用以下命令进行编译：

```bash
g++ -O2 -std=c++17 server.cpp pair_runtime.cpp runtime_resolver.c -lcjson -libverbs -o server
g++ -O2 -std=c++17 client.cpp pair_runtime.cpp runtime_resolver.c -lcjson -libverbs -o client
```

用以下命令运行：

```bash
python3 coordinator.py --server-update server_update.json --client-update client_update.json --server-viewserver_view.json --client-view client_view.json

RDMA_FUZZ_RUNTIME=<PATH_TO_THE_PROJECT>/server_view.json ./server
RDMA_FUZZ_RUNTIME=<PATH_TO_THE_PROJECT>/client_view.json ./client
```

也提供了 `all-in-on` 的脚本，直接执行：
```bash
make run
```
或者启动 `ASAN`：
```bash
make SAN=asan run
```
会自动编译并运行，采用 `tmux` 分屏方式呈现结果。如果需要停止运行，可以在另一个终端下执行：
```bash
make tmux-kill
```

## TODO

- 目前 log 中的 stdout 和 stderr 行似乎不是严格按照时间顺序排列的，最好能够解决一下。比如，asan 的 stderr 理论上应该出现在 log 的末尾，因为 asan 触发之后，程序就应该无法运行了
- 增加对 verbs 运行失败（failure）频率的统计
- 将完整的一些流程（单个或者多个 verb，含有参数）打包为 scaffold or template，避免流程总是失败（可复用已有的 contract 系统）
  - 如何获得 scaffold？自己写？或者从已有的程序中提取？manual efforts are needed