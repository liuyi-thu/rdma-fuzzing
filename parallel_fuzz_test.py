import subprocess

if __name__ == "__main__":
    # 定义不同的 seed 列表
    # seeds = [1, 2, 3, 4, 5]  # 你想要的不同 seed
    seeds = range(6, 50)  # 你想要的不同 seed
    processes = []

    for seed in seeds:
        cmd = [
            "python",
            "fuzz_test.py",
            "--seed",
            str(seed),
            "--rounds",
            "1000",
            "--out-dir",
            f"./debug/out_seed_{seed}",
        ]
        print("启动:", " ".join(cmd))
        p = subprocess.Popen(cmd)
        processes.append(p)

    # 等待所有进程结束
    for p in processes:
        p.wait()
