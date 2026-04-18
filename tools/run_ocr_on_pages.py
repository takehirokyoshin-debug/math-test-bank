"""
run_ocr_on_pages.py
-------------------
exam_pages に登録されたページ画像に OCR をかけるスクリプト。

やること:
  1. exam_pages の page_image_path を読み込む
  2. OCR エンジンでテキストを抽出
  3. 生テキストを ocr_raw_text に保存
  4. 軽く整形したテキストを ocr_clean_text に保存
  5. 信頼度を confidence に保存（対応エンジンのみ）
  6. status を 'ocr_done' に更新

---- OCR エンジンの選択 ----
このスクリプトは差し替えやすい構造にしてあります。
ENGINE 変数を変えるだけで切り替えられます。

  "tesseract" : Tesseract OCR（ローカル・無料・日本語対応）
                pip install pytesseract pillow
                別途 Tesseract 本体のインストールが必要:
                https://github.com/UB-Mannheim/tesseract/wiki
                インストール後、下記 TESSERACT_CMD のパスを設定してください。

  "easyocr"   : EasyOCR（ローカル・無料・精度高め・初回に重いモデルDLあり）
                pip install easyocr

  "stub"      : ダミーエンジン（ライブラリ不要・動作確認用）
                テキストは空文字で登録され、status='ocr_done' になる。

実行方法:
    python tools/run_ocr_on_pages.py                # 未処理をすべて処理
    python tools/run_ocr_on_pages.py EXAM001        # exam_code を指定
    python tools/run_ocr_on_pages.py --engine stub  # エンジンを指定して実行
"""

import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH      = PROJECT_ROOT / "db" / "math_test_bank.db"

# ---------------------------------------------------------------
# 設定
# ---------------------------------------------------------------

# 使用するエンジン: "tesseract" / "easyocr" / "stub"
ENGINE = "stub"

# Tesseract 本体の実行ファイルパス（tesseract エンジン使用時のみ）
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# OCR 対象の status 値（この状態のページだけ処理する）
TARGET_STATUSES = ("unreviewed",)


# ---------------------------------------------------------------
# テキスト整形
# ---------------------------------------------------------------

def clean_text(raw: str) -> str:
    """
    OCR 生テキストを軽く整形する。
    - 行頭・行末の空白を除去
    - 3行以上の連続空行を1行に圧縮
    - 全角スペースを半角に変換
    """
    if not raw:
        return ""
    lines = raw.splitlines()
    lines = [line.replace("\u3000", " ").strip() for line in lines]
    # 連続空行を圧縮
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return cleaned.strip()


# ---------------------------------------------------------------
# OCR エンジン: stub（動作確認用ダミー）
# ---------------------------------------------------------------

def ocr_stub(img_path: Path) -> tuple[str, float]:
    """何もしないダミーエンジン。枠組みの確認用。"""
    return "", 0.0


# ---------------------------------------------------------------
# OCR エンジン: Tesseract
# ---------------------------------------------------------------

def ocr_tesseract(img_path: Path) -> tuple[str, float]:
    """
    Tesseract OCR でテキストを抽出する。
    戻り値: (raw_text, confidence)
    """
    try:
        import pytesseract
        from PIL import Image
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

        img = Image.open(img_path)
        # lang='jpn' で日本語モード。英数字も含む場合は 'jpn+eng'
        data = pytesseract.image_to_data(
            img, lang="jpn", output_type=pytesseract.Output.DICT
        )

        # 単語ごとの信頼度を平均して全体の confidence とする
        confs = [int(c) for c in data["conf"] if str(c).lstrip("-").isdigit() and int(c) >= 0]
        confidence = sum(confs) / len(confs) / 100.0 if confs else 0.0

        raw_text = pytesseract.image_to_string(img, lang="jpn")
        return raw_text, confidence

    except ImportError:
        print("  [ERROR] pytesseract または pillow がインストールされていません。")
        print("          pip install pytesseract pillow")
        return "", 0.0
    except Exception as e:
        print(f"  [ERROR] Tesseract OCR に失敗しました: {e}")
        return "", 0.0


# ---------------------------------------------------------------
# OCR エンジン: EasyOCR
# ---------------------------------------------------------------

def ocr_easyocr(img_path: Path) -> tuple[str, float]:
    """
    EasyOCR でテキストを抽出する。
    初回実行時にモデルのダウンロードが発生する（数百 MB）。
    戻り値: (raw_text, confidence)
    """
    try:
        import easyocr
        reader = easyocr.Reader(["ja", "en"], gpu=False)
        results = reader.readtext(str(img_path))

        # results: [(bbox, text, confidence), ...]
        texts = [r[1] for r in results]
        confs = [r[2] for r in results]

        raw_text   = "\n".join(texts)
        confidence = sum(confs) / len(confs) if confs else 0.0
        return raw_text, confidence

    except ImportError:
        print("  [ERROR] easyocr がインストールされていません。")
        print("          pip install easyocr")
        return "", 0.0
    except Exception as e:
        print(f"  [ERROR] EasyOCR に失敗しました: {e}")
        return "", 0.0


# ---------------------------------------------------------------
# エンジン選択
# ---------------------------------------------------------------

OCR_ENGINES = {
    "stub":       ocr_stub,
    "tesseract":  ocr_tesseract,
    "easyocr":    ocr_easyocr,
}


def get_engine(name: str):
    engine = OCR_ENGINES.get(name)
    if engine is None:
        print(f"[ERROR] 不明なエンジン名: {name}")
        print(f"        使用可能: {list(OCR_ENGINES.keys())}")
        sys.exit(1)
    return engine


# ---------------------------------------------------------------
# 1ページの OCR 処理
# ---------------------------------------------------------------

def run_ocr_on_page(
    conn: sqlite3.Connection,
    page: dict,
    ocr_fn,
) -> bool:
    img_path = Path(page["page_image_path"])
    if not img_path.exists():
        print(f"  [ERROR] 画像が見つかりません: {img_path}")
        conn.execute(
            "UPDATE exam_pages SET status='needs_review' WHERE page_id=?",
            (page["page_id"],),
        )
        return False

    raw_text, confidence = ocr_fn(img_path)
    clean  = clean_text(raw_text)

    conn.execute(
        """
        UPDATE exam_pages
        SET ocr_raw_text  = ?,
            ocr_clean_text = ?,
            confidence     = ?,
            status         = 'ocr_done'
        WHERE page_id = ?
        """,
        (raw_text, clean, confidence, page["page_id"]),
    )
    return True


# ---------------------------------------------------------------
# メイン
# ---------------------------------------------------------------

def main() -> None:
    if not DB_PATH.exists():
        print(f"[ERROR] DBが見つかりません。先に init_test_db.py を実行してください: {DB_PATH}")
        return

    # コマンドライン引数の解析
    engine_name  = ENGINE
    target_code  = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--engine" and i + 1 < len(args):
            engine_name = args[i + 1]
            i += 2
        else:
            target_code = args[i]
            i += 1

    ocr_fn = get_engine(engine_name)
    print(f"使用エンジン: {engine_name}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 対象ページを取得
    placeholders = ",".join("?" * len(TARGET_STATUSES))
    if target_code:
        rows = conn.execute(
            f"""
            SELECT ep.*
            FROM exam_pages ep
            JOIN exams e ON ep.exam_id = e.exam_id
            WHERE ep.status IN ({placeholders})
              AND e.exam_code = ?
            ORDER BY ep.exam_id, ep.page_no
            """,
            (*TARGET_STATUSES, target_code),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            SELECT ep.*
            FROM exam_pages ep
            WHERE ep.status IN ({placeholders})
            ORDER BY ep.exam_id, ep.page_no
            """,
            TARGET_STATUSES,
        ).fetchall()

    if not rows:
        print("[INFO] OCR 処理対象のページがありません。")
        conn.close()
        return

    print(f"--- OCR 開始 ({len(rows)} ページ) ---")

    ok_count   = 0
    fail_count = 0

    try:
        for row in rows:
            page = dict(row)
            label = f"page_id={page['page_id']} / page_no={page['page_no']}"
            if run_ocr_on_page(conn, page, ocr_fn):
                print(f"  [OK] {label}")
                ok_count += 1
            else:
                fail_count += 1

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 処理中にエラーが発生しました: {e}")
    finally:
        conn.close()

    print(f"--- 完了: 成功 {ok_count} ページ / 失敗 {fail_count} ページ ---")
    if engine_name == "stub":
        print("  ※ stub エンジンのため OCR テキストは空です。")
        print("    実際に使う場合は --engine tesseract または --engine easyocr を指定してください。")


if __name__ == "__main__":
    main()
