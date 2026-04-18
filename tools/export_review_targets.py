"""
export_review_targets.py
------------------------
status='needs_review' のレコードを CSV に出力するスクリプト。
講師があとで Excel 等で開いて手修正しやすい形にする。

出力先: exports/review_targets.csv

出力対象:
  - exams      : status='needs_review'
  - exam_pages : status='needs_review'
  - questions  : status='needs_review'

実行方法:
    python tools/export_review_targets.py
"""

import csv
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH      = PROJECT_ROOT / "db" / "math_test_bank.db"
OUTPUT_PATH  = PROJECT_ROOT / "exports" / "review_targets.csv"

# 出力する列（講師が修正しやすいよう、種別ごとに必要な情報を揃える）
OUTPUT_COLUMNS = [
    "種別",
    "exam_code",
    "page_no",
    "question_no",       # major + minor をまとめた表示用
    "status",
    "confidence",
    "school_name",
    "grade_level",
    "school_year",
    "term_name",
    "unit_name",
    "sub_unit_name",
    "question_type",
    "ocr_clean_text",
    "answer_text",
    "備考",
]

# ---------------------------------------------------------------
# 各テーブルからレビュー対象を取得
# ---------------------------------------------------------------

def fetch_exam_reviews(conn: sqlite3.Connection) -> list[dict]:
    """exams の needs_review を取得する。"""
    rows = conn.execute(
        """
        SELECT
            'テスト'       AS 種別,
            exam_code,
            NULL           AS page_no,
            NULL           AS question_no,
            status,
            NULL           AS confidence,
            school_name,
            grade_level,
            school_year,
            term_name,
            NULL           AS unit_name,
            NULL           AS sub_unit_name,
            NULL           AS question_type,
            NULL           AS ocr_clean_text,
            NULL           AS answer_text,
            '学校名・学年・学期などを確認してください' AS 備考
        FROM exams
        WHERE status = 'needs_review'
        ORDER BY imported_at
        """
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_page_reviews(conn: sqlite3.Connection) -> list[dict]:
    """exam_pages の needs_review を取得する。"""
    rows = conn.execute(
        """
        SELECT
            'ページ'       AS 種別,
            e.exam_code,
            ep.page_no,
            NULL           AS question_no,
            ep.status,
            ep.confidence,
            e.school_name,
            e.grade_level,
            e.school_year,
            e.term_name,
            NULL           AS unit_name,
            NULL           AS sub_unit_name,
            NULL           AS question_type,
            ep.ocr_clean_text,
            NULL           AS answer_text,
            'OCR結果を確認してください' AS 備考
        FROM exam_pages ep
        JOIN exams e ON ep.exam_id = e.exam_id
        WHERE ep.status = 'needs_review'
        ORDER BY e.exam_code, ep.page_no
        """
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_question_reviews(conn: sqlite3.Connection) -> list[dict]:
    """questions の needs_review を取得する。"""
    rows = conn.execute(
        """
        SELECT
            '問題'         AS 種別,
            e.exam_code,
            ep.page_no,
            -- major + minor を "1-(1)" の形式で表示
            CASE
                WHEN q.minor_question_no IS NOT NULL
                    THEN q.major_question_no || '-' || q.minor_question_no
                ELSE q.major_question_no
            END            AS question_no,
            q.status,
            q.confidence,
            e.school_name,
            e.grade_level,
            e.school_year,
            e.term_name,
            q.unit_name,
            q.sub_unit_name,
            q.question_type,
            q.ocr_clean_text,
            q.answer_text,
            '単元・OCR・解答を確認してください' AS 備考
        FROM questions q
        JOIN exam_pages ep ON q.page_id  = ep.page_id
        JOIN exams      e  ON q.exam_id  = e.exam_id
        WHERE q.status = 'needs_review'
        ORDER BY e.exam_code, ep.page_no, q.major_question_no, q.minor_question_no
        """
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------
# メイン
# ---------------------------------------------------------------

def main() -> None:
    if not DB_PATH.exists():
        print(f"[ERROR] DB が見つかりません。先に init_test_db.py を実行してください: {DB_PATH}")
        return

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        exam_rows     = fetch_exam_reviews(conn)
        page_rows     = fetch_page_reviews(conn)
        question_rows = fetch_question_reviews(conn)
        conn.close()

        all_rows = exam_rows + page_rows + question_rows

        with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as f:
            # utf-8-sig = BOM付きUTF-8。Excel で開いたとき文字化けしない。
            writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(all_rows)

        print(f"[OK] review_targets.csv を出力しました: {OUTPUT_PATH}")
        print(f"     テスト: {len(exam_rows)} 件 / ページ: {len(page_rows)} 件 / 問題: {len(question_rows)} 件")
        print(f"     合計:   {len(all_rows)} 件")

    except sqlite3.Error as e:
        print(f"[ERROR] DB 操作に失敗しました: {e}")
    except Exception as e:
        print(f"[ERROR] 予期しないエラーが発生しました: {e}")


if __name__ == "__main__":
    main()
