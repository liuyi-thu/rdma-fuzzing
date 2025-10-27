import random
import sqlite3
from typing import List, Literal, Optional, Tuple


def get_connection(db_path: str = "callchain.db") -> sqlite3.Connection:
    """
    与数据库建立连接并返回连接对象

    Args:
        db_path: 数据库文件路径，默认为 "rdma.db"

    Returns:
        sqlite3.Connection: 数据库连接对象
    """
    try:
        print(f"[+] 正在连接数据库: {db_path}")
        conn = sqlite3.connect(db_path)
        print(f"[+] 数据库连接成功")
        return conn
    except sqlite3.Error as e:
        print(f"[-] 数据库连接错误: {e}")
        raise


def get_call_chain(function_name: str, space: str) -> Optional[Tuple[str, str]]:
    """
    根据函数名和空间类型查询对应的 source_function 和 call_chain

    Args:
        function_name: 要查询的函数名
        space: 空间类型，"user" 查询 ibv 表，"kernel" 查询 uverbs 表

    Returns:
        Optional[Tuple[str, str]]: (source_function, call_chain) 或 None（未找到）
    """
    if space.lower() == "user":
        table_name = "ibv"
    elif space.lower() == "kernel":
        table_name = "uverbs"
    else:
        print(f"[-] 错误: space 参数必须是 'user' 或 'kernel'，当前值为 '{space}'")
        return None

    print(f"[+] 查询函数: {function_name}, 空间: {space}, 表: {table_name}")

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        query = f"""
        SELECT source_function, call_chain, depth
        FROM {table_name}
        WHERE function = ?
        ORDER BY depth DESC
        """

        cursor.execute(query, (function_name,))
        results = cursor.fetchall()

        if not results:
            print(f"[-] 未找到函数 '{function_name}' 在 {table_name} 表中的记录")
            return None

        print(f"[+] 找到 {len(results)} 条记录")

        max_depth = results[0][2]
        max_depth_results = [r for r in results if r[2] == max_depth]

        print(f"[+] 最大 depth: {max_depth}, 符合条件的记录数: {len(max_depth_results)}")

        selected = random.choice(max_depth_results)

        print(f"[+] 已选择记录: source_function={selected[0]}")

        return (selected[0], selected[1])

    except sqlite3.Error as e:
        print(f"[-] 数据库查询错误: {e}")
        return None
    finally:
        if conn:
            conn.close()
            print(f"[+] 数据库连接已关闭")


def get_call_chains(
    function_name: str,
    space: str,
    mode: Literal["max_depth_only", "all"] = "max_depth_only",
    min_depth: Optional[int] = None,
    distinct_source: bool = False,
) -> List[Tuple[str, str, int]]:
    """
    查询满足条件的所有 (source_function, call_chain, depth) 记录。

    Args:
        function_name: 目标函数名（匹配列 function）
        space: "user" -> 表 ibv；"kernel" -> 表 uverbs
        mode:
            - "max_depth_only": 只返回该 function 下 depth 为最大值的记录（默认）
            - "all": 返回该 function 的所有记录，按 depth DESC 排序
        min_depth: 可选的最小 depth 过滤（包含该值）
        distinct_source: 若为 True，则对 source_function 去重（同一 source 只保留一条，优先更大 depth）

    Returns:
        List[Tuple[source_function, call_chain, depth]]
    """
    if space.lower() == "user":
        table_name = "ibv"
    elif space.lower() == "kernel":
        table_name = "uverbs"
    else:
        print(f"[-] 错误: space 参数必须是 'user' 或 'kernel'，当前值为 '{space}'")
        return None

    if not table_name:
        return []

    print(
        f"[+] 查询函数(批量): {function_name}, 空间: {space}, 表: {table_name}, mode={mode}, min_depth={min_depth}, distinct_source={distinct_source}"
    )

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        params: List[object] = [function_name]

        if mode == "max_depth_only":
            # 仅返回最大 depth 的记录；把 min_depth（若给定）并入子查询约束
            sub_params: List[object] = [function_name]
            where_min = ""
            if min_depth is not None:
                where_min = " AND depth >= ?"
                sub_params.append(min_depth)

            sql = f"""
            SELECT source_function, call_chain, depth
            FROM {table_name}
            WHERE function = ?
              AND depth = (
                    SELECT MAX(depth) FROM {table_name}
                    WHERE function = ? {where_min}
              )
            """
            params = [function_name] + sub_params

        elif mode == "all":
            # 返回所有记录，支持最小 depth 过滤
            sql = f"""
            SELECT source_function, call_chain, depth
            FROM {table_name}
            WHERE function = ?
            """
            if min_depth is not None:
                sql += " AND depth >= ?"
                params.append(min_depth)
            sql += " ORDER BY depth DESC"
        else:
            raise ValueError(f"未知的 mode: {mode}")

        cursor.execute(sql, tuple(params))
        rows: List[Tuple[str, str, int]] = cursor.fetchall()

        if not rows:
            print(f"[-] 未找到函数 '{function_name}' 在 {table_name} 表中的记录（或不满足过滤条件）")
            return []

        # 可选：对 source_function 去重，保留 depth 更大的那条
        if distinct_source:
            best_by_src = {}
            for src, chain, d in rows:
                if (src not in best_by_src) or (d > best_by_src[src][1]):
                    best_by_src[src] = (chain, d)
            dedup_rows = [(src, best_by_src[src][0], best_by_src[src][1]) for src in best_by_src]
            # 保持与 "all" 一致的降序 depth
            dedup_rows.sort(key=lambda x: x[2], reverse=True)
            rows = dedup_rows

        print(f"[+] 符合条件的记录数: {len(rows)}")
        if rows:
            depths = [r[2] for r in rows]
            print(f"[+] depth 分布: min={min(depths)}, max={max(depths)}, count={len(depths)}")

        return rows

    except sqlite3.Error as e:
        print(f"[-] 数据库查询错误: {e}")
        return []
    finally:
        if conn:
            conn.close()
            print(f"[+] 数据库连接已关闭")
