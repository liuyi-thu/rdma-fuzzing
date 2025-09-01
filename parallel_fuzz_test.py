# import subprocess

# if __name__ == "__main__":
#     # 定义不同的 seed 列表
#     # seeds = [1, 2, 3, 4, 5]  # 你想要的不同 seed
#     seeds = range(301, 1000)  # 你想要的不同 seed
#     processes = []
#     rounds = 1000  # 每个 seed 的测试轮数

#     for seed in seeds:
#         cmd = [
#             "python",
#             "fuzz_test.py",
#             "--seed",
#             str(seed),
#             "--rounds",
#             str(rounds),
#             "--out-dir",
#             f"./debug/out_seed_{seed}",
#         ]
#         print("启动:", " ".join(cmd))
#         p = subprocess.Popen(cmd)
#         processes.append(p)

#     # 等待所有进程结束
#     for p in processes:
#         p.wait()

import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed


def run_fuzz(seed):
    rounds = 1000
    cmd = [
        "python",
        "fuzz_test.py",
        "--seed",
        str(seed),
        "--rounds",
        str(rounds),
        "--out-dir",
        f"./debug/out_seed_{seed}",
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


seeds = range(11000, 12000)  # 你想要的不同 seed

with ProcessPoolExecutor(max_workers=50) as executor:
    futures = [executor.submit(run_fuzz, s) for s in seeds]
    for future in as_completed(futures):
        result = future.result()
        print(f"[完成] seed={result.args[result.args.index('--seed') + 1]}")
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(result.stderr)
