#!/usr/bin/env python3
"""
Pythonで動かす常駐型スケジューラ
タスクスケジューラを使わない場合はこちらを実行
python scheduler_loop.py
"""

import time
import datetime
import subprocess
import sys
import os
from pathlib import Path

# GEMINI_API_KEY は Windows 環境変数 (setx) で設定してください

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"

# 実行時刻 (JST時) - 6, 12, 16, 20時
SCHEDULE_HOURS = [6, 12, 16, 20]


def log(msg: str):
    now = datetime.datetime.now()
    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")
    log_file = LOG_DIR / f"scheduler_{now.strftime('%Y%m')}.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


def run_fetch():
    """ニュース取得スクリプトを実行"""
    script = BASE_DIR / "fetch_news.py"
    log("fetch_news.py 実行開始")
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, encoding="utf-8",
            env=os.environ,  # APIキーを子プロセスに引き継ぐ
        )
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                log(f"  > {line}")
        if result.returncode != 0 and result.stderr:
            log(f"[ERROR] {result.stderr[:500]}")
    except Exception as e:
        log(f"[ERROR] 実行失敗: {e}")


def get_next_run() -> datetime.datetime:
    """次の実行時刻を計算"""
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst)

    for hour in SCHEDULE_HOURS:
        candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if candidate > now:
            return candidate

    # 翌日の最初の時刻
    tomorrow = now + datetime.timedelta(days=1)
    return tomorrow.replace(hour=SCHEDULE_HOURS[0], minute=0, second=0, microsecond=0)


def main():
    log("=" * 40)
    log("AI News スケジューラ 起動")
    schedule_str = ", ".join(f"{h}:00" for h in SCHEDULE_HOURS)
    log(f"実行スケジュール: {schedule_str} JST")
    log("=" * 40)

    # 起動時に一度実行
    log("起動時の初回実行...")
    run_fetch()

    while True:
        next_run = get_next_run()
        jst = datetime.timezone(datetime.timedelta(hours=9))
        now = datetime.datetime.now(jst)
        wait_seconds = (next_run - now).total_seconds()

        log(f"次の実行: {next_run.strftime('%Y-%m-%d %H:%M JST')} ({int(wait_seconds/60)}分後)")

        # 待機 (5分ごとに状態確認)
        while True:
            jst = datetime.timezone(datetime.timedelta(hours=9))
            now = datetime.datetime.now(jst)
            if now >= next_run:
                break
            remaining = (next_run - now).total_seconds()
            if remaining > 300:
                time.sleep(300)  # 5分待機
            else:
                time.sleep(remaining)
                break

        log("スケジュール実行タイミング到達")
        run_fetch()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("スケジューラを停止しました")
