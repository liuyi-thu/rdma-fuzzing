# 硬编码路径完整分析报告

> **生成时间:** 2025-10-24  
> **分析工具:** AI Assistant (Claude Sonnet 4.5)  
> **分析范围:** 全项目所有 Python 源文件及配置文件

---

## 📋 目录

1. [概述](#概述)
2. [关键硬编码路径](#关键硬编码路径)
3. [项目相对路径](#项目相对路径)
4. [配置文件路径](#配置文件路径)
5. [统计汇总](#统计汇总)
6. [优化建议](#优化建议)
7. [实施方案](#实施方案)

---

## 🎯 概述

本报告分析了 RDMA Fuzzing 项目中所有硬编码的文件路径，按照影响程度分为三个等级：

- 🔴 **关键路径** - 必须配置化，影响核心功能
- 🟡 **次要路径** - 建议优化，影响可移植性
- 🟢 **良好路径** - 设计合理，无需修改

---

## 🔴 关键硬编码路径

### 1. 用户态覆盖率收集 - `lib/runexec.py`

#### 1.1 覆盖率输出文件

```python
文件: lib/runexec.py
行号: 25, 30-36
路径: /home/lbz/user_coverage.json
```

**代码片段:**
```python
# 第25行
utils.run_cmd("rm -f /home/lbz/user_coverage.json")

# 第30-34行
if utils.retry_until_file_exist("/home/lbz/user_coverage.json"):
    print("[+] User coverage generated successfully")
else:
    print("[-] /home/lbz/user_coverage.json not found, retrying...")

# 第36行
if os.path.exists("/home/lbz/user_coverage.json"):
    all_edges = collect_all_edges("/home/lbz/user_coverage.json", None)
```

**影响分析:**
- 🔴 **严重性:** 高 - 覆盖率收集功能完全依赖此路径
- 🔴 **可移植性:** 差 - 绝对路径，不同用户需修改代码
- 🔴 **优先级:** 最高 - 必须改为可配置

---

#### 1.2 RDMA Core 编译输出目录

```python
文件: lib/runexec.py
行号: 27
路径: /home/lbz/rdma-core/build/
```

**代码片段:**
```python
user_cmd = "python3 /home/lbz/fastcov-master/fastcov.py -f /home/lbz/rdma-core/build/librdmacm/CMakeFiles/rspreload.dir/*.gcda /home/lbz/rdma-core/build/libibverbs/CMakeFiles/ibverbs.dir/*.gcda /home/lbz/rdma-core/build/librdmacm/CMakeFiles/rdmacm.dir/*.gcda -e /home/lbz/rdma-core/build/include -o /home/lbz/user_coverage.json -X"
```

**涉及的具体路径:**
```
/home/lbz/rdma-core/build/librdmacm/CMakeFiles/rspreload.dir/*.gcda
/home/lbz/rdma-core/build/libibverbs/CMakeFiles/ibverbs.dir/*.gcda
/home/lbz/rdma-core/build/librdmacm/CMakeFiles/rdmacm.dir/*.gcda
/home/lbz/rdma-core/build/include
```

**影响分析:**
- 🔴 **严重性:** 高 - gcov 数据源路径
- 🔴 **可移植性:** 差 - 每个用户的 rdma-core 位置不同
- 🔴 **优先级:** 最高 - 必须改为可配置

---

#### 1.3 Fastcov 工具路径

```python
文件: lib/runexec.py
行号: 27
路径: /home/lbz/fastcov-master/fastcov.py
```

**代码片段:**
```python
user_cmd = "python3 /home/lbz/fastcov-master/fastcov.py -f ..."
```

**影响分析:**
- 🔴 **严重性:** 高 - 覆盖率收集工具
- 🔴 **可移植性:** 差 - 工具位置因环境而异
- 🔴 **优先级:** 最高 - 建议加入 PATH 或配置化

---

### 2. 覆盖率默认路径 - `lib/gcov_llm_callback.py`

```python
文件: lib/gcov_llm_callback.py
行号: 108, 174, 226
路径: /home/lbz/user_coverage.json, /home/kernel_coverage.json
```

**代码片段:**
```python
def get_random_uncovered_function(...):
    if user_coverage_path is None:
        user_coverage_path = "/home/lbz/user_coverage.json"
    if kernel_coverage_path is None:
        kernel_coverage_path = "/home/kernel_coverage.json"  # 已废弃
```

**影响分析:**
- 🟡 **严重性:** 中 - 有参数可覆盖，但默认值硬编码
- 🟡 **可移植性:** 中 - 可通过参数传递自定义路径
- 🟡 **优先级:** 中 - 建议改为相对路径或读取环境变量

**同样的模式出现在:**
- `get_all_uncovered_functions()` - 第174行
- `get_uncovered_function_count()` - 第226行

---

### 3. 临时文件路径 - `fuzz_test.py`

```python
文件: fuzz_test.py
行号: 260, 266
路径: /tmp/
```

**代码片段:**
```python
# 第260行
with open(f"/tmp/{seed}_{_round}.cpp", "w") as f:
    f.write(render(verbs))

# 第266行
compile_cmd = f"g++ -g -O0 -std=c++11 -o /tmp/{seed}_{_round} /tmp/{seed}_{_round}.cpp {cwd}/pair_runtime.cpp {cwd}/runtime_resolver.c -I {cwd} -lcjson -libverbs -lpthread"
```

**影响分析:**
- 🟡 **严重性:** 中 - 仅用于测试编译
- 🔴 **可移植性:** 差 - Windows 不支持 `/tmp/`
- 🟡 **优先级:** 中 - 建议使用 `tempfile.gettempdir()`

---

### 4. LLM 工具硬编码路径 - `lib/llm_utils.py`

```python
文件: lib/llm_utils.py
行号: 34-37, 48, 53
路径: lib/scaffolds/base_connect.py, CLASSES_IN_LIB.md
```

**代码片段:**
```python
def gen_scaffold(
    example_scaffold: str = "lib/scaffolds/base_connect.py",  # 参数默认值
    context: str = "",
    class_defs: str = "CLASSES_IN_LIB.md",                     # 参数默认值
    output_dir: str = "lib/scaffolds",
    ...
):
    # 但函数内部忽略参数，直接硬编码！
    with open("lib/scaffolds/base_connect.py", "r", encoding="utf-8") as f:  # 第48行
        example_scaffold = f.read()
    
    with open("CLASSES_IN_LIB.md", "r", encoding="utf-8") as f:  # 第53行
        class_defs = f.read()
```

**影响分析:**
- 🟡 **严重性:** 中 - 定义了参数但未使用
- 🟡 **可移植性:** 中 - 相对路径，但应该使用参数
- 🟡 **优先级:** 中 - 代码逻辑问题，应使用参数值

---

## 🟢 项目相对路径（设计良好）

这些路径使用相对路径，设计合理，无需修改：

### 1. 构建输出目录 - `lib/auto_run.py`

```python
文件: lib/auto_run.py
行号: 23-24
```

**代码片段:**
```python
CWD = Path.cwd()
SERVER_BIN = str(CWD / "build" / "asan" / "server")
CLIENT_BIN = str(CWD / "build" / "asan" / "client")
```

✅ **评价:** 良好 - 相对于项目根目录，灵活且可移植

---

### 2. 数据存储目录 - `lib/auto_run.py`

```python
文件: lib/auto_run.py
行号: 29-30
```

**代码片段:**
```python
REPO_DIR = Path("./repo")
REPO_DIR.mkdir(parents=True, exist_ok=True)
CACHE_BIN = REPO_DIR / "client_cached"
```

✅ **评价:** 良好 - 自动创建，相对路径

---

### 3. 日志和输出文件 - `lib/auto_run.py`

```python
文件: lib/auto_run.py
行号: 91-95
```

**代码片段:**
```python
self.stdout_path = REPO_DIR / f"{index}_client.stdout.log"
self.stderr_path = REPO_DIR / f"{index}_client.stderr.log"
self.tmp_stdout_path = REPO_DIR / f"client.tmp.stdout.log"
self.tmp_stderr_path = REPO_DIR / f"client.tmp.stderr.log"
self.src_path = REPO_DIR / f"{index}_client.cpp"
```

✅ **评价:** 良好 - 统一管理在 repo 目录下

---

### 4. 模板目录 - `my_fuzz_test.py`, `gen_code_from_scaffold.py`

```python
文件: my_fuzz_test.py
行号: 211-212
```

**代码片段:**
```python
template_dir = "./templates"
template_name = "client.cpp.j2"
env = Environment(loader=FileSystemLoader(template_dir), ...)
```

✅ **评价:** 良好 - 项目标准目录结构

---

### 5. Coordinator 配置文件 - `lib/auto_run.py`

```python
文件: lib/auto_run.py
行号: 18-21
```

**代码片段:**
```python
COORDINATOR_CMD = [
    "python3",
    str(CWD / "coordinator.py"),
    "--server-update", str(CWD / "server_update.json"),
    "--client-update", str(CWD / "client_update.json"),
    "--server-view", str(CWD / "server_view.json"),
    "--client-view", str(CWD / "client_view.json"),
]
```

✅ **评价:** 良好 - 基于工作目录，符合预期

---

### 6. 生成的源文件 - `my_fuzz_test.py`

```python
文件: my_fuzz_test.py
行号: 337-338
```

**代码片段:**
```python
with open("client.cpp", "w") as f:
    f.write(rendered)
```

✅ **评价:** 良好 - 符合工作流，在当前目录生成

---

## 📂 配置文件路径

### 1. 数据库文件

```python
文件: lib/corpus.py
行号: 30
```

**代码片段:**
```python
DB_NAME = "corpus.db"
```

✅ **评价:** 良好 - 相对路径，在指定目录创建

---

```python
文件: lib/sqlite3_llm_callback.py
行号: 6
```

**代码片段:**
```python
def get_connection(db_path: str = "callchain.db") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
```

✅ **评价:** 良好 - 默认值可覆盖

---

### 2. 函数列表文件

```python
文件: lib/gcov_llm_callback.py
行号: 111-114, 177-180, 229-232
```

**代码片段:**
```python
if user_list_path is None:
    user_list_path = "user.txt"
if kernel_list_path is None:
    kernel_list_path = "kernel.txt"
```

✅ **评价:** 良好 - 相对路径，可通过参数覆盖

---

## 📊 统计汇总

### 按路径类型分类

| 路径类型 | 数量 | 风险等级 | 示例 |
|---------|------|---------|------|
| 绝对路径 (/home/) | 6 | 🔴 高 | `/home/lbz/rdma-core/build/` |
| 系统路径 (/tmp/) | 2 | 🟡 中 | `/tmp/{seed}_{round}.cpp` |
| 项目相对路径 (./) | 12 | 🟢 低 | `./repo/`, `./templates/` |
| 当前目录文件 | 5 | 🟢 低 | `client.cpp`, `corpus.db` |
| **总计** | **25** | - | - |

---

### 按文件分类

| 文件 | 硬编码路径数 | 关键路径数 | 优先级 |
|------|------------|-----------|--------|
| `lib/runexec.py` | 6 | 6 | 🔴 最高 |
| `lib/gcov_llm_callback.py` | 6 | 0 | 🟡 中 |
| `lib/auto_run.py` | 8 | 0 | 🟢 低 |
| `fuzz_test.py` | 2 | 2 | 🟡 中 |
| `my_fuzz_test.py` | 3 | 0 | 🟢 低 |
| `lib/llm_utils.py` | 3 | 2 | 🟡 中 |
| 其他文件 | 5 | 0 | 🟢 低 |

---

### 按影响程度分类

| 影响程度 | 路径数 | 需处理 | 说明 |
|---------|--------|--------|------|
| 🔴 关键 - 核心功能 | 6 | ✅ 必须 | 覆盖率收集相关 |
| 🟡 重要 - 可移植性 | 7 | ⚠️ 建议 | 临时文件、LLM工具 |
| 🟢 正常 - 设计良好 | 12 | ❌ 无需 | 项目相对路径 |

---

## 🔧 优化建议

### 高优先级（必须处理）

#### 建议 1: 覆盖率收集路径配置化

**问题文件:** `lib/runexec.py`

**当前代码:**
```python
utils.run_cmd("rm -f /home/lbz/user_coverage.json")
user_cmd = "python3 /home/lbz/fastcov-master/fastcov.py -f /home/lbz/rdma-core/build/..."
```

**推荐方案 A - 环境变量:**
```python
import os

# 读取环境变量（带默认值）
RDMA_CORE_BUILD = os.getenv("RDMA_CORE_BUILD_DIR", "/home/lbz/rdma-core/build")
FASTCOV_PATH = os.getenv("FASTCOV_PATH", "/home/lbz/fastcov-master/fastcov.py")
USER_COVERAGE_JSON = os.getenv("USER_COVERAGE_JSON", "/home/lbz/user_coverage.json")

# 使用配置
utils.run_cmd(f"rm -f {USER_COVERAGE_JSON}")

user_cmd = (
    f"python3 {FASTCOV_PATH} "
    f"-f {RDMA_CORE_BUILD}/librdmacm/CMakeFiles/rspreload.dir/*.gcda "
    f"{RDMA_CORE_BUILD}/libibverbs/CMakeFiles/ibverbs.dir/*.gcda "
    f"{RDMA_CORE_BUILD}/librdmacm/CMakeFiles/rdmacm.dir/*.gcda "
    f"-e {RDMA_CORE_BUILD}/include "
    f"-o {USER_COVERAGE_JSON} -X"
)
```

**推荐方案 B - 配置文件:**

创建 `config.py`:
```python
from pathlib import Path
import os

# 项目根目录
PROJECT_ROOT = Path(__file__).parent

# 从环境变量读取，否则使用默认值
class Config:
    # 外部工具路径
    RDMA_CORE_BUILD_DIR = Path(os.getenv(
        "RDMA_CORE_BUILD_DIR", 
        "/home/lbz/rdma-core/build"
    ))
    FASTCOV_PATH = Path(os.getenv(
        "FASTCOV_PATH",
        "/home/lbz/fastcov-master/fastcov.py"
    ))
    
    # 覆盖率文件
    USER_COVERAGE_JSON = Path(os.getenv(
        "USER_COVERAGE_JSON",
        "/home/lbz/user_coverage.json"
    ))
    
    # 项目目录
    REPO_DIR = PROJECT_ROOT / "repo"
    TEMP_DIR = PROJECT_ROOT / "temp"
```

在 `lib/runexec.py` 中使用:
```python
from config import Config

utils.run_cmd(f"rm -f {Config.USER_COVERAGE_JSON}")

user_cmd = (
    f"python3 {Config.FASTCOV_PATH} "
    f"-f {Config.RDMA_CORE_BUILD_DIR}/librdmacm/CMakeFiles/rspreload.dir/*.gcda "
    # ...
)
```

---

### 中优先级（建议处理）

#### 建议 2: 临时文件路径跨平台化

**问题文件:** `fuzz_test.py`

**当前代码:**
```python
with open(f"/tmp/{seed}_{_round}.cpp", "w") as f:
    f.write(render(verbs))
```

**推荐方案:**
```python
import tempfile
from pathlib import Path

# 方案1: 使用系统临时目录
temp_dir = Path(tempfile.gettempdir())
cpp_file = temp_dir / f"{seed}_{_round}.cpp"
with open(cpp_file, "w") as f:
    f.write(render(verbs))

# 方案2: 使用项目临时目录（推荐）
temp_dir = Path("./temp")
temp_dir.mkdir(exist_ok=True)
cpp_file = temp_dir / f"{seed}_{_round}.cpp"
with open(cpp_file, "w") as f:
    f.write(render(verbs))
```

---

#### 建议 3: LLM 工具使用参数值

**问题文件:** `lib/llm_utils.py`

**当前代码:**
```python
def gen_scaffold(
    example_scaffold: str = "lib/scaffolds/base_connect.py",
    class_defs: str = "CLASSES_IN_LIB.md",
    ...
):
    # 忽略参数，直接硬编码
    with open("lib/scaffolds/base_connect.py", "r") as f:
        example_scaffold = f.read()
    
    with open("CLASSES_IN_LIB.md", "r") as f:
        class_defs = f.read()
```

**推荐方案:**
```python
def gen_scaffold(
    example_scaffold: str = "lib/scaffolds/base_connect.py",
    class_defs: str = "CLASSES_IN_LIB.md",
    ...
):
    # 使用参数值！
    with open(example_scaffold, "r", encoding="utf-8") as f:
        example_content = f.read()
    
    with open(class_defs, "r", encoding="utf-8") as f:
        class_defs_content = f.read()
```

---

#### 建议 4: 覆盖率默认路径改为相对路径

**问题文件:** `lib/gcov_llm_callback.py`

**当前代码:**
```python
if user_coverage_path is None:
    user_coverage_path = "/home/lbz/user_coverage.json"
```

**推荐方案:**
```python
import os

if user_coverage_path is None:
    # 方案1: 环境变量
    user_coverage_path = os.getenv("USER_COVERAGE_JSON", "./user_coverage.json")
    
    # 方案2: 项目目录
    # user_coverage_path = "./repo/user_coverage.json"
```

---

## 💡 实施方案

### 方案 A: 环境变量配置（推荐用于开发）

#### 步骤 1: 创建 `.env.example` 模板

```bash
# RDMA Fuzzing 配置文件
# 复制此文件为 .env 并根据您的环境修改

# ========== 外部依赖路径 ==========
# RDMA Core 编译输出目录
RDMA_CORE_BUILD_DIR=/home/your-username/rdma-core-master/build

# Fastcov 工具路径（或确保在 PATH 中）
FASTCOV_PATH=/home/your-username/fastcov/fastcov.py

# ========== 覆盖率文件 ==========
# 用户态覆盖率输出文件
USER_COVERAGE_JSON=/home/your-username/user_coverage.json

# 内核覆盖率文件（已废弃，可选）
KERNEL_COVERAGE_JSON=/home/your-username/kernel_coverage.json

# ========== LLM 配置 ==========
# OpenAI API 配置（用于测试生成增强）
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-your-key-here
OPENAI_PROXY_URL=

# ========== 项目配置 ==========
# 临时文件目录（默认使用 ./temp）
TEMP_DIR=./temp

# 日志输出目录（默认使用 ./repo）
REPO_DIR=./repo
```

#### 步骤 2: 修改代码读取环境变量

在需要的文件头部添加：
```python
import os
from pathlib import Path

# 读取配置
RDMA_CORE_BUILD = os.getenv("RDMA_CORE_BUILD_DIR", "/home/lbz/rdma-core/build")
FASTCOV_PATH = os.getenv("FASTCOV_PATH", "/home/lbz/fastcov-master/fastcov.py")
USER_COVERAGE_JSON = os.getenv("USER_COVERAGE_JSON", "/home/lbz/user_coverage.json")
```

#### 步骤 3: （可选）使用 python-dotenv

```bash
pip install python-dotenv
```

```python
from dotenv import load_dotenv
load_dotenv()  # 自动加载 .env 文件

# 现在可以直接使用 os.getenv()
```

---

### 方案 B: 统一配置文件（推荐用于生产）

#### 创建 `config.py`

```python
"""
RDMA Fuzzing 项目配置
优先级: 环境变量 > 默认值
"""

from pathlib import Path
import os

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.absolute()

class PathConfig:
    """路径配置管理"""
    
    # ========== 外部工具 ==========
    RDMA_CORE_BUILD_DIR = Path(os.getenv(
        "RDMA_CORE_BUILD_DIR",
        "/home/lbz/rdma-core/build"
    ))
    
    FASTCOV_PATH = Path(os.getenv(
        "FASTCOV_PATH",
        "/home/lbz/fastcov-master/fastcov.py"
    ))
    
    # ========== 覆盖率文件 ==========
    USER_COVERAGE_JSON = Path(os.getenv(
        "USER_COVERAGE_JSON",
        "/home/lbz/user_coverage.json"
    ))
    
    # ========== 项目目录 ==========
    REPO_DIR = PROJECT_ROOT / "repo"
    BUILD_DIR = PROJECT_ROOT / "build"
    TEMPLATES_DIR = PROJECT_ROOT / "templates"
    SCAFFOLDS_DIR = PROJECT_ROOT / "lib" / "scaffolds"
    
    # 临时目录
    TEMP_DIR = Path(os.getenv("TEMP_DIR", str(PROJECT_ROOT / "temp")))
    
    # ========== 数据库 ==========
    CORPUS_DB = REPO_DIR / "corpus.db"
    CALLCHAIN_DB = PROJECT_ROOT / "callchain.db"
    
    # ========== 数据文件 ==========
    USER_FUNCTIONS = PROJECT_ROOT / "user.txt"
    KERNEL_FUNCTIONS = PROJECT_ROOT / "kernel.txt"
    CLASS_DEFS_MD = PROJECT_ROOT / "CLASSES_IN_LIB.md"
    
    @classmethod
    def ensure_dirs(cls):
        """确保必要的目录存在"""
        cls.REPO_DIR.mkdir(exist_ok=True)
        cls.TEMP_DIR.mkdir(exist_ok=True)
        cls.SCAFFOLDS_DIR.mkdir(parents=True, exist_ok=True)


# 初始化时创建必要目录
PathConfig.ensure_dirs()


class BuildConfig:
    """构建配置"""
    SAN = "asan"  # 或 "tsan", "ubsan"
    SERVER_BIN = PathConfig.BUILD_DIR / BuildConfig.SAN / "server"
    CLIENT_BIN = PathConfig.BUILD_DIR / BuildConfig.SAN / "client"


# 导出便捷引用
PATHS = PathConfig
BUILD = BuildConfig
```

#### 在代码中使用

```python
# lib/runexec.py
from config import PATHS

utils.run_cmd(f"rm -f {PATHS.USER_COVERAGE_JSON}")

user_cmd = (
    f"python3 {PATHS.FASTCOV_PATH} "
    f"-f {PATHS.RDMA_CORE_BUILD_DIR}/librdmacm/CMakeFiles/rspreload.dir/*.gcda "
    f"-o {PATHS.USER_COVERAGE_JSON} -X"
)
```

```python
# lib/auto_run.py
from config import PATHS, BUILD

SERVER_BIN = str(BUILD.SERVER_BIN)
CLIENT_BIN = str(BUILD.CLIENT_BIN)
REPO_DIR = PATHS.REPO_DIR
```

```python
# lib/llm_utils.py
from config import PATHS

def gen_scaffold(...):
    with open(PATHS.SCAFFOLDS_DIR / "base_connect.py", "r") as f:
        example_scaffold = f.read()
    
    with open(PATHS.CLASS_DEFS_MD, "r") as f:
        class_defs = f.read()
```

---

### 方案 C: YAML 配置文件（可选）

#### 创建 `config.yaml`

```yaml
# RDMA Fuzzing 配置

paths:
  # 外部工具
  rdma_core_build: /home/your-username/rdma-core-master/build
  fastcov: /home/your-username/fastcov/fastcov.py
  
  # 覆盖率文件
  user_coverage: /home/your-username/user_coverage.json
  kernel_coverage: /home/your-username/kernel_coverage.json
  
  # 项目目录
  repo: ./repo
  templates: ./templates
  scaffolds: ./lib/scaffolds
  temp: ./temp
  
  # 数据库
  corpus_db: ./repo/corpus.db
  callchain_db: ./callchain.db

build:
  sanitizer: asan  # asan, tsan, ubsan
  
llm:
  base_url: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}  # 从环境变量读取
  proxy_url: ""
```

#### 加载配置

```python
import yaml
from pathlib import Path

def load_config(config_path="config.yaml"):
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    # 展开环境变量
    import os
    for key, value in config.get("llm", {}).items():
        if isinstance(value, str) and value.startswith("${"):
            env_var = value[2:-1]  # 去除 ${ }
            config["llm"][key] = os.getenv(env_var)
    
    return config

CONFIG = load_config()
```

---

## 📈 实施优先级建议

### 第一阶段（立即执行）- 关键路径

1. ✅ 修改 `lib/runexec.py` - 覆盖率收集路径
   - 预计时间: 30分钟
   - 影响: 高
   - 风险: 低

### 第二阶段（近期执行）- 重要优化

2. ✅ 修改 `fuzz_test.py` - 临时文件路径
   - 预计时间: 15分钟
   - 影响: 中
   - 风险: 低

3. ✅ 修改 `lib/llm_utils.py` - 使用参数值
   - 预计时间: 10分钟
   - 影响: 中
   - 风险: 极低

4. ✅ 修改 `lib/gcov_llm_callback.py` - 默认路径
   - 预计时间: 15分钟
   - 影响: 中
   - 风险: 低

### 第三阶段（可选）- 长期改进

5. ⭐ 创建统一配置系统 (`config.py`)
   - 预计时间: 2小时
   - 影响: 高
   - 风险: 中

6. ⭐ 编写配置文档和迁移指南
   - 预计时间: 1小时
   - 影响: 中
   - 风险: 无

---

## ✅ 验收标准

修改完成后，项目应该满足：

1. ✅ **无绝对路径硬编码** - 所有外部依赖路径可配置
2. ✅ **跨平台兼容** - Windows/Linux/macOS 都能运行
3. ✅ **环境隔离** - 不同用户/环境互不干扰
4. ✅ **配置清晰** - 有明确的配置文档和示例
5. ✅ **向后兼容** - 提供默认值，不影响现有用户

---

## 📚 附录

### 完整路径清单

#### 绝对路径（需修改）
```
/home/lbz/rdma-core/build/librdmacm/CMakeFiles/rspreload.dir/*.gcda
/home/lbz/rdma-core/build/libibverbs/CMakeFiles/ibverbs.dir/*.gcda
/home/lbz/rdma-core/build/librdmacm/CMakeFiles/rdmacm.dir/*.gcda
/home/lbz/rdma-core/build/include
/home/lbz/fastcov-master/fastcov.py
/home/lbz/user_coverage.json
/home/kernel_coverage.json (废弃)
/tmp/{seed}_{round}.cpp
/tmp/{seed}_{round}
```

#### 相对路径（保持不变）
```
./repo/
./build/asan/server
./build/asan/client
./templates/
./lib/scaffolds/
client.cpp
server.cpp
coordinator.py
server_update.json
client_update.json
server_view.json
client_view.json
corpus.db
callchain.db
user.txt
kernel.txt
CLASSES_IN_LIB.md
```

---

## 🎯 总结

### 当前状态
- 📊 总计 25 个硬编码路径
- 🔴 6 个关键路径需要立即配置化
- 🟡 7 个路径建议优化
- 🟢 12 个路径设计良好

### 推荐方案
1. **短期:** 使用环境变量方案（快速、简单）
2. **长期:** 建立统一配置系统（规范、可维护）

### 预期收益
- ✅ 提升可移植性
- ✅ 简化部署流程
- ✅ 降低维护成本
- ✅ 改善用户体验

---

**报告完成！** 🎉

如有问题或需要更详细的实施指导，请随时咨询。

