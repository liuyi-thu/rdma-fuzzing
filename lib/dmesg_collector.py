import subprocess
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class DmesgCollector:
    """高效的增量dmesg信息收集器"""

    def __init__(self, repo_dir: Path = None):
        self.last_line_count = 0
        self.repo_dir = repo_dir or Path("./repo")
        self.repo_dir.mkdir(parents=True, exist_ok=True)

    def get_baseline(self) -> bool:
        """获取当前dmesg行数基线，返回是否成功"""
        try:
            result = subprocess.run(
                ["dmesg"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                self.last_line_count = len(result.stdout.splitlines())
                logger.debug("dmesg baseline set to %d lines", self.last_line_count)
                return True
            else:
                logger.warning("Failed to get dmesg baseline: %s", result.stderr)
                return False
        except subprocess.TimeoutExpired:
            logger.warning("dmesg baseline command timed out")
            return False
        except Exception as e:
            logger.exception("Failed to get dmesg baseline: %s", e)
            return False

    def collect_new_messages(self, idx: str) -> str:
        """只收集新增的dmesg消息，返回新增内容"""
        try:
            # 获取最新的dmesg
            result = subprocess.run(
                ["dmesg"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                logger.warning("dmesg command failed: %s", result.stderr)
                return ""

            all_lines = result.stdout.splitlines()
            # 只取新增的行
            new_lines = all_lines[self.last_line_count:]
            new_content = "\n".join(new_lines)

            if new_content:
                dmesg_path = self.repo_dir / f"{idx}_dmesg.log"
                try:
                    with open(dmesg_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    logger.info("Saved %d new dmesg lines to %s", len(new_lines), dmesg_path)
                except Exception as e:
                    logger.exception("Failed to save dmesg to file: %s", e)
            else:
                logger.debug("No new dmesg messages found")

            # 更新基线
            self.last_line_count = len(all_lines)
            return new_content

        except subprocess.TimeoutExpired:
            logger.warning("dmesg collection command timed out")
            return ""
        except Exception as e:
            logger.exception("Failed to collect new dmesg messages: %s", e)
            return ""

    def collect_recent_messages(self, idx: str, seconds_ago: int = 30) -> str:
        """收集最近N秒的dmesg信息（备用方法）"""
        try:
            # 使用--since参数（如果系统支持）
            start_time = time.time() - seconds_ago
            start_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time))

            result = subprocess.run(
                ["dmesg", "--since", start_time_str],
                capture_output=True, text=True, timeout=5
            )

            if result.returncode == 0:
                content = result.stdout
                if content:
                    dmesg_path = self.repo_dir / f"{idx}_dmesg_recent.log"
                    with open(dmesg_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    logger.info("Saved recent dmesg (%ds) to %s", seconds_ago, dmesg_path)
                return content
            else:
                # 如果--since不支持，回退到tail方法
                return self._collect_tail_fallback(idx, lines=100)

        except Exception:
            logger.debug("dmesg --since not supported, using tail fallback")
            return self._collect_tail_fallback(idx, lines=100)

    def _collect_tail_fallback(self, idx: str, lines: int = 100) -> str:
        """回退方法：使用tail获取最近的行"""
        try:
            # 如果dmesg不支持--since，尝试--tail
            result = subprocess.run(
                ["dmesg", "--tail", str(lines)],
                capture_output=True, text=True, timeout=3
            )

            if result.returncode == 0:
                content = result.stdout
                if content:
                    dmesg_path = self.repo_dir / f"{idx}_dmesg_tail.log"
                    with open(dmesg_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    logger.info("Saved dmesg tail (%d lines) to %s", lines, dmesg_path)
                return content
            else:
                logger.warning("dmesg tail fallback failed: %s", result.stderr)
                return ""

        except Exception as e:
            logger.exception("dmesg tail fallback failed: %s", e)
            return ""