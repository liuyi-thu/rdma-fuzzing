import random
import sqlite3
from typing import Optional, Tuple


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


def function(function_name: str, space: str) -> Optional[Tuple[str, str]]:
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
