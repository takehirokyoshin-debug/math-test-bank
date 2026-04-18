"""
split_pdf_pages.py
------------------
exams テーブルに登録済みの PDF を、1ページずつ画像に変換するスクリプト。

やること:
  1. exams の source_file_type='pdf' を対象に取得
  2. 各ページを PNG 画像として data/processed/pages/ に保存
  3. exam_pages テーブルに登録
  4. exams.page_count を更新
  5. 失敗した PDF はスキップしてログに残す

必要なライブラリ:
  pip install pymupdf
  ※ PyMuPDF は「import fitz」で使う。軽量で Windows 環境でも動きやすい。
  ※ Poppler 不要のため、別途インストールなしで動く。

実行方法:
    python tools/split_pdf_pages.py          # 未処理の PDF をすべて処理
    python tools/split_pdf_pages.py EXAM001  # exam_code を指定して1件だけ処理
"""

import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH      = PROJECT_ROOT / "db" / "math_test_bank.db"
PAGES_DIR    = PROJECT_ROOT / "data" / "processed" / "pages"

# 画像化の解像度（DPI）。高いほど鮮明だがファイルサイズが増える。
DPI = 150


# ---------------------------------------------------------------
# PyMuPDF のインポート確認
# ---------------------------------------------------------------

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False


# ---------------------------------------------------------------
# 1件の PDF を処理
# ---------------------------------------------------------------

def split_pdf(conn: sqlite3.Connection, exam: dict) -> bool:
    """
    1件の PDF をページ画像に分解して exam_pages に登録する。
    成功したら True を返す。
    """
    pdf_path = Path(exam["source_file_path"])
    if not pdf_path.exists():
        print(f"  [ERROR] ファイルが見つかりません: {pdf_path}")
        return False

    # exam ごとのページ出力先フォルダ
    out_dir = PAGES_DIR / exam["exam_code"]
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        print(f"  [ERROR] PDF を開けませんでした ({exam['exam_code']}): {e}")
        return False

    page_count = len(doc)
    inserted   = 0

    for page_no, page in enumerate(doc, start=1):
        img_filename = f"{exam['exam_code']}_p{page_no:03d}.png"
        img_path     = out_dir / img_filename

        # すでに画像があれば変換をスキップ（DBへの登録も確認）
        already = conn.execute(
            "SELECT 1 FROM exam_pages WHERE exam_id=? AND page_no=?",
            (exam["exam_id"], page_no),
        ).fetchone()
        if already:
            continue

        # ページを画像化
        mat = fitz.Matrix(DPI / 72, DPI / 72)  # 72dpi → DPI に拡大
        pix = page.get_pixmap(matrix=mat)
        pix.save(str(img_path))

        conn.execute(
            """
            INSERT INTO exam_pages
                (exam_id, page_no, page_image_path, width, height, status)
            VALUES (?, ?, ?, ?, ?, 'unreviewed')
            """,
            (exam["exam_id"], page_no, str(img_path), pix.width, pix.height),
        )
        inserted += 1

    doc.close()

    # exams.page_count を更新
    conn.execute(
        "UPDATE exams SET page_count=? WHERE exam_id=?",
        (page_count, exam["exam_id"]),
    )

    print(f"  [OK] {exam['exam_code']}  {page_count} ページ（新規登録: {inserted} 件）")
    return True


# ---------------------------------------------------------------
# メイン
# ---------------------------------------------------------------

def main() -> None:
    if not FITZ_AVAILABLE:
        print("[ERROR] PyMuPDF がインストールされていません。")
        print("        以下のコマンドでインストールしてください:")
        print("        pip install pymupdf")
        return

    if not DB_PATH.exists():
        print(f"[ERROR] DBが見つかりません。先に init_test_db.py を実行してください: {DB_PATH}")
        return

    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 対象レコードを取得
    target_code = sys.argv[1] if len(sys.argv) > 1 else None
    if target_code:
        rows = conn.execute(
            "SELECT * FROM exams WHERE source_file_type='pdf' AND exam_code=?",
            (target_code,),
        ).fetchall()
    else:
        # page_count が未登録（NULL）のものを未処理とみなす
        rows = conn.execute(
            "SELECT * FROM exams WHERE source_file_type='pdf' AND page_count IS NULL",
        ).fetchall()

    if not rows:
        print("[INFO] 処理対象の PDF がありません。")
        conn.close()
        return

    print(f"--- PDF ページ分解開始 ({len(rows)} 件) ---")

    ok_count   = 0
    fail_count = 0

    try:
        for row in rows:
            exam = dict(row)
            if split_pdf(conn, exam):
                ok_count += 1
            else:
                # status を needs_review に更新してスキップ
                conn.execute(
                    "UPDATE exams SET status='needs_review' WHERE exam_id=?",
                    (exam["exam_id"],),
                )
                fail_count += 1

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 処理中にエラーが発生しました: {e}")
    finally:
        conn.close()

    print(f"--- 完了: 成功 {ok_count} 件 / 失敗 {fail_count} 件 ---")
    if fail_count:
        print("  ※ 失敗した PDF は exams.status='needs_review' に更新しました。")


if __name__ == "__main__":
    main()
