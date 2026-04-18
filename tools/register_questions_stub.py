"""
register_questions_stub.py
--------------------------
CSV ファイルから questions テーブルに問題を登録するスクリプト。

完全自動の問題切り出しは将来の課題。
現段階では「人が CSV を書いて登録する」半自動運用を想定している。

やること:
  1. imports/questions_template.csv（または指定 CSV）を読み込む
  2. exam_code + page_no から exam_id / page_id を引く
  3. unit_name が unit_dictionary に存在しない場合は警告する
  4. question_code を自動生成して questions に登録する
  5. 取り込み件数・警告件数を表示する

question_code の形式:
  <exam_code>_q<major_question_no>_<minor_question_no>
  例: 〇〇中学_2年_2024_2学期期末_002_q1_(1)

実行方法:
    python tools/register_questions_stub.py
    python tools/register_questions_stub.py imports/my_questions.csv
"""

import csv
import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT  = Path(__file__).parent.parent
DB_PATH       = PROJECT_ROOT / "db" / "math_test_bank.db"
DEFAULT_CSV   = PROJECT_ROOT / "imports" / "questions_template.csv"

REQUIRED_COLUMNS = {"exam_code", "page_no", "major_question_no"}


# ---------------------------------------------------------------
# 補助: ルックアップキャッシュ
# ---------------------------------------------------------------

def build_page_lookup(conn: sqlite3.Connection) -> dict:
    """
    (exam_code, page_no) → (exam_id, page_id) のマップを作る。
    毎行 SELECT するより効率的。
    """
    rows = conn.execute(
        """
        SELECT e.exam_code, ep.page_no, e.exam_id, ep.page_id
        FROM exam_pages ep
        JOIN exams e ON ep.exam_id = e.exam_id
        """
    ).fetchall()
    return {(r[0], int(r[1])): (r[2], r[3]) for r in rows}


def build_unit_set(conn: sqlite3.Connection) -> set:
    """unit_dictionary に登録されている unit_name の集合を返す。"""
    rows = conn.execute("SELECT DISTINCT unit_name FROM unit_dictionary").fetchall()
    return {r[0] for r in rows}


# ---------------------------------------------------------------
# question_code の生成
# ---------------------------------------------------------------

def make_question_code(exam_code: str, major: str, minor: str) -> str:
    # ファイル名に使えない文字を除去
    safe_major = re.sub(r"[\\/:*?\"<>|]", "", str(major))
    safe_minor = re.sub(r"[\\/:*?\"<>|]", "", str(minor)) if minor else "x"
    return f"{exam_code}_q{safe_major}_{safe_minor}"


# ---------------------------------------------------------------
# 1行のバリデーション
# ---------------------------------------------------------------

def validate_row(row: dict, line_num: int, page_lookup: dict, unit_set: set) -> list[str]:
    errors   = []
    warnings = []

    # 必須列チェック
    for col in REQUIRED_COLUMNS:
        if not row.get(col, "").strip():
            errors.append(f"列 '{col}' が空です")

    exam_code = row.get("exam_code", "").strip()
    page_no   = row.get("page_no", "").strip()

    # page_no が整数かチェック
    if page_no:
        try:
            page_no_int = int(page_no)
        except ValueError:
            errors.append(f"page_no が整数ではありません: {page_no}")
            return errors, warnings
    else:
        return errors, warnings

    # exam_code + page_no の存在チェック
    if exam_code and (exam_code, page_no_int) not in page_lookup:
        errors.append(
            f"exam_code='{exam_code}' / page_no={page_no_int} が"
            f" exam_pages に見つかりません（import_exam_files と split/register を先に実行してください）"
        )

    # unit_name の辞書チェック（警告のみ、エラーにはしない）
    unit_name = row.get("unit_name", "").strip()
    if unit_name and unit_name not in unit_set:
        warnings.append(f"unit_name='{unit_name}' は unit_dictionary に未登録です")

    # confidence の数値チェック
    conf = row.get("confidence", "").strip()
    if conf:
        try:
            float(conf)
        except ValueError:
            errors.append(f"confidence が数値ではありません: {conf}")

    return errors, warnings


# ---------------------------------------------------------------
# メイン
# ---------------------------------------------------------------

def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV

    if not csv_path.exists():
        print(f"[ERROR] CSV ファイルが見つかりません: {csv_path}")
        return

    if not DB_PATH.exists():
        print(f"[ERROR] DB が見つかりません。先に init_test_db.py を実行してください: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    page_lookup = build_page_lookup(conn)
    unit_set    = build_unit_set(conn)

    rows_to_insert = []
    warning_count  = 0
    skip_count     = 0

    print(f"--- 問題登録開始: {csv_path.name} ---")

    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        for line_num, row in enumerate(reader, start=2):
            errors, warnings = validate_row(row, line_num, page_lookup, unit_set)

            for w in warnings:
                print(f"  [WARN] 行{line_num}: {w}")
                warning_count += 1

            if errors:
                for e in errors:
                    print(f"  [SKIP] 行{line_num}: {e}")
                skip_count += 1
                continue

            exam_code = row["exam_code"].strip()
            page_no   = int(row["page_no"].strip())
            major     = row["major_question_no"].strip()
            minor     = row.get("minor_question_no", "").strip() or None

            exam_id, page_id = page_lookup[(exam_code, page_no)]
            question_code    = make_question_code(exam_code, major, minor or "x")

            rows_to_insert.append((
                exam_id,
                page_id,
                major,
                minor,
                question_code,
                row.get("unit_name", "").strip()        or None,
                row.get("sub_unit_name", "").strip()    or None,
                row.get("question_type", "").strip()    or None,
                int(row.get("figure_exists", "0").strip() or "0"),
                row.get("question_image_path", "").strip() or None,
                row.get("ocr_raw_text", "").strip()     or None,
                row.get("ocr_clean_text", "").strip()   or None,
                row.get("answer_text", "").strip()      or None,
                float(row["confidence"].strip()) if row.get("confidence", "").strip() else None,
                row.get("status", "needs_review").strip() or "needs_review",
            ))

    ok_count = 0
    try:
        for params in rows_to_insert:
            try:
                conn.execute(
                    """
                    INSERT INTO questions
                        (exam_id, page_id, major_question_no, minor_question_no,
                         question_code, unit_name, sub_unit_name, question_type,
                         figure_exists, question_image_path, ocr_raw_text, ocr_clean_text,
                         answer_text, confidence, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    params,
                )
                ok_count += 1
            except sqlite3.IntegrityError:
                # question_code の重複はスキップ
                print(f"  [SKIP] question_code 重複: {params[4]}")
                skip_count += 1

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] DB 登録中にエラーが発生しました: {e}")
    finally:
        conn.close()

    print(f"--- 完了: 登録 {ok_count} 件 / スキップ {skip_count} 件 / 警告 {warning_count} 件 ---")


if __name__ == "__main__":
    main()
