from pathlib import Path
import subprocess
import threading
import logging
import sys
import os
import shutil
import time
import filecmp
import select

from lib.dmesg_collector import DmesgCollector

CWD = Path.cwd()

MY_FUZZ_CMD = ["python3", str(CWD / "my_fuzz_test.py")]
COORDINATOR_CMD = [
    "python3",
    str(CWD / "coordinator.py"),
    "--server-update", str(CWD / "server_update.json"),
    "--client-update", str(CWD / "client_update.json"),
    "--server-view", str(CWD / "server_view.json"),
    "--client-view", str(CWD / "client_view.json"),
]
SERVER_BIN = str(CWD / "build" / "asan" / "server")
CLIENT_BIN = str(CWD / "build" / "asan" / "client")
SERVER_VIEW = str(CWD / "server_view.json")
CLIENT_VIEW = str(CWD / "client_view.json")
CLIENT_SRC = str(CWD / "client.cpp")

REPO_DIR = Path("./repo")
REPO_DIR.mkdir(parents=True, exist_ok=True)
CACHE_BIN = REPO_DIR / "client_cached"

TERMINATE_WAIT = 5

logger = logging.getLogger("rdma_loop")
logger.setLevel(logging.INFO)
h = logging.StreamHandler(sys.stdout)
h.setFormatter(logging.Formatter("[+] %(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(h)

def clean_cached_files(cached_files: list):
    for f in cached_files:
        file = os.path.join(CWD, f)
        if os.path.exists(file):
            try:
                os.remove(f)
            except Exception:
                pass


def next_index() -> str:
    existing = []
    for p in REPO_DIR.iterdir():
        if p.is_file() and p.name.endswith("_client.cpp"):
            digits = ""
            for c in p.name:
                if c.isdigit():
                    digits += c
                else:
                    break
            if digits:
                existing.append(int(digits))
    n = max(existing) + 1 if existing else 1
    return f"{n:06d}"

def safe_terminate(proc: subprocess.Popen, name: str):
    if proc is None or proc.poll() is not None:
        return
    logger.info("Terminating %s (pid=%s)", name, getattr(proc, "pid", None))
    try:
        proc.terminate()
    except Exception:
        logger.exception("Terminate failed, trying to kill %s", name)
        try:
            proc.kill()
        except Exception:
            logger.exception("Kill also failed %s", name)
    try:
        proc.wait(timeout=TERMINATE_WAIT)
    except subprocess.TimeoutExpired:
        logger.info("%s did not exit within %s seconds, forcing kill", name, TERMINATE_WAIT)
        try:
            proc.kill()
        except Exception:
            logger.exception("Force kill %s failed", name)


class ClientCapture:
    def __init__(self, index: str):
        self.index = index
        self.stdout_path = REPO_DIR / f"{index}_client.stdout.log"
        self.stderr_path = REPO_DIR / f"{index}_client.stderr.log"
        self.tmp_stdout_path = REPO_DIR / f"client.tmp.stdout.log"
        self.tmp_stderr_path = REPO_DIR / f"client.tmp.stderr.log"
        self.src_path = REPO_DIR / f"{index}_client.cpp"
        self.lock = threading.Lock()
        self.proc = None
        self.thread = None
        self.dmesg_collector = DmesgCollector(REPO_DIR)  # 添加journalctl收集器

    def start(self, env: dict):
        # 在client启动前设置时间基线
        self.dmesg_collector.get_baseline()

        cmd = ["stdbuf", "-oL", "-eL", CLIENT_BIN]
        logger.info("Starting client: %s RDMA_FUZZ_RUNTIME=%s", " ".join(cmd), CLIENT_VIEW)
        try:
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                bufsize=1,
                text=True,
                errors="replace"
            )
        except Exception:
            logger.exception("Failed to start client")
            self.proc = None
            return None
        self.thread = threading.Thread(target=self._reader_thread, daemon=True)
        self.thread.start()
        return self.proc

    def _reader_thread(self):
        try:
            assert self.proc is not None
            with open(self.stdout_path, "w", encoding="utf-8", errors="replace") as fout, \
                    open(self.stderr_path, "w", encoding="utf-8", errors="replace") as ferr, \
                    open(self.tmp_stdout_path, "w", encoding="utf-8", errors="replace") as ftmp_out, \
                    open(self.tmp_stderr_path, "w", encoding="utf-8", errors="replace") as ftmp_err:
                streams = [self.proc.stdout, self.proc.stderr]
                names = {self.proc.stdout: "stdout", self.proc.stderr: "stderr"}
                while streams:
                    readable, _, _ = select.select(streams, [], [], 1.0)
                    for stream in readable:
                        line = stream.readline()
                        if not line:
                            streams = [s for s in streams if s is not stream]
                            continue
                        stream_name = names.get(stream, "unknown")
                        if stream_name == "stdout":
                            fout.write(line)
                            fout.flush()
                            ftmp_out.write(line)
                            ftmp_out.flush()
                        elif stream_name == "stderr":
                            ferr.write(line)
                            ferr.flush()
                            ftmp_err.write(line)
                            ftmp_err.flush()
                        logger.info("[client %s] %s", stream_name, line.rstrip())
        except Exception:
            logger.exception("Exception while reading client output")
        finally:
            logger.info("Client output reader thread exiting")

    def save_client_and_check_binary(self):
        try:
            shutil.copy2(CLIENT_SRC, self.src_path)
            logger.info("Saved client.cpp to %s", self.src_path)
        except Exception:
            logger.exception("Failed to save client.cpp")

        if CACHE_BIN.exists():
            if filecmp.cmp(CLIENT_BIN, CACHE_BIN, shallow=False):
                logger.error("New client binary is identical to cache!")
            else:
                logger.info("New client binary differs from cache")
        try:
            shutil.copy2(CLIENT_BIN, CACHE_BIN)
            logger.info("Updated client binary cache: %s", CACHE_BIN)
        except Exception:
            logger.exception("Failed to update client binary cache")

    def collect_dmesg_after_exit(self) -> str:
        """收集client退出后的新增journalctl信息"""
        return self.dmesg_collector.collect_new_messages(self.index)


def run_once():
    # 立即保存client.cpp到repo，无论编译是否成功
    files_to_delete = [
        'server_update.json',
        'client_update.json',
        'server_view.json',
        'client_view.json'
    ]
    clean_cached_files(files_to_delete)
    idx = next_index()
    src_path = REPO_DIR / f"{idx}_client.cpp"
    try:
        shutil.copy2(CLIENT_SRC, src_path)
        logger.info("Saved client.cpp to %s", src_path)
    except Exception:
        logger.exception("Failed to save client.cpp")

    logger.info("Starting make SAN=asan build")
    compile_log_path = REPO_DIR / f"{idx}_compile.log"
    try:
        r_make = subprocess.run(["make", "SAN=asan"], capture_output=True, text=True)

        # 保存编译日志到文件
        with open(compile_log_path, "w", encoding="utf-8") as f:
            f.write("=== COMPILE COMMAND ===\n")
            f.write("make SAN=asan\n\n")
            f.write("=== RETURN CODE ===\n")
            f.write(f"{r_make.returncode}\n\n")
            f.write("=== STDOUT ===\n")
            f.write(r_make.stdout or "(empty)")
            f.write("\n\n=== STDERR ===\n")
            f.write(r_make.stderr or "(empty)")

        if r_make.stdout:
            logger.info("Compile stdout: %s", r_make.stdout.strip())
        if r_make.stderr:
            logger.info("Compile stderr: %s", r_make.stderr.strip())
        if r_make.returncode != 0:
            logger.error("make SAN=asan build failed, returncode=%s", r_make.returncode)
            logger.error("Full compile log saved to: %s", compile_log_path)
            return
        logger.info("make SAN=asan build finished successfully")
        logger.info("Compile log saved to: %s", compile_log_path)
    except Exception:
        logger.exception("Failed to execute make SAN=asan")
        # 保存异常信息
        try:
            with open(compile_log_path, "w", encoding="utf-8") as f:
                f.write("=== COMPILE COMMAND ===\n")
                f.write("make SAN=asan\n\n")
                f.write("=== EXCEPTION ===\n")
                f.write("Failed to execute make command - see main log for details\n")
        except:
            pass
        return

    coord_proc = None
    try:
        coord_proc = subprocess.Popen(COORDINATOR_CMD)
        logger.info("coordinator pid=%s", getattr(coord_proc, "pid", None))
    except Exception:
        logger.exception("Failed to start coordinator.py")
        coord_proc = None

    time.sleep(0.6)

    server_proc = None
    try:
        env_s = os.environ.copy()
        env_s["RDMA_FUZZ_RUNTIME"] = SERVER_VIEW
        logger.info("Starting server: %s RDMA_FUZZ_RUNTIME=%s", SERVER_BIN, SERVER_VIEW)
        server_proc = subprocess.Popen([SERVER_BIN], env=env_s)
    except Exception:
        logger.exception("Failed to start server")
        server_proc = None

    time.sleep(0.4)

    logger.info("Starting client...")
    cc = ClientCapture(idx)  # 使用已经生成的idx
    env_c = os.environ.copy()
    env_c["RDMA_FUZZ_RUNTIME"] = CLIENT_VIEW
    client_proc = cc.start(env=env_c)

    cc.save_client_and_check_binary()

    try:
        if client_proc is not None:
            exit_code = client_proc.wait()
            logger.info("client exited, exit code=%s", exit_code)

            # 收集client退出后的新增journalctl信息
            new_dmesg = cc.collect_dmesg_after_exit()
            if new_dmesg:
                logger.info("Collected new journalctl: %d characters", len(new_dmesg))
            else:
                logger.debug("No new journalctl messages found")
        else:
            logger.warning("client not started, cleaning up other processes directly")
    except Exception:
        logger.exception("Exception while waiting for client exit")
    finally:
        logger.info("Cleaning up: terminating server and coordinator if running")
        safe_terminate(server_proc, "server")
        safe_terminate(coord_proc, "coordinator")
        if cc.thread is not None:
            cc.thread.join(timeout=2)
        logger.info("Run finished")

if __name__ == "__main__":
    run_once()