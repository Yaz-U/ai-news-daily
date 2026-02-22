#!/usr/bin/env python3
"""
Windowsタスクスケジューラへの登録スクリプト
管理者権限で実行してください: python setup_scheduler.py
"""

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
BAT_FILE = BASE_DIR / "run_news.bat"
LOG_DIR = BASE_DIR / "logs"

# 実行時刻 (JST) - 6:00, 12:00, 16:00, 20:00
SCHEDULE_TIMES = ["06:00", "12:00", "16:00", "20:00"]
TASK_NAME_PREFIX = "AINewsCuration"


def create_task(task_name: str, time_str: str) -> bool:
    """Windowsタスクスケジューラにタスクを作成"""
    cmd = [
        "schtasks", "/create",
        "/tn", task_name,
        "/tr", f'"{BAT_FILE}"',
        "/sc", "DAILY",
        "/st", time_str,
        "/f",  # 上書き
        "/rl", "HIGHEST",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"[OK] タスク作成: {task_name} @ {time_str}")
            return True
        else:
            print(f"[ERROR] タスク作成失敗: {task_name}")
            print(result.stderr)
            return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def delete_tasks():
    """既存のタスクを削除"""
    for i in range(len(SCHEDULE_TIMES)):
        task_name = f"{TASK_NAME_PREFIX}_{i+1}"
        subprocess.run(
            ["schtasks", "/delete", "/tn", task_name, "/f"],
            capture_output=True
        )


def main():
    print("=" * 50)
    print("AI News Curation スケジューラ設定")
    print("=" * 50)
    print(f"バッチファイル: {BAT_FILE}")
    print(f"実行時刻: {', '.join(SCHEDULE_TIMES)} JST")
    print()

    if not BAT_FILE.exists():
        print(f"[ERROR] バッチファイルが見つかりません: {BAT_FILE}")
        sys.exit(1)

    # 既存タスクを削除
    print("既存タスクを削除中...")
    delete_tasks()

    # 新しいタスクを作成
    print("タスクを登録中...")
    success = 0
    for i, time_str in enumerate(SCHEDULE_TIMES):
        task_name = f"{TASK_NAME_PREFIX}_{i+1}"
        if create_task(task_name, time_str):
            success += 1

    print()
    print(f"登録完了: {success}/{len(SCHEDULE_TIMES)} タスク")

    if success > 0:
        print()
        print("タスクスケジューラで確認できます:")
        print("  タスクスケジューラ > タスクスケジューラライブラリ > AINewsCuration_*")
        print()
        print("手動実行テスト:")
        print(f"  python {BASE_DIR}/fetch_news.py")


if __name__ == "__main__":
    main()
