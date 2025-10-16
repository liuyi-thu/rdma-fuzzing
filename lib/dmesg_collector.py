import subprocess
import logging
import time
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class DmesgCollector:
    """基于journalctl的内核日志收集器"""

    def __init__(self, repo_dir: Path = None):
        self.start_time = None
        self.end_time = None
        self.repo_dir = repo_dir or Path("./repo")
        self.repo_dir.mkdir(parents=True, exist_ok=True)

    def get_baseline(self) -> bool:
        """记录当前时间作为基线时间"""
        self.start_time = datetime.now()
        logger.debug("Journalctl baseline time set to %s", self.start_time)
        return True

    def collect_new_messages(self, idx: str) -> str:
        """收集两个时间点之间的内核日志消息，返回相关内容"""
        self.end_time = datetime.now()
        
        if self.start_time is None:
            logger.warning("No start time recorded, cannot collect journalctl messages")
            return ""

        try:
            # 格式化时间以供journalctl使用
            start_time_str = self.start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_time_str = self.end_time.strftime("%Y-%m-%d %H:%M:%S")
            
            # 使用journalctl收集指定时间范围内的内核日志
            # 只收集内核日志并进行过滤，避免读取过多无用信息
            cmd = [
                "journalctl",
                "--since", start_time_str,
                "--until", end_time_str,
                "-k",  # 只显示内核日志
                "-o", "short-iso"  # 使用标准格式
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode != 0:
                logger.warning("journalctl command failed: %s", result.stderr)
                return ""

            # 过滤包含KASAN、Oops等关键字的行，这些通常是内核错误信息
            lines = result.stdout.splitlines()
            filtered_lines = []
            keywords = ["KASAN", "Oops", "kernel", "null-ptr-deref", "BUG", "WARNING", "segfault"]
            
            for line in lines:
                # 检查是否包含我们关心的关键字
                if any(keyword in line for keyword in keywords):
                    filtered_lines.append(line)
            
            new_content = "\n".join(filtered_lines)

            if new_content:
                dmesg_path = self.repo_dir / f"{idx}_dmesg.log"
                try:
                    with open(dmesg_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    logger.info("Saved %d filtered journalctl lines to %s", len(filtered_lines), dmesg_path)
                except Exception as e:
                    logger.exception("Failed to save journalctl to file: %s", e)
            else:
                logger.debug("No relevant journalctl messages found")

            return new_content

        except subprocess.TimeoutExpired:
            logger.warning("journalctl collection command timed out")
            return ""
        except Exception as e:
            logger.exception("Failed to collect journalctl messages: %s", e)
            return ""

    def collect_recent_messages(self, idx: str, seconds_ago: int = 30) -> str:
        """收集最近N秒的内核日志信息（备用方法）"""
        try:
            # 计算开始时间
            start_time = datetime.now().timestamp() - seconds_ago
            start_time_str = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S")

            # 使用journalctl收集最近的日志
            cmd = [
                "journalctl",
                "--since", start_time_str,
                "-k",  # 只显示内核日志
                "-o", "short-iso"
            ]

            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                content = result.stdout
                if content:
                    # 过滤内容
                    lines = content.splitlines()
                    filtered_lines = []
                    keywords = ["KASAN", "Oops", "kernel", "null-ptr-deref", "BUG", "WARNING", "segfault"]
                    
                    for line in lines:
                        if any(keyword in line for keyword in keywords):
                            filtered_lines.append(line)
                    
                    filtered_content = "\n".join(filtered_lines)
                    
                    dmesg_path = self.repo_dir / f"{idx}_dmesg_recent.log"
                    with open(dmesg_path, "w", encoding="utf-8") as f:
                        f.write(filtered_content)
                    logger.info("Saved recent journalctl (%ds) to %s", seconds_ago, dmesg_path)
                return content
            else:
                logger.warning("journalctl command failed: %s", result.stderr)
                return ""

        except Exception:
            logger.exception("Failed to collect recent journalctl messages")
            return ""

    def _collect_tail_fallback(self, idx: str, lines: int = 100) -> str:
        """回退方法：使用journalctl获取最近的行"""
        try:
            # 使用journalctl的--lines选项获取最近的日志
            cmd = [
                "journalctl",
                "-k",  # 只显示内核日志
                "--lines", str(lines),
                "-o", "short-iso"
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                content = result.stdout
                if content:
                    # 过滤内容
                    lines = content.splitlines()
                    filtered_lines = []
                    keywords = ["KASAN", "Oops", "kernel", "null-ptr-deref", "BUG", "WARNING", "segfault"]
                    
                    for line in lines:
                        if any(keyword in line for keyword in keywords):
                            filtered_lines.append(line)
                    
                    filtered_content = "\n".join(filtered_lines)
                    
                    dmesg_path = self.repo_dir / f"{idx}_dmesg_tail.log"
                    with open(dmesg_path, "w", encoding="utf-8") as f:
                        f.write(filtered_content)
                    logger.info("Saved journalctl tail (%d lines) to %s", len(filtered_lines), dmesg_path)
                return content
            else:
                logger.warning("journalctl tail fallback failed: %s", result.stderr)
                return ""

        except Exception as e:
            logger.exception("journalctl tail fallback failed: %s", e)
            return ""