"""
pull_db_from_render.py
----------------------
Render サーバーの math_test_bank.db をローカルにダウンロードするスクリプト。

GPTs で問題を登録したあとにこのスクリプトを実行すると、
Render 上の最新 DB をローカルに保存できます。

次回デプロイ前に push_db_to_render.py でアップロードし直すことで
データを守ることができます。

実行方法:
    python tools/pull_db_from_render.py
"""

import os
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
DB_DIR       = PROJECT_ROOT / "db"
RENDER_URL   = os.environ.get("RENDER_URL", "https://math-test-bank.onrender.com")


def pull() -> None:
    url = f"{RENDER_URL.rstrip('/')}/admin/download_db"

    # バックアップ先のパス（タイムスタンプ付き）
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path  = DB_DIR / "math_test_bank.db"
    backup_path = DB_DIR / f"math_test_bank_backup_{timestamp}.db"

    DB_DIR.mkdir(parents=True, exist_ok=True)

    print(f"ダウンロード元: {url}")
    print("ダウンロード中...")

    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()

        size_kb = len(data) // 1024

        # 既存DBをバックアップ
        if save_path.exists():
            import shutil
            shutil.copy2(save_path, backup_path)
            print(f"既存DBをバックアップ: {backup_path.name}")

        # 保存
        save_path.write_bytes(data)
        print(f"[OK] 保存しました: {save_path} ({size_kb} KB)")
        print()
        print("--- 次のステップ ---")
        print("デプロイ前には以下でRenderに戻してください:")
        print("    python tools/push_db_to_render.py")

    except urllib.error.HTTPError as e:
        print(f"[ERROR] HTTPエラー {e.code}: {e.read().decode()}")
    except urllib.error.URLError as e:
        print(f"[ERROR] 接続できませんでした: {e.reason}")


if __name__ == "__main__":
    pull()
