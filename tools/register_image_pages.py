"""
register_image_pages.py
-----------------------
JPG / PNG ファイルを 1ファイル = 1ページとして exam_pages に登録するスクリプト。

やること:
  1. exams の source_file_type が jpg / png のレコードを対象に取得
  2. 原本画像を data/processed/pages/ にコピー
  3. 画像サイズ（幅・高さ）を読み取る
  4. exam_pages テーブルに page_no=1 で登録

必要なライブラリ:
  pip install pillow
  ※ 画像サイズ取得に使用。インストールできない場合は width/height を NULL で登録する。

実行方法:
    python tools/register_image_pages.py          # 未処理をすべて処理
    python tools/register_image_pages.py EXAM002  # exam_code を指定して1件だけ処理
"""

import shutil
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH      = PROJECT_ROOT / "db" / "math_test_bank.db"
PAGES_DIR    = PROJECT_ROOT / "data" / "processed" / "pages"

# Pillow のインポート確認（なければ width/height は None で登録）
try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False


# ---------------------------------------------------------------
# 画像サイズ取得
# ---------------------------------------------------------------

def get_image_size(img_path: Path) -> tuple[int | None, int | None]:
    if not PILLOW_AVAILABLE:
        return None, None
    try:
        with Image.open(img_path) as img:
            return img.width, img.height
    except Exception:
        return None, None


# ---------------------------------------------------------------
# 1件の画像ファイルを処理
# ---------------------------------------------------------------

def register_image(conn: sqlite3.Connection, exam: dict) -> bool:
    """
    1件の JPG/PNG を exam_pages に登録する。
    成功したら True を返す。
    """
    src_path = Path(exam["source_file_path"])
    if not src_path.exists():
        print(f"  [ERROR] ファイルが見つかりません: {src_path}")
        return False

    # すでに登録済みかチェック
    already = conn.execute(
        "SELECT 1 FROM exam_pages WHERE exam_id=? AND page_no=1",
        (exam["exam_id"],),
    ).fetchone()
    if already:
        print(f"  [SKIP] 登録済みです: {exam['exam_code']}")
        return False

    # data/processed/pages/<exam_code>/ にコピー
    out_dir  = PAGES_DIR / exam["exam_code"]
    out_dir.mkdir(parents=True, exist_ok=True)

    suffix       = src_path.suffix.lower()
    img_filename = f"{exam['exam_code']}_p001{suffix}"
    dest_path    = out_dir / img_filename

    if not dest_path.exists():
        shutil.copy2(src_path, dest_path)

    # 画像サイズを取得
    width, height = get_image_size(dest_path)

    conn.execute(
        """
        INSERT INTO exam_pages
            (exam_id, page_no, page_image_path, width, height, status)
        VALUES (?, 1, ?, ?, ?, 'unreviewed')
        """,
        (exam["exam_id"], str(dest_path), width, height),
    )

    # page_count=1 で更新
    conn.execute(
        "UPDATE exams SET page_count=1 WHERE exam_id=?",
        (exam["exam_id"],),
    )

    size_str = f"  {width}x{height}px" if width else "  サイズ不明（pillow未インストール）"
    print(f"  [OK] {exam['exam_code']} → {dest_path.name}{size_str}")
    return True


# ---------------------------------------------------------------
# メイン
# ---------------------------------------------------------------

def main() -> None:
    if not DB_PATH.exists():
        print(f"[ERROR] DBが見つかりません。先に init_test_db.py を実行してください: {DB_PATH}")
        return

    if not PILLOW_AVAILABLE:
        print("[WARN] Pillow がインストールされていません。width/height は NULL で登録します。")
        print("       pip install pillow でインストールできます。")

    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 対象レコードを取得
    target_code = sys.argv[1] if len(sys.argv) > 1 else None
    if target_code:
        rows = conn.execute(
            """
            SELECT * FROM exams
            WHERE source_file_type IN ('jpg','jpeg','png')
              AND exam_code = ?
            """,
            (target_code,),
        ).fetchall()
    else:
        # page_count が未登録（NULL）のものを未処理とみなす
        rows = conn.execute(
            """
            SELECT * FROM exams
            WHERE source_file_type IN ('jpg','jpeg','png')
              AND page_count IS NULL
            """
        ).fetchall()

    if not rows:
        print("[INFO] 処理対象の画像ファイルがありません。")
        conn.close()
        return

    print(f"--- 画像ページ登録開始 ({len(rows)} 件) ---")

    ok_count   = 0
    skip_count = 0

    try:
        for row in rows:
            result = register_image(conn, dict(row))
            if result:
                ok_count += 1
            else:
                skip_count += 1

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 処理中にエラーが発生しました: {e}")
    finally:
        conn.close()

    print(f"--- 完了: 登録 {ok_count} 件 / スキップ {skip_count} 件 ---")


if __name__ == "__main__":
    main()
