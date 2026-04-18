"""
import_exam_files.py
--------------------
指定フォルダ内の PDF / JPG / PNG を取り込むスクリプト。

やること:
  1. 指定フォルダ内の対象ファイルを走査
  2. 原本を data/raw_tests/ にコピーして保管
  3. ファイル名からメタデータを推定
  4. exams テーブルに登録
  5. メタデータが不十分な場合は status='needs_review' にする

ファイル名推定ルール（あくまで補助。無理なら空欄で登録する）:
  例: 〇〇中学_2年_2024_2学期期末.pdf
  → school_name=〇〇中学, grade_level=2年, school_year=2024, term_name=2学期期末

実行方法:
    python tools/import_exam_files.py <取り込み対象フォルダのパス>
    python tools/import_exam_files.py C:/Users/fujihara/Desktop/test_pdfs
"""

import re
import shutil
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH      = PROJECT_ROOT / "db" / "math_test_bank.db"
RAW_DIR      = PROJECT_ROOT / "data" / "raw_tests"

SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

# ファイル名から推定するための正規表現パターン
GRADE_PATTERN     = re.compile(r"([1-3]年)")
YEAR_PATTERN      = re.compile(r"(20\d{2})")
TERM_PATTERNS     = [
    (re.compile(r"(1学期中間|前期中間)"),  "1学期中間"),
    (re.compile(r"(1学期期末|前期期末)"),  "1学期期末"),
    (re.compile(r"(2学期中間|後期中間)"),  "2学期中間"),
    (re.compile(r"(2学期期末|後期期末)"),  "2学期期末"),
    (re.compile(r"(3学期|学年末)"),         "学年末"),
]
EXAM_TYPE_PATTERNS = [
    (re.compile(r"中間"),  "中間"),
    (re.compile(r"期末"),  "期末"),
    (re.compile(r"実力"),  "実力"),
]


# ---------------------------------------------------------------
# ファイル名からメタデータを推定
# ---------------------------------------------------------------

def guess_metadata(filename: str) -> dict:
    """ファイル名（拡張子なし）から学年・年度・学期などを推定する。"""
    meta = {
        "school_name":  None,
        "grade_level":  None,
        "school_year":  None,
        "term_name":    None,
        "exam_type":    None,
    }

    # 学年
    m = GRADE_PATTERN.search(filename)
    if m:
        meta["grade_level"] = m.group(1)

    # 年度（西暦4桁）
    m = YEAR_PATTERN.search(filename)
    if m:
        meta["school_year"] = m.group(1)

    # 学期・試験名
    for pattern, label in TERM_PATTERNS:
        if pattern.search(filename):
            meta["term_name"] = label
            break

    # 試験種別
    for pattern, label in EXAM_TYPE_PATTERNS:
        if pattern.search(filename):
            meta["exam_type"] = label
            break

    # 学校名: アンダースコアや空白で区切った最初のトークンを仮の学校名とする
    # 例: "〇〇中学_2年_2024_2学期期末" → "〇〇中学"
    tokens = re.split(r"[_\s　]+", filename)
    if tokens:
        candidate = tokens[0]
        # 年度・学年・試験種別っぽい文字列でなければ学校名と見なす
        if not YEAR_PATTERN.fullmatch(candidate) and not GRADE_PATTERN.fullmatch(candidate):
            meta["school_name"] = candidate

    return meta


# ---------------------------------------------------------------
# exam_code の自動生成
# ---------------------------------------------------------------

def generate_exam_code(conn: sqlite3.Connection, meta: dict, seq: int) -> str:
    """
    school_name_grade_year_term_連番 形式で exam_code を生成する。
    情報が欠けている部分は 'unknown' で埋める。
    """
    parts = [
        meta.get("school_name")  or "unknown",
        meta.get("grade_level")  or "unknown",
        meta.get("school_year")  or "unknown",
        meta.get("term_name")    or "unknown",
        f"{seq:03d}",
    ]
    return "_".join(parts)


# ---------------------------------------------------------------
# 1ファイルの取り込み処理
# ---------------------------------------------------------------

def import_file(
    conn: sqlite3.Connection,
    src_path: Path,
    seq: int,
) -> bool:
    """
    1ファイルを取り込む。成功したら True を返す。
    """
    suffix = src_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        return False

    # 原本を raw_tests/ にコピー（同名ファイルがあれば上書きしない）
    dest_path = RAW_DIR / src_path.name
    if dest_path.exists():
        print(f"  [SKIP] すでに取り込み済みです: {src_path.name}")
        return False

    shutil.copy2(src_path, dest_path)

    # メタデータ推定
    stem = src_path.stem
    meta = guess_metadata(stem)

    # メタデータが不足している場合は needs_review にする
    missing = [k for k, v in meta.items() if v is None]
    status = "needs_review" if missing else "imported"

    # exam_code 生成
    exam_code = generate_exam_code(conn, meta, seq)

    file_type = suffix.lstrip(".")  # pdf / jpg / png
    if file_type == "jpeg":
        file_type = "jpg"

    try:
        conn.execute(
            """
            INSERT INTO exams
                (exam_code, school_name, grade_level, subject, term_name,
                 school_year, exam_type, source_file_name, source_file_type,
                 source_file_path, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exam_code,
                meta["school_name"],
                meta["grade_level"],
                "数学",
                meta["term_name"],
                meta["school_year"],
                meta["exam_type"],
                src_path.name,
                file_type,
                str(dest_path),
                status,
            ),
        )
        flag = "[needs_review]" if status == "needs_review" else "[OK]"
        missing_str = f"  ※未推定: {missing}" if missing else ""
        print(f"  {flag} {src_path.name} → {exam_code}{missing_str}")
        return True

    except sqlite3.IntegrityError:
        print(f"  [SKIP] exam_code が重複しています: {exam_code}")
        return False


# ---------------------------------------------------------------
# メイン
# ---------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("使い方: python tools/import_exam_files.py <取り込み対象フォルダ>")
        print("例:     python tools/import_exam_files.py C:/Users/fujihara/Desktop/test_pdfs")
        return

    src_dir = Path(sys.argv[1])
    if not src_dir.exists():
        print(f"[ERROR] フォルダが存在しません: {src_dir}")
        return

    if not DB_PATH.exists():
        print(f"[ERROR] DBが見つかりません。先に init_test_db.py を実行してください: {DB_PATH}")
        return

    # 対象ファイルを収集（サブフォルダも含める）
    targets = [
        p for p in sorted(src_dir.rglob("*"))
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    if not targets:
        print(f"[INFO] 対象ファイルが見つかりませんでした: {src_dir}")
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print(f"--- ファイル取り込み開始 ({len(targets)} 件) ---")

    conn = sqlite3.connect(DB_PATH)
    ok_count   = 0
    skip_count = 0

    # 既存のレコード数を連番の開始値に使う
    seq_start = conn.execute("SELECT COUNT(*) FROM exams").fetchone()[0] + 1

    try:
        for i, path in enumerate(targets):
            result = import_file(conn, path, seq_start + i)
            if result:
                ok_count += 1
            else:
                skip_count += 1

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 取り込み中にエラーが発生しました: {e}")
    finally:
        conn.close()

    print(f"--- 完了: 登録 {ok_count} 件 / スキップ {skip_count} 件 ---")


if __name__ == "__main__":
    main()
