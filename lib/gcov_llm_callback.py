import json
import random
from typing import List, Optional


def load_coverage_data(file_path: str) -> dict:
    """
    加载覆盖率数据文件

    Args:
        file_path: JSON文件路径

    Returns:
        dict: 覆盖率数据
    """
    try:
        print(f"[+] 正在加载覆盖率文件: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[+] 覆盖率文件加载成功")
        return data
    except FileNotFoundError:
        print(f"[-] 文件不存在: {file_path}")
        raise
    except json.JSONDecodeError as e:
        print(f"[-] JSON解析错误: {e}")
        raise
    except Exception as e:
        print(f"[-] 加载文件时出错: {e}")
        raise


def load_function_list(file_path: str) -> set:
    """
    从txt文件加载函数名列表

    Args:
        file_path: 函数列表文件路径

    Returns:
        set: 函数名集合
    """
    try:
        print(f"[+] 正在加载函数列表: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            functions = set(line.strip() for line in f if line.strip())
        print(f"[+] 加载了 {len(functions)} 个函数名")
        return functions
    except FileNotFoundError:
        print(f"[-] 文件不存在: {file_path}")
        raise
    except Exception as e:
        print(f"[-] 加载文件时出错: {e}")
        raise


def extract_zero_coverage_functions(coverage_data: dict, target_functions: set) -> List[str]:
    """
    从覆盖率数据中提取execution_count为0的目标函数

    Args:
        coverage_data: 覆盖率JSON数据
        target_functions: 目标函数名集合

    Returns:
        List[str]: execution_count为0的函数名列表
    """
    zero_coverage_funcs = []

    sources = coverage_data.get("sources", {})
    for source_file, source_data in sources.items():
        for _, file_data in source_data.items():
            functions = file_data.get("functions", {})
            for func_name, func_info in functions.items():
                if func_name in target_functions and func_info.get("execution_count", 0) == 0:
                    zero_coverage_funcs.append(func_name)
    return zero_coverage_funcs


def get_all_uncovered_functions(
    space: str = "user",
    user_coverage_path: Optional[str] = None,
    kernel_coverage_path: Optional[str] = None,
    user_list_path: Optional[str] = None,
    kernel_list_path: Optional[str] = None,
) -> Optional[str]:
    """
    从覆盖率数据中随机选择一个未覆盖的函数

    Args:
        space: 空间类型，"user" 或 "kernel"
        user_coverage_path: 用户态覆盖率JSON文件路径，默认为 /home/user_coverage.json
        kernel_coverage_path: 内核态覆盖率JSON文件路径，默认为 /home/kernel_coverage.json
        user_list_path: 用户态函数列表文件路径，默认为 user.txt
        kernel_list_path: 内核态函数列表文件路径，默认为 kernel.txt

    Returns:
        Optional[str]: 随机选择的未覆盖函数名，如果没有则返回None
    """
    if user_coverage_path is None:
        user_coverage_path = "/home/user_coverage.json"
    if kernel_coverage_path is None:
        kernel_coverage_path = "/home/kernel_coverage.json"
    if user_list_path is None:
        user_list_path = "user.txt"
    if kernel_list_path is None:
        kernel_list_path = "kernel.txt"

    try:
        if space.lower() == "user":
            coverage_path = user_coverage_path
            function_list_path = user_list_path
            print(f"[+] 处理用户态函数")
        elif space.lower() == "kernel":
            coverage_path = kernel_coverage_path
            function_list_path = kernel_list_path
            print(f"[+] 处理内核态函数")
        else:
            print(f"[-] 错误: space 参数必须是 'user' 或 'kernel'，当前值为 '{space}'")
            return None

        coverage_data = load_coverage_data(coverage_path)

        target_functions = load_function_list(function_list_path)

        print(f"[+] 正在查找execution_count为0的函数...")
        zero_coverage_funcs = extract_zero_coverage_functions(coverage_data, target_functions)

        if not zero_coverage_funcs:
            print(f"[-] 没有找到execution_count为0的目标函数")
            return None

        zero_coverage_funcs = list(set(zero_coverage_funcs))
        print(f"[+] 共找到 {len(zero_coverage_funcs)} 个未覆盖的函数")

        # selected_func = random.choice(zero_coverage_funcs)
        # print(f"[+] 随机选择函数: {selected_func}")

        return zero_coverage_funcs

    except Exception as e:
        print(f"[-] 处理过程中出错: {e}")
        return None


def get_random_uncovered_function(
    space: str = "user",
    user_coverage_path: Optional[str] = None,
    kernel_coverage_path: Optional[str] = None,
    user_list_path: Optional[str] = None,
    kernel_list_path: Optional[str] = None,
) -> Optional[str]:
    """
    从覆盖率数据中随机选择一个未覆盖的函数

    Args:
        space: 空间类型，"user" 或 "kernel"
        user_coverage_path: 用户态覆盖率JSON文件路径，默认为 /home/user_coverage.json
        kernel_coverage_path: 内核态覆盖率JSON文件路径，默认为 /home/kernel_coverage.json
        user_list_path: 用户态函数列表文件路径，默认为 user.txt
        kernel_list_path: 内核态函数列表文件路径，默认为 kernel.txt

    Returns:
        Optional[str]: 随机选择的未覆盖函数名，如果没有则返回None
    """
    if user_coverage_path is None:
        user_coverage_path = "/home/user_coverage.json"
    if kernel_coverage_path is None:
        kernel_coverage_path = "/home/kernel_coverage.json"
    if user_list_path is None:
        user_list_path = "user.txt"
    if kernel_list_path is None:
        kernel_list_path = "kernel.txt"

    try:
        if space.lower() == "user":
            coverage_path = user_coverage_path
            function_list_path = user_list_path
            print(f"[+] 处理用户态函数")
        elif space.lower() == "kernel":
            coverage_path = kernel_coverage_path
            function_list_path = kernel_list_path
            print(f"[+] 处理内核态函数")
        else:
            print(f"[-] 错误: space 参数必须是 'user' 或 'kernel'，当前值为 '{space}'")
            return None

        coverage_data = load_coverage_data(coverage_path)

        target_functions = load_function_list(function_list_path)

        print(f"[+] 正在查找execution_count为0的函数...")
        zero_coverage_funcs = extract_zero_coverage_functions(coverage_data, target_functions)

        if not zero_coverage_funcs:
            print(f"[-] 没有找到execution_count为0的目标函数")
            return None

        zero_coverage_funcs = list(set(zero_coverage_funcs))
        print(f"[+] 共找到 {len(zero_coverage_funcs)} 个未覆盖的函数")

        selected_func = random.choice(zero_coverage_funcs)
        print(f"[+] 随机选择函数: {selected_func}")

        return selected_func

    except Exception as e:
        print(f"[-] 处理过程中出错: {e}")
        return None


def get_all_uncovered_functions(
    space: str = "user",
    user_coverage_path: Optional[str] = None,
    kernel_coverage_path: Optional[str] = None,
    user_list_path: Optional[str] = None,
    kernel_list_path: Optional[str] = None,
) -> List[str]:
    """
    获取所有未覆盖的函数列表

    Args:
        space: 空间类型，"user" 或 "kernel"
        user_coverage_path: 用户态覆盖率JSON文件路径，默认为 /home/user_coverage.json
        kernel_coverage_path: 内核态覆盖率JSON文件路径，默认为 /home/kernel_coverage.json
        user_list_path: 用户态函数列表文件路径，默认为 user.txt
        kernel_list_path: 内核态函数列表文件路径，默认为 kernel.txt

    Returns:
        List[str]: 所有未覆盖函数名列表
    """
    if user_coverage_path is None:
        user_coverage_path = "/home/user_coverage.json"
    if kernel_coverage_path is None:
        kernel_coverage_path = "/home/kernel_coverage.json"
    if user_list_path is None:
        user_list_path = "user.txt"
    if kernel_list_path is None:
        kernel_list_path = "kernel.txt"

    try:
        if space.lower() == "user":
            coverage_path = user_coverage_path
            function_list_path = user_list_path
        elif space.lower() == "kernel":
            coverage_path = kernel_coverage_path
            function_list_path = kernel_list_path
        else:
            print(f"[-] 错误: space 参数必须是 'user' 或 'kernel'")
            return []

        coverage_data = load_coverage_data(coverage_path)
        target_functions = load_function_list(function_list_path)

        zero_coverage_funcs = extract_zero_coverage_functions(coverage_data, target_functions)

        return sorted(list(set(zero_coverage_funcs)))

    except Exception as e:
        print(f"[-] 处理过程中出错: {e}")
        return []


def get_uncovered_function_count(
    space: str = "user",
    user_coverage_path: Optional[str] = None,
    kernel_coverage_path: Optional[str] = None,
    user_list_path: Optional[str] = None,
    kernel_list_path: Optional[str] = None,
) -> int:
    """
    获取未覆盖函数的数量

    Args:
        space: 空间类型，"user" 或 "kernel"
        user_coverage_path: 用户态覆盖率JSON文件路径，默认为 /home/user_coverage.json
        kernel_coverage_path: 内核态覆盖率JSON文件路径，默认为 /home/kernel_coverage.json
        user_list_path: 用户态函数列表文件路径，默认为 user.txt
        kernel_list_path: 内核态函数列表文件路径，默认为 kernel.txt

    Returns:
        int: 未覆盖函数的数量
    """
    if user_coverage_path is None:
        user_coverage_path = "/home/user_coverage.json"
    if kernel_coverage_path is None:
        kernel_coverage_path = "/home/kernel_coverage.json"
    if user_list_path is None:
        user_list_path = "user.txt"
    if kernel_list_path is None:
        kernel_list_path = "kernel.txt"

    try:
        if space.lower() == "user":
            coverage_path = user_coverage_path
            function_list_path = user_list_path
            print(f"[+] 统计用户态未覆盖函数")
        elif space.lower() == "kernel":
            coverage_path = kernel_coverage_path
            function_list_path = kernel_list_path
            print(f"[+] 统计内核态未覆盖函数")
        else:
            print(f"[-] 错误: space 参数必须是 'user' 或 'kernel'，当前值为 '{space}'")
            return 0

        coverage_data = load_coverage_data(coverage_path)
        target_functions = load_function_list(function_list_path)

        print(f"[+] 正在统计execution_count为0的函数...")
        zero_coverage_funcs = extract_zero_coverage_functions(coverage_data, target_functions)

        # 去重
        unique_zero_coverage_funcs = list(set(zero_coverage_funcs))
        count = len(unique_zero_coverage_funcs)

        total_target_count = len(target_functions)
        coverage_rate = ((total_target_count - count) / total_target_count * 100) if total_target_count > 0 else 0

        print(f"[+] 目标函数总数: {total_target_count}")
        print(f"[+] 未覆盖函数数量: {count}")
        print(f"[+] 覆盖率: {coverage_rate:.2f}%")

        return count

    except Exception as e:
        print(f"[-] 统计过程中出错: {e}")
        return 0


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("[+] 测试内核态未覆盖函数查找 (使用自定义路径)")
    print("=" * 60)
    kernel_func = get_random_uncovered_function(
        space="kernel",
        user_coverage_path="user_coverage.json",
        kernel_coverage_path="kernel_coverage.json",
        user_list_path="user.txt",
        kernel_list_path="kernel.txt",
    )
    if kernel_func:
        print(f"\n[+] 随机选择的内核态未覆盖函数: {kernel_func}")

    print("\n" + "=" * 60)
