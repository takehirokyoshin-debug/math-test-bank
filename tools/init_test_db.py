"""
init_test_db.py
---------------
db/math_test_bank.db を初期化するスクリプト。

やること:
  1. db/ フォルダがなければ作成
  2. sql/test_db_schema.sql を実行してテーブルを作成
  3. configs/math_unit_dictionary.csv から unit_dictionary に初期データを投入

再実行しても安全（テーブルは IF NOT EXISTS、辞書は INSERT OR IGNORE）。

実行方法:
    python tools/init_test_db.py
"""

import csv
import sqlite3
from pathlib import Path

PROJECT_ROOT    = Path(__file__).parent.parent
DB_PATH         = PROJECT_ROOT / "db" / "math_test_bank.db"
SCHEMA_PATH     = PROJECT_ROOT / "sql" / "test_db_schema.sql"
UNIT_DICT_PATH  = PROJECT_ROOT / "configs" / "math_unit_dictionary.csv"


# ---------------------------------------------------------------
# テーブル作成
# ---------------------------------------------------------------

def create_tables(conn: sqlite3.Connection) -> None:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"スキーマファイルが見つかりません: {SCHEMA_PATH}")

    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()
    print("[OK] テーブルを作成しました（既存の場合はスキップ）")


# ---------------------------------------------------------------
# 単元辞書の投入
# ---------------------------------------------------------------

def load_unit_dictionary(conn: sqlite3.Connection) -> None:
    if not UNIT_DICT_PATH.exists():
        print(f"[WARN] 単元辞書CSVが見つかりません: {UNIT_DICT_PATH}  (スキップ)")
        return

    rows = []
    with UNIT_DICT_PATH.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append((
                row["subject"].strip(),
                row["unit_name"].strip(),
                row["sub_unit_name"].strip() or None,
                int(row["sort_order"].strip()) if row["sort_order"].strip() else None,
            ))

    # unit_name + sub_unit_name の組み合わせが重複していれば無視する
    conn.executemany(
        """
        INSERT OR IGNORE INTO unit_dictionary (subject, unit_name, sub_unit_name, sort_order)
        SELECT ?, ?, ?, ?
        WHERE NOT EXISTS (
            SELECT 1 FROM unit_dictionary
            WHERE subject = ? AND unit_name = ?
              AND (sub_unit_name = ? OR (sub_unit_name IS NULL AND ? IS NULL))
        )
        """,
        [(r[0], r[1], r[2], r[3], r[0], r[1], r[2], r[2]) for r in rows],
    )
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM unit_dictionary").fetchone()[0]
    print(f"[OK] unit_dictionary: {count} 件（重複はスキップ）")


# ---------------------------------------------------------------
# メイン
# ---------------------------------------------------------------

def main() -> None:
    # db/ ディレクトリを作成
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        conn = sqlite3.connect(DB_PATH)

        print(f"--- DB初期化開始 ---")
        print(f"DBパス: {DB_PATH}")

        create_tables(conn)
        load_unit_dictionary(conn)

        # 作成されたテーブル一覧を表示
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        print(f"[OK] テーブル一覧: {[t[0] for t in tables]}")

        conn.close()
        print("--- DB初期化完了 ---")

    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
    except sqlite3.Error as e:
        print(f"[ERROR] DB操作に失敗しました: {e}")


if __name__ == "__main__":
    main()
