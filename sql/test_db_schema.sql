-- ============================================================
-- math_test_bank / test_db_schema.sql
-- 中学数学 定期テストDB スキーマ定義
-- ============================================================

-- テスト単位のメタデータ
-- 1ファイル = 1行。原本パスと基本情報を保持する。
CREATE TABLE IF NOT EXISTS exams (
    exam_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_code        TEXT    UNIQUE,                        -- 例: 〇〇中_2年_2024_2学期_001
    school_name      TEXT,
    grade_level      TEXT,                                  -- 例: 1年 / 2年 / 3年
    subject          TEXT,                                  -- 今回は原則「数学」固定
    term_name        TEXT,                                  -- 例: 1学期中間 / 2学期期末
    school_year      TEXT,                                  -- 例: 2024
    exam_type        TEXT,                                  -- 例: 中間 / 期末 / 実力
    source_file_name TEXT,                                  -- GPT登録時は省略可
    source_file_type TEXT,                                  -- pdf / jpg / png
    source_file_path TEXT,                                  -- raw_tests/ 以下の絶対パス（省略可）
    page_count       INTEGER,
    imported_at      TEXT    DEFAULT CURRENT_TIMESTAMP,
    status           TEXT    DEFAULT 'imported'             -- imported / needs_review / reviewed
);

-- ページ単位の情報
-- PDFは1ページ=1行、JPG/PNGはファイル全体を1ページとして扱う
CREATE TABLE IF NOT EXISTS exam_pages (
    page_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id          INTEGER NOT NULL,
    page_no          INTEGER NOT NULL,                      -- 1始まり
    page_image_path  TEXT,                                  -- processed/pages/ 以下のパス（GPT登録時は省略可）
    width            INTEGER,
    height           INTEGER,
    ocr_raw_text     TEXT,                                  -- OCRの生出力（未整形）
    ocr_clean_text   TEXT,                                  -- 軽く整形したテキスト
    confidence       REAL,                                  -- OCR信頼度 0.0〜1.0
    status           TEXT    DEFAULT 'unreviewed',          -- unreviewed / reviewed / needs_review
    FOREIGN KEY (exam_id) REFERENCES exams(exam_id)
);

-- 問題単位の情報
-- まずはCSV登録を想定。将来的に自動切り出しに対応する。
CREATE TABLE IF NOT EXISTS questions (
    question_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id            INTEGER NOT NULL,
    page_id            INTEGER NOT NULL,
    major_question_no  TEXT,                                -- 大問番号 例: 1 / 2 / 3
    minor_question_no  TEXT,                                -- 小問番号 例: (1) / ア / a
    question_code      TEXT    UNIQUE,                      -- 例: EXAM001_q2_1
    unit_name          TEXT,                                -- 単元辞書に沿った値
    sub_unit_name      TEXT,                                -- 小単元
    question_type      TEXT,                                -- 計算 / 証明 / 作図 / 記述 など
    figure_exists      INTEGER NOT NULL DEFAULT 0,          -- 図あり=1 / なし=0
    figure_description TEXT,                               -- GPT-4oによる図の説明・式
    question_image_path TEXT,                              -- 切り出し画像パス（将来用）
    question_image_base64 TEXT,                            -- 図の画像（base64、将来用）
    ocr_raw_text       TEXT,
    ocr_clean_text     TEXT,
    answer_text        TEXT,
    confidence         REAL,
    status             TEXT    DEFAULT 'needs_review',      -- needs_review / reviewed / skip
    FOREIGN KEY (exam_id) REFERENCES exams(exam_id),
    FOREIGN KEY (page_id) REFERENCES exam_pages(page_id)
);

-- 図・表・グラフ単位の情報
-- 問題に紐づく図を別管理する（将来の自動切り出しを見据えた構造）
CREATE TABLE IF NOT EXISTS figures (
    figure_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id       INTEGER NOT NULL,
    figure_type       TEXT,                                 -- graph / table / diagram / other
    figure_image_path TEXT    NOT NULL,
    description       TEXT,
    confidence        REAL,
    status            TEXT    DEFAULT 'unreviewed',
    FOREIGN KEY (question_id) REFERENCES questions(question_id)
);

-- 単元辞書
-- 分類を自由入力にせず、この辞書に沿って管理することで表記ゆれを防ぐ
CREATE TABLE IF NOT EXISTS unit_dictionary (
    unit_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    subject       TEXT    NOT NULL,                         -- 今回は「数学」固定
    unit_name     TEXT    NOT NULL,
    sub_unit_name TEXT,
    sort_order    INTEGER,
    is_active     INTEGER DEFAULT 1                         -- 0で論理削除
);
