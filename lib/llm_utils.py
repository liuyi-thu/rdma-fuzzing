import json
import os
from datetime import datetime
from typing import List, Optional

import httpx
from openai import OpenAI


def load_config():
    """
    Load base_url and api_key in this order:
    1) Environment variables OPENAI_BASE_URL / OPENAI_API_KEY
    2) Config file: ~/.config/rdma_scaffold/config.ini  (section [openai])
    3) .env in current working directory (if python-dotenv installed)
    Returns (base_url, api_key) or (None, None) if not found.
    """
    base_url = os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY")
    proxy_url = os.environ.get("OPENAI_PROXY_URL", None)

    if base_url and api_key:
        return base_url, api_key, proxy_url

    return None, None, None


def fail_if_no_creds(base_url, api_key):
    if not base_url or not api_key:
        raise RuntimeError(
            "OpenAI base_url/api_key not found. Set environment variables `OPENAI_BASE_URL` and `OPENAI_API_KEY`."
        )


def gen_scaffold(
    example_scaffold: str = "lib/scaffolds/base_connect.py",
    context: str = "",
    class_defs: str = "CLASSES_IN_LIB.md",
    output_dir: str = "lib/scaffolds",
    model: str = "openai/gpt-5",
):
    base_url, api_key, proxy_url = load_config()
    fail_if_no_creds(base_url, api_key)
    client = (
        OpenAI(base_url=base_url, api_key=api_key)
        if proxy_url is None or proxy_url == ""
        else OpenAI(base_url=base_url, api_key=api_key, http_client=httpx.Client(proxy=proxy_url))
    )
    example_scaffold = ""
    with open("lib/scaffolds/base_connect.py", "r", encoding="utf-8") as f:
        example_scaffold = f.read()

    context = """"""

    with open("CLASSES_IN_LIB.md", "r", encoding="utf-8") as f:
        class_defs = f.read()

    user_prompt = f"""
    {context}

    The following are the existing class definitions CLASSES_IN_LIB.md (only these may be used):
    {class_defs}

    ---
    Produce a brand-new Python scaffold plugin file with the following requirements:

    1. Usage constraints
        - Only use the classes defined in my library (see the existing class definitions). Do not define new types or new fields.
        - All verb calls must strictly match the constructor signatures of the existing classes.
        - If connecting/linking is required, call the base_connect() function located in lib.scaffolds.base_connect. Its prototype is:
        def base_connect(pd: str, cq: str, qp: str, port: int, remote_qp: str) -> Tuple[List[VerbCall], List[int]].

    2. Structural requirements
        - The file must contain exactly one scaffold function whose name indicates the scaffold's general semantics and purpose.
        - The scaffold function returns (verbs: List[VerbCall], hotspots: List[int]).
        - Also provide an entry function:
        def build(local_snapshot, global_snapshot, rng) -> Tuple[List[VerbCall], List[int]] | None
        which auto-fills resource names and calls the scaffold.

    3. Prohibitions
        - No I/O, sleep, or threading calls.
        - No undefined Verb classes or custom structs.

    4. Output format
        - Output the complete .py file source code directly (including imports, docstring, etc.). The docstring should include a brief description of the scaffold's semantics and purpose.
        - Add a short comment at the top of the .py file explaining the scaffold's semantics and purpose.
        - The file should be directly placeable into lib/scaffolds/ and loadable via importlib.

    ----
    Here is a Python scaffold plugin file provided as an example:
    {example_scaffold}

    ----

    The Python scaffold plugin file code you should generate is:

    """

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": """
    You are a programming assistant.
    You are helping develop an RDMA verbs fuzzing framework.
    The framework uses a Python + C hybrid architecture where Python is responsible for automatically generating scaffold plugin files (placed under lib/scaffolds/) that implement specific semantic verb sequences based on the RDMA verb wrapper classes defined in CLASSES_IN_LIB.md.

    Your task is to generate a new scaffold plugin file according to the prompt rules provided by the user.
    The file must conform to the constructor signatures of the Verb classes in the library and must be dynamically importable with importlib.

    """,
                    }
                ],
            },
            {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
        ],
        temperature=0.5,
    )

    resp = completion.choices[0].message.content
    # print(resp)

    fname = f"scaffold_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
    with open(os.path.join(output_dir, fname), "w", encoding="utf-8") as f:
        f.write(resp)
    print("Saved to:", fname)

    # # （可选）查看 token 用量
    # print("usage:", completion.usage)  # prompt_tokens / completion_tokens / total_tokens


def gen_scaffold_by_function(
    example_scaffold: str = "lib/scaffolds/base_connect.py",
    context: str = "",
    target_symbol: str = "ibv_create_cq",
    target_space: str = "user",
    # source_function: str = "",
    call_chain: str = "",
    class_defs: str = "CLASSES_IN_LIB.md",
    output_dir: str = "lib/scaffolds",
    model: str = "openai/gpt-5",
):
    base_url, api_key, proxy_url = load_config()
    fail_if_no_creds(base_url, api_key)
    client = (
        OpenAI(base_url=base_url, api_key=api_key)
        if proxy_url is None or proxy_url == ""
        else OpenAI(base_url=base_url, api_key=api_key, http_client=httpx.Client(proxy=proxy_url))
    )
    example_scaffold = ""
    with open("lib/scaffolds/base_connect.py", "r", encoding="utf-8") as f:
        example_scaffold = f.read()

    context = """"""

    with open("CLASSES_IN_LIB.md", "r", encoding="utf-8") as f:
        class_defs = f.read()

    user_prompt = f"""{context}

    你生成的 Python scaffold 插件文件代码为：

    【上下文：未覆盖目标】
    - 目标函数（未覆盖）：{target_symbol}
    - 所在空间：{target_space}   # "kernel" 或 "user"
    - 触达该函数的调用链（由前往后）：{call_chain}

    【只能使用的类定义（务必严格对齐 __init__ 签名，不得自造字段/类型）】
    {class_defs}

    【已有示例 scaffold（风格/导入/结构示例）：】
    {example_scaffold}

    ——— 生成要求 ———
    1) 使用约束
    - 只能使用我库里已有类（见“只能使用的类定义”），**不得**自定义新类型、新字段、新参数。
    - 所有 verbs 调用必须**严格对齐**已有类的构造函数签名。
    - 如需建链，**调用** `base_connect()`。

    1) 结构要求（文件内仅包含一个新 scaffold）
    - 定义一个全新的 scaffold 函数（例如 `srq_path`, `atomic_pair`, `rereg_mr_variants` 等风格的命名，但**不要**与已存在的重名），返回类型必须是：
    `(verbs: List[VerbCall], hotspots: List[int])`
    - 提供入口函数：
    `def build(local_snapshot, global_snapshot, rng) -> Tuple[List[VerbCall], List[int]] | None`
    用于自动补齐资源命名（调用 `gen_name/_pick_unused_from_snap`），若缺关键资源则返回 `None`。
    - **不要**做任何 I/O、sleep、线程或网络调用。
    - 只导入 `lib.*` 命名空间下的模块（与示例一致）。

    1) 目标导向（围绕“未覆盖函数 + 调用链”）
    - 请**优先构造**能沿着给定调用链前段触发的 verbs 序列；如果 class_defs 中存在与链路前端对应的 *Ex* / *cmd* / *icmd* 路径绑定的构造器（例如 `CreateCQEx`、`CreateSRQ`、`CreateSRQEx`、`ReregMR`、`BindMW`、`CreateSRQ`/`PostSRQRecv`/`ModifySRQ` 等），请优先选择 **最贴近**目标链路的调用组合。
    - 如果链路中出现了 “Create*Ex / *cmd / *icmd / uverbs” 的路径，请在用户态这侧选择 **更可能走到对应 ioctl 的构造器**（具体以 class_defs 里可用的构造器为准）。
    - **在 scaffold 顶部 docstring 简述**：该 scaffold 的语义、试图触达的链路关键点（例如 “尝试走 *create_cq_ex* 路径以命中 ib_uverbs_ex_create_cq 的 ioctl 分支”）。

    1) 多样化限定
    - 本次**不要**生成与 CQ 通知相关的内容（例如 `ReqNotifyCQ`、`AckCQEvents`、`PollCQ` 仅在必要校验路径时极简使用；若非必要，请避免）。
    - 如无需 CQ 通知即可触达目标 ioctl/uverbs 路径，请**不**使用通知相关 verbs。
    - 在以下语义区域中择其一，**且应与已存在的 scaffold 不同**：
    - SRQ 路径（`CreateSRQ` / `PostSRQRecv` / `ModifySRQ`）
    - Memory（`RegMR` / `ReregMR` / `BindMW` / `DeallocMW`）
    - Atomic（`IBV_WR_ATOMIC_*`）
    - CQ 相关（**偏向 Create/Resize/Query/Modify，不是通知**）
    - Multi-QP / Shared CQ
    - 错误恢复 / 状态迁移 / Reconnect

    1) 质量约束
    - 返回的 `hotspots` 应包含**最可能命中 ioctl/uverbs 路径**的几个关键 verbs 的索引（如 `Create*` / `Modify*` / `ReregMR` / `BindMW` 等）。
    - 若 class_defs **缺失**触发链路所需的关键构造器，请：
    - 选择**最邻近**的可用变体（例如 `CreateCQ` 替代 `CreateCQEx`）；
    - 在 docstring 中**明确写出**该折衷点；
    - 仍需返回一个可编译可执行的 scaffold；若实在无法构造，则让 `build()` 返回 `None`。

    1) 输出格式
    - 直接输出**完整 .py 文件源代码**，含必要 imports 与 docstring。
    - 文件可直接放入 `lib/scaffolds/` 并由 importlib 加载。
    - 严禁输出除源码以外的任何文字。

    【再次提醒】
    - 所有构造器参数名与类型都要**一字不差**符合 “只能使用的类定义”；
    - 资源名通过 `gen_name/_pick_unused_from_snap` 生成；
    - **目标导向**：使生成的 verbs **沿给定调用链**触发更靠近 `{target_symbol}` 的 ioctl/uverbs 分支。

    你生成的 Python scaffold 插件文件代码为：
"""
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": """
    你是一个编程助手。
    你正在协助一个 RDMA verbs fuzzing 框架的开发。
    该框架使用 Python + C 混合架构，其中 Python 负责根据 CLASSES_IN_LIB.md 中定义的 RDMA verbs 封装类，
    自动生成 scaffold 插件文件（位于 lib/scaffolds/）以实现特定语义的 verbs 序列。

    你的任务是根据用户提供的 prompt 规则生成一个新的 scaffold 插件文件。
    文件必须符合库中 Verb 类的构造签名，且能被 importlib 动态加载。""",
                    }
                ],
            },
            {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
        ],
        temperature=0.2,
    )

    resp = completion.choices[0].message.content
    # print(resp)

    fname = f"scaffold_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
    with open(os.path.join(output_dir, fname), "w", encoding="utf-8") as f:
        f.write(resp)
    # print("Saved to:", fname)

    # # （可选）查看 token 用量
    # print("usage:", completion.usage)  # prompt_tokens / completion_tokens / total_tokens


def mutate_scaffold(
    existing_scaffold_path: str = "lib/scaffolds/base_connect.py",
    context: str = "",
    class_defs: str = "CLASSES_IN_LIB.md",
    output_dir: str = "lib/scaffolds",
    model: str = "openai/gpt-5",
):
    base_url, api_key, proxy_url = load_config()
    fail_if_no_creds(base_url, api_key)
    client = (
        OpenAI(base_url=base_url, api_key=api_key)
        if proxy_url is None or proxy_url == ""
        else OpenAI(base_url=base_url, api_key=api_key, http_client=httpx.Client(proxy=proxy_url))
    )
    existing_scaffold = ""
    with open(existing_scaffold_path, "r", encoding="utf-8") as f:
        existing_scaffold = f.read()

    context = """"""

    with open("CLASSES_IN_LIB.md", "r", encoding="utf-8") as f:
        class_defs = f.read()

    user_prompt = f"""
    {context}

    The following are the existing class definitions CLASSES_IN_LIB.md (only these may be used):
    {class_defs}
    
    You are given an existing Python scaffold plugin file as the **baseline**: {existing_scaffold}
    
    Your job is to **mutate this baseline** to produce a new scaffold for fuzzing.
    Do NOT rewrite from scratch. Apply small-to-moderate, fuzzing-relevant mutations that keep the file structure and API intact while producing a meaningfully different verbs sequence.
    No I/O, sleep, or threading calls. No undefined Verb classes or custom structs.
    
    1. Usage constraints
        - Only use the classes defined in my library (see the existing class definitions). Do not define new types or new fields.
        - All verb calls must strictly match the constructor signatures of the existing classes.
        - If connecting/linking is required, call the base_connect() function located in lib.scaffolds.base_connect. Its prototype is:
        def base_connect(pd: str, cq: str, qp: str, port: int, remote_qp: str) -> Tuple[List[VerbCall], List[int]].

    2. Structural requirements
        - The file must contain exactly one scaffold function whose name indicates the scaffold's general semantics and purpose.
        - The scaffold function returns (verbs: List[VerbCall], hotspots: List[int]).
        - Also provide an entry function:
        def build(local_snapshot, global_snapshot, rng) -> Tuple[List[VerbCall], List[int]] | None
        which auto-fills resource names and calls the scaffold.
    
    3. Allowed mutation strategies for example
    - **Verb sequence mutations**: reorder compatible verbs; insert/remap optional steps; split one step into multiple finer-grained steps; merge adjacent compatible steps.
    - **Parameter mutations**: tweak flags, opcodes, access rights, queue depths, inline thresholds, wr_id patterns; introduce boundary values (min/max/zero/near-limit), off-by-one where valid; vary SGE counts/sizes; adjust polling batches.
    - **Resource reuse patterns**: reuse vs. reallocate PD/CQ/QP/MR within legal constraints; vary QP state transitions timing (still honoring required transitions).
    - **Hotspots tuning**: update indices to reflect new risk/interest points (e.g., before/after modify_qp, around reg/rereg/dereg_mr, at post_send/recv bursts).
    - **Error-path probes (safe)**: choose parameters that are *edge-like but valid*; avoid undefined behavior or class/signature violations.
    - **Determinism via rng**: when branching, derive choices from the provided `rng` so behavior is reproducible under a given seed.


   4. Output format
    - Output a complete `.py` file directly (including imports and a module-level docstring explaining the scaffold’s semantics).
    - At the very top, add a short comment block **"Mutation Summary"** listing the changes and a brief comment explaining the scaffold's semantics and purpose.
    - Mark each changed line/section with `# MUTATION:` comments where appropriate.
    - The file should be directly placeable into `lib/scaffolds/` and loadable via `importlib`.

    ----

    The Python scaffold plugin file code you should generate is:

    """

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": """
    You are a programming assistant for an RDMA verbs fuzzing framework.
    The framework uses a Python + C hybrid architecture where Python auto-generates scaffold plugin files (under lib/scaffolds/) that implement specific semantic verb sequences based on wrapper classes defined in CLASSES_IN_LIB.md.
    Your task: **mutate** an existing scaffold file the user provides to produce a *new* scaffold. This is **not** a rewrite from scratch. Treat the provided file as the baseline and apply targeted fuzzing-oriented mutations while preserving overall file structure, public function signatures, and compatibility.
    The new scaffold file must conform to the constructor signatures of the Verb classes in the library and must be dynamically importable with importlib.

    """,
                    }
                ],
            },
            {"role": "user", "content": [{"type": "text", "text": user_prompt}]},
        ],
        temperature=0.5,
    )

    resp = completion.choices[0].message.content
    # print(resp)

    fname = f"mutated_scaffold_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
    with open(os.path.join(output_dir, fname), "w", encoding="utf-8") as f:
        f.write(resp)
    print("Saved to:", fname)

    # # （可选）查看 token 用量
    # print("usage:", completion.usage)  # prompt_tokens / completion_tokens / total_tokens


def generate_mvs_scaffold(
    *,
    target_symbol: str,
    callchain: List[str],
    entry_verb: str,
    example_scaffold_path: str = "lib/scaffolds/base_connect.py",
    class_defs_path: str = "CLASSES_IN_LIB.md",
    output_dir: str = "lib/scaffolds",
    model: str = "openai/gpt-5",
    # 语义家族提示：影响生成策略与负例约束（避免走偏）
    family_hint: Optional[str] = None,  # 例如: "srq", "atomic", "memory", "multi_qp"
    # 额外的硬约束（例如必须包含哪些Verb或字段；或禁止哪些Verb）
    hard_require_verbs: Optional[List[str]] = None,
    hard_forbid_verbs: Optional[List[str]] = None,
    # 你的项目里已有
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    proxy_url: Optional[str] = None,
    temperature: float = 0.2,
) -> str:
    """
    生成“最小可行（MVS）”的新 scaffold，用于命中指定调用链的用户态入口 verb。
    产出一个 .py 插件文件：仅包含 1 个 scaffold 函数 + 1 个 build() 入口，遵守 CLASSES_IN_LIB.md 中的类签名。
    返回保存的文件路径。
    """

    # 你项目里若有封装可直接替换这段
    def _default_load_config():
        # 占位：如果你已有 load_config/fail_if_no_creds，用它们替换即可
        BU = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        AK = api_key or os.getenv("OPENAI_API_KEY", "")
        PX = proxy_url or os.getenv("HTTPS_PROXY", "") or os.getenv("HTTP_PROXY", "")
        if not AK:
            raise RuntimeError("Missing OpenAI API key")
        return BU, AK, PX

    base_url, api_key, proxy_url = _default_load_config()

    # 读示例 & 类定义
    with open(example_scaffold_path, "r", encoding="utf-8") as f:
        example_scaffold = f.read()
    with open(class_defs_path, "r", encoding="utf-8") as f:
        class_defs = f.read()

    # 语义家族与负例约束（自动增强）
    family_hint = (family_hint or "").strip().lower()
    hard_require_verbs = hard_require_verbs or []
    hard_forbid_verbs = hard_forbid_verbs or []

    # 常见“不要走偏”的负例：根据 family_hint 自动加入
    # 例如 SRQ 家族就避免去做 CQ 通知相关
    # if family_hint in {"srq", "atomic", "memory", "multi_qp"}:
    #     for v in ["ReqNotifyCQ", "AckCQEvents", "PollCQ"]:  # 你明确不想卷入通知/事件
    #         if v not in hard_forbid_verbs:
    #             hard_forbid_verbs.append(v)

    # 形成上下文
    callchain_str = " -> ".join(callchain)
    context = f"""
[Target]
- Uncovered symbol (kernel/user): {target_symbol}
- Callchain (user entry at the left): {callchain_str}
- Required user-space entry verb: {entry_verb}

[Family hint]
- {family_hint or "N/A"}

[Hard constraints]
- REQUIRED verbs (must include): {json.dumps(hard_require_verbs, ensure_ascii=False)}
- FORBIDDEN verbs (must avoid): {json.dumps(hard_forbid_verbs, ensure_ascii=False)}
    """.strip()

    # 组装用户提示词（强约束、清晰结构、强调“新写MVS”而非变异）
    user_prompt = f"""
{context}

以下是已有类定义（仅可使用这些，严格对齐构造签名，不得自定义新类型/字段）：
{class_defs}

—
请“新写一个最小可行（MVS）”的 Python scaffold 插件文件，以命中上述调用链的**用户态入口 verb**：{entry_verb}
要求：

1) 使用约束
- 只能使用我库里已有类（见上面的类定义）；所有 verbs 调用必须严格对齐已有类构造函数签名。
- 若需要建链，请调用 base_connect()（不要复制实现）。
- 禁止使用：{", ".join(hard_forbid_verbs) or "无"}。
- 必须包含（若合理）：{", ".join(hard_require_verbs) or "无"}。

2) 结构要求
- 文件仅包含一个 scaffold 函数（函数名需简短明确，反映该 MVS 语义）。
- scaffold 函数返回: (verbs: List[VerbCall], hotspots: List[int])。
- 另提供一个入口函数：def build(local_snapshot, global_snapshot, rng) -> Tuple[List[VerbCall], List[int]] | None
  自动生成资源名，调用该 scaffold。
- 不得出现任何 I/O、sleep、threading 调用；不得定义新的结构类型。

3) 语义要求
- 围绕 {entry_verb} 的**必要前置资源与状态**，构造最小可行序列（例如 PD/CQ/QP/SRQ/MR 等依赖和绑定）。
- 如果 {entry_verb} 只是控制面/创建类 API，需合理补齐上下文（例如 QP init_attr.srq=... 等），以确保运行路径能触达调用链深处。
- hotspots 理应标注在关键点（如 Create*/Modify*/Post* 这些会触发内核路径的调用处）。

4) 输出格式
- 直接输出完整 .py 文件源代码（含 imports 与模块级 docstring，简述该 MVS 的语义与用途，并说明为什么这个 MVS 可能会触发 uncovered symbol {target_symbol}）。
- 文件能直接放入 lib/scaffolds/ 并通过 importlib 加载。

——
给你一个 scaffold 文件作为风格参考（只能参考结构/风格，不要照搬逻辑；请“新写 MVS”而不是 mutate）：
{example_scaffold}

——
你生成的 Python scaffold 插件文件代码为：
""".strip()

    # OpenAI Client
    http_client = None if not proxy_url else httpx.Client(proxy=proxy_url)
    client = OpenAI(base_url=base_url, api_key=api_key, http_client=http_client)

    completion = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a programming assistant for an RDMA verbs fuzzing framework. "
                    "Generate a brand new, minimal viable scaffold (MVS) targeting the specified user-space entry verb, "
                    "strictly conforming to the provided Verb class signatures. "
                    "No I/O, no threads, no sleeps. Output a single .py module with one scaffold function and a build() entry."
                ),
            },
            {"role": "user", "content": user_prompt},
        ],
    )

    resp = completion.choices[0].message.content or ""
    os.makedirs(output_dir, exist_ok=True)
    fname = f"mvs_{entry_verb}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
    fpath = os.path.join(output_dir, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(resp)
    return fpath
