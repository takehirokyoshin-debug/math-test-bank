"""
push_db_to_render.py
--------------------
ローカルの math_test_bank.db を Render サーバーにアップロードするスクリプト。

ローカルで import_exam_files.py などを実行してDBを更新したあと、
このスクリプトを実行すると Render 上のDBに反映される。

実行方法:
    python tools/push_db_to_render.py

事前に RENDER_URL 環境変数を設定するか、スクリプト内の RENDER_URL を直接書き換えてください。
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH      = PROJECT_ROOT / "db" / "math_test_bank.db"

# Render のURL（環境変数 RENDER_URL または直接指定）
RENDER_URL = os.environ.get("RENDER_URL", "https://your-app.onrender.com")


def push() -> None:
    try:
        import urllib.request
        import urllib.error
    except ImportError:
        print("[ERROR] urllib が利用できません")
        return

    if not DB_PATH.exists():
        print(f"[ERROR] DBが見つかりません: {DB_PATH}")
        return

    if "your-app.onrender.com" in RENDER_URL:
        print("[ERROR] RENDER_URL が設定されていません。")
        print("        スクリプト内の RENDER_URL を実際のURLに書き換えてください。")
        print("        例: RENDER_URL = 'https://math-test-bank.onrender.com'")
        return

    url      = f"{RENDER_URL.rstrip('/')}/admin/upload_db"
    db_bytes = DB_PATH.read_bytes()
    size_kb  = len(db_bytes) // 1024

    print(f"アップロード先: {url}")
    print(f"ファイルサイズ: {size_kb} KB")
    print("アップロード中...")

    # multipart/form-data を手動で組み立てる（requests 不要）
    boundary = "----PushDBBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="math_test_bank.db"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + db_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            import json
            result = json.loads(resp.read().decode())
            print(f"[OK] {result.get('message', '完了')}")
    except urllib.error.HTTPError as e:
        print(f"[ERROR] HTTPエラー {e.code}: {e.read().decode()}")
    except urllib.error.URLError as e:
        print(f"[ERROR] 接続できませんでした: {e.reason}")
        print("        Render サーバーが起動しているか確認してください。")


if __name__ == "__main__":
    push()
