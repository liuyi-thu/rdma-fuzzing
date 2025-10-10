import os
from datetime import datetime

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

    user_prompt = f"""{context}

    以下是已有类定义（仅可使用这些）：
    {class_defs}

    ---
    请产出一个全新的 Python scaffold 插件文件，要求：
    1. 使用约束
        - 只能使用我库里已有类（见已有类定义），不得自定义新类型、新字段。
        - 所有 verbs 调用必须严格对齐已有类的构造函数签名。
        - 若需要建链，请调用 base_connect()。

    2. 结构要求
        - 文件仅包含一个 scaffold 函数（例如 atomic_pair、resize_cq_flow、rereg_mr_variants 等）。
        - scaffold 函数返回 (verbs: List[VerbCall], hotspots: List[int])。
        - 另需提供一个入口函数：def build(local_snapshot, global_snapshot, rng) -> Tuple[List[VerbCall], List[int]] | None，自动填补资源名并调用 scaffold。
    3. 不得出现
        - 任何 I/O、sleep、threading 调用。
        - 未定义的 Verb 类或自定义结构体。

    4. 关键补充（用于多样化生成）
        - 请不要生成与 CQ 通知、PollCQ、AckCQEvents、ReqNotifyCQ 相关的 scaffold。
        - 请优先选择不同语义区域之一：
        - SRQ 路径（CreateSRQ / PostSRQRecv / ModifySRQ）
        - Memory 相关（RegMR, ReregMR, BindMW, DeallocMW）
        - Atomic 操作（FetchAdd, CompareSwap）
        - CQ Resize/Query/Modify
        - Multi-QP / Shared CQ 场景
        - 错误恢复 / 状态迁移 / Reconnect
        - 若不确定，任选一种但必须与之前提供的 scaffold（如 base_connect、notify_cq_basic、qp_retry_tuning）语义不同。

    5. 输出格式
        - 直接输出完整 .py 文件源代码（包含 imports、docstring 等）。
        - 在 .py 文件开头添加简要注释，说明该 scaffold 的语义和用途。
        - 文件应能直接放入 lib/scaffolds/ 并通过 importlib 加载。

    ⸻
    给你一个 Python scaffold 插件文件作为示例：
    {example_scaffold}

    ⸻

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
