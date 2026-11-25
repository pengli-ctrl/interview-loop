"""AgentRun 清理脚本模块，负责按保留策略清理过期运行记录。"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from interview_loop.platform.run_repository import SQLiteAgentRunRepository


def main() -> None:
    """命令行入口：清理过期 AgentRun。"""
    db_path = Path(os.getenv("INTERVIEWLOOP_DB_PATH", ROOT / "interview_loop.db"))
    repository = SQLiteAgentRunRepository(db_path)
    deleted = repository.purge_expired()
    print(f"purged_runs={deleted}")


if __name__ == "__main__":
    main()
