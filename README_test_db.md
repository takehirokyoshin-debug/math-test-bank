# 中学数学 定期テスト問題データベース化基盤

## この仕組みの目的

約500本の中学数学の定期テスト（PDF / JPG / PNG）を、**安全に保管しながらデータベース化**するためのローカル基盤です。

最終的には「定期テスト点数予測システム」につなげることを見据えていますが、今回はその前段階として「テスト資産を失わず、後で使える形に整理する土台」を作ることを目的としています。

---

## なぜ数学だけに絞るのか

- 国語・社会などは文章量が多く、著作権の問題が複雑になりやすい
- 数学は図・数式・計算問題が中心で、OCRや問題分類の自動化に向いている
- まず1教科で仕組みを完成させてから、他教科への展開を検討する

---

## なぜ最初から完全自動にしないのか

定期テストの PDF や画像は、次のような理由で完全自動処理が難しいです。

- **レイアウトが学校・年度ごとにバラバラ**（問題番号の位置・フォントが統一されていない）
- **OCR の精度は100%にならない**（特に手書きや数式、図表を含む問題）
- **問題の切り出し境界が曖昧**（大問・小問の区切りが視覚的にしか判断できない）

そのため「機械が下処理 → 人が確認・修正」という **半自動の流れ** を基本にしています。  
`status` と `confidence` の仕組みで「怪しいものをあぶり出す」ことに集中しています。

---

## フォルダ構成

```
math_test_bank/
│
├── README_test_db.md             このファイル
│
├── data/
│   ├── raw_tests/                原本保管庫（取り込み後は変更・削除しない）
│   └── processed/
│       ├── pages/                PDFをページごとに画像化したもの
│       ├── questions/            問題単位に切り出した画像（将来用）
│       ├── figures/              図・グラフの切り出し画像（将来用）
│       └── ocr/                  OCRテキストのバックアップ（将来用）
│
├── db/
│   └── math_test_bank.db         SQLiteデータベース本体
│
├── sql/
│   └── test_db_schema.sql        テーブル定義
│
├── tools/                        実行スクリプト群
│   ├── init_test_db.py           DB初期化＋単元辞書投入
│   ├── import_exam_files.py      ファイル取り込み・原本保管
│   ├── split_pdf_pages.py        PDFをページ画像に分解
│   ├── register_image_pages.py   JPG/PNGをページ登録
│   ├── run_ocr_on_pages.py       ページ画像にOCRをかける
│   ├── register_questions_stub.py CSVから問題をDBに登録
│   └── export_review_targets.py  要確認データをCSV出力
│
├── configs/
│   └── math_unit_dictionary.csv  単元辞書（65件）
│
├── imports/
│   └── questions_template.csv    問題登録用CSVのひな形
│
└── exports/
    └── review_targets.csv        要確認データの出力先
```

---

## SQLiteの役割

SQLite は「サーバー不要のファイル型データベース」です。  
`math_test_bank.db` という1つのファイルに、テスト・ページ・問題の情報を表形式で保管します。

### テーブル構成

```
exams               テスト1本 = 1行（原本パス・学校・学年・学期など）
  └─ exam_pages     ページ1枚 = 1行（画像パス・OCRテキスト・信頼度）
       └─ questions 問題1問  = 1行（単元・テキスト・画像パス・解答）
             └─ figures  図1枚 = 1行（切り出し画像・種別）

unit_dictionary     単元の正規辞書（表記ゆれを防ぐ）
```

### status の意味

| 値 | 意味 |
|---|---|
| `imported` | 取り込み完了（メタデータ推定OK） |
| `needs_review` | 要確認（メタデータ不足・OCR信頼度低など） |
| `unreviewed` | OCR未実行、またはレビュー待ち |
| `ocr_done` | OCR完了・レビュー待ち |
| `reviewed` | 人が確認済み |

### confidence の意味

`0.0〜1.0` の数値で、OCR・分類の信頼度を示します。  
目安として `0.7` 未満のものは `review_targets.csv` で優先的に確認してください。

---

## 原本保管の考え方

取り込んだファイルは `data/raw_tests/` に**コピーして保管**します。  
元のファイルは削除しても構いませんが、この仕組みでは原本を唯一の正とみなし、以下のルールを守っています。

- **raw_tests/ 内のファイルは変更・削除しない**
- 画像処理・OCRはすべて `data/processed/` 以下のコピーに対して行う
- SQLite には画像バイナリを入れず、**ファイルパスで管理**する

万が一 DB が壊れても、`raw_tests/` の原本から再構築できます。

---

## 手順1：DB初期化

プロジェクトのルートフォルダで実行します。

```
cd C:\Users\fujihara\Documents\math_test_bank
python tools/init_test_db.py
```

`db/math_test_bank.db` が作成され、単元辞書（65件）が投入されます。  
何度実行しても既存データは壊れません。

---

## 手順2：ファイル取り込み

PDF / JPG / PNG が入ったフォルダを指定します。

```
python tools/import_exam_files.py C:\Users\fujihara\Desktop\test_pdfs
```

- 原本が `data/raw_tests/` にコピーされます
- `exams` テーブルに登録されます
- ファイル名から学校名・学年・年度・学期を自動推定します
  - 推定できなかった項目は空欄で登録し、`status='needs_review'` になります

**ファイル名の推奨形式:**

```
〇〇中学_2年_2024_2学期期末.pdf
△△中学校_3年_2023_学年末.jpg
```

アンダースコア区切りで「学校名・学年・年度・学期」の順にすると推定精度が上がります。

---

## 手順3：PDF のページ分解

```
python tools/split_pdf_pages.py
```

- `source_file_type='pdf'` のファイルが対象です
- 1ページずつ PNG 画像化して `data/processed/pages/` に保存します
- `exam_pages` テーブルに登録されます

**事前にインストールが必要:**

```
pip install pymupdf
```

特定の PDF だけ処理したい場合:

```
python tools/split_pdf_pages.py 〇〇中学_2年_2024_2学期期末_001
```

---

## 手順4：JPG / PNG のページ登録

```
python tools/register_image_pages.py
```

- JPG / PNG は1ファイル = 1ページとして扱います
- `data/processed/pages/` にコピーし、`exam_pages` に登録します

**事前にインストールが必要（任意）:**

```
pip install pillow
```

Pillow がない場合でも動作しますが、`width` / `height` が空欄になります。

---

## 手順5：OCR 実行

```
python tools/run_ocr_on_pages.py
```

デフォルトは `stub`（ダミー）エンジンです。実際に使う場合はエンジンを指定します。

```
# Tesseract を使う場合
python tools/run_ocr_on_pages.py --engine tesseract

# EasyOCR を使う場合
python tools/run_ocr_on_pages.py --engine easyocr

# 特定のテストだけ処理する場合
python tools/run_ocr_on_pages.py 〇〇中学_2年_2024_2学期期末_001 --engine tesseract
```

**エンジン別インストール:**

| エンジン | インストール | 補足 |
|---|---|---|
| `tesseract` | `pip install pytesseract pillow` | 別途 [Tesseract 本体](https://github.com/UB-Mannheim/tesseract/wiki) のインストールが必要 |
| `easyocr` | `pip install easyocr` | 初回実行時にモデルDL（数百MB）が発生する |

---

## 手順6：問題の登録

### CSVを準備する

`imports/questions_template.csv` をコピーして、問題情報を記入します。

| 列名 | 必須 | 説明 |
|---|---|---|
| `exam_code` | ○ | `exams` テーブルの値と完全一致 |
| `page_no` | ○ | ページ番号（`exam_pages` に存在するもの） |
| `major_question_no` | ○ | 大問番号（例: `1`） |
| `minor_question_no` | | 小問番号（例: `(1)` `ア`） |
| `unit_name` | | 単元辞書の値を使う（`configs/math_unit_dictionary.csv` 参照） |
| `confidence` | | 0.0〜1.0。不明なら空欄 |
| `status` | | 空欄なら `needs_review` で登録 |

### 登録を実行する

```
python tools/register_questions_stub.py
python tools/register_questions_stub.py imports/my_questions.csv  # ファイル指定
```

- `unit_name` が辞書にない場合は `[WARN]` で警告します（登録は行われます）
- `exam_pages` に存在しない `exam_code` / `page_no` の組み合わせは `[SKIP]` されます

---

## review_targets.csv の使い方

```
python tools/export_review_targets.py
```

`exports/review_targets.csv` が生成されます。**Excel で直接開けます**（BOM 付き UTF-8）。

### 出力される内容

| 種別 | 何が要確認か |
|---|---|
| `テスト` | 学校名・学年・学期などが自動推定できなかった |
| `ページ` | OCR 結果が信頼できない、または失敗した |
| `問題` | 単元・OCR テキスト・解答が未確定 |

### 修正の流れ

1. Excel で `review_targets.csv` を開く
2. 内容を確認・修正する
3. 修正した値を CSV に記入し直す
4. `register_questions_stub.py` で再インポート、または DB Browser for SQLite で直接編集する

**DB Browser for SQLite**（無料）を使うと、DB の中身を Excel 感覚で直接確認・編集できます。  
→ https://sqlitebrowser.org/

---

## よくあるエラーと対処

### `DBが見つかりません`
→ 先に `python tools/init_test_db.py` を実行してください。

### `pymupdf がインストールされていません`
→ `pip install pymupdf` を実行してください。

### `exam_code が見つかりません`（問題登録時）
→ `import_exam_files.py` と `split_pdf_pages.py` / `register_image_pages.py` を先に実行してください。  
→ `exam_code` の値は DB の `exams` テーブルで確認できます。

### OCR の結果が全部文字化けする
→ Tesseract の言語パックに `jpn`（日本語）が含まれているか確認してください。  
→ インストール時に「Japanese」を選択する必要があります。

### Excel で CSV を開くと文字化けする
→ `review_targets.csv` は BOM 付き UTF-8 で出力しているため、Excel で直接開けます。  
→ それ以外の CSV（`questions_template.csv` など）は UTF-8 のため、Excel から開く場合は「データ」→「テキストファイルから取り込み」でエンコードを指定してください。

---

## 将来的な拡張

### 1. 問題の自動切り出し

現在は人が CSV を書いて問題を登録していますが、将来的には以下の流れで自動化できます。

- ページ画像の輪郭検出（OpenCV）で問題枠を自動検出
- 検出された領域を `data/processed/questions/` に切り出し
- `questions` テーブルの `question_image_path` に登録
- 信頼度が低いものは自動で `needs_review` に振り分け

### 2. 単元別・学校別の出題傾向分析

`questions` テーブルの `unit_name` と `exam_code`（学校情報を含む）を集計することで:

- 「この学校は三平方の定理を毎年出題している」
- 「2年生の2学期期末は連立方程式が頻出」

といった傾向をCSVやグラフで可視化できます。

### 3. 定期テスト点数予測システムとの接続

本基盤が整ったあとの接続イメージ:

```
math_test_bank.db（問題DB）
       ↓ 単元・難易度・出題頻度データ
点数予測システム
       ↓ 生徒の学習ログ（math_learning_os.db）と照合
       ↓
「この生徒はこの単元が弱い → この問題が出たら何点取れるか」の予測
```

`math_learning_os.db`（学習ログDB）と `math_test_bank.db`（問題DB）を `unit_name` をキーに接続することで、予測システムの土台になります。
