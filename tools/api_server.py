"""
api_server.py
-------------
math_test_bank のローカル API サーバー。
GPTs の Action からリクエストを受け取り、SQLite DB を操作する。

起動方法:
    python tools/api_server.py

デフォルトポート: 8000
ブラウザで確認: http://localhost:8000/docs  (Swagger UI)
"""

import asyncio
import sqlite3
import urllib.request
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------
# 設定
# ---------------------------------------------------------------

import os

PROJECT_ROOT = Path(__file__).parent.parent

# 環境変数 DB_PATH が設定されていればそちらを使う（Render 上での動作用）
# 未設定の場合はローカルのパスを使う
_db_env = os.environ.get("DB_PATH")
DB_PATH  = Path(_db_env) if _db_env else PROJECT_ROOT / "db" / "math_test_bank.db"

PORT = int(os.environ.get("PORT", 8000))

# ---------------------------------------------------------------
# 自己 ping（Render のスリープ防止）
# ---------------------------------------------------------------

async def _keep_alive():
    """10分ごとに自分自身の /status を叩いてスリープを防ぐ。Render 環境のみ動作。"""
    await asyncio.sleep(60)  # 起動直後は待つ
    while True:
        try:
            url = f"http://localhost:{PORT}/status"
            urllib.request.urlopen(url, timeout=10)
            print("[keep-alive] ping OK")
        except Exception as e:
            print(f"[keep-alive] ping failed: {e}")
        await asyncio.sleep(600)  # 10分ごと

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Render 環境のみ自己 ping を起動
    if os.environ.get("RENDER"):
        asyncio.create_task(_keep_alive())
        print("[keep-alive] 自己 ping タスクを開始しました（10分間隔）")
    yield

app = FastAPI(
    title="math_test_bank API",
    description="中学数学 定期テスト問題DB化基盤のローカルAPIサーバー",
    version="1.0.0",
    lifespan=lifespan,
)

# GPTs（外部）からのリクエストを受け付けるため CORS を許可する
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------
# DB 接続ヘルパー
# ---------------------------------------------------------------

@contextmanager
def get_db():
    if not DB_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=f"DB が見つかりません。先に init_test_db.py を実行してください: {DB_PATH}",
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------
# リクエスト / レスポンスの型定義
# ---------------------------------------------------------------

class ExamInput(BaseModel):
    exam_code:        Optional[str] = None
    school_name:      Optional[str] = None
    grade_level:      Optional[str] = None
    subject:          Optional[str] = "数学"
    term:             Optional[str] = None  # GPT用エイリアス（term_name と同じ）
    term_name:        Optional[str] = None
    school_year:      Optional[str] = None
    exam_type:        Optional[str] = None
    source_file_name: Optional[str] = None  # GPT登録時は省略可
    source_file_type: Optional[str] = None
    source_file_path: Optional[str] = None  # GPT登録時は省略可
    status:           Optional[str] = "imported"

class ExamPatch(BaseModel):
    school_name: Optional[str] = None
    grade_level: Optional[str] = None
    term_name:   Optional[str] = None
    school_year: Optional[str] = None
    exam_type:   Optional[str] = None
    status:      Optional[str] = None

class QuestionInput(BaseModel):
    exam_code:         str
    page_no:           int
    question_no:       Optional[str] = None  # GPT用エイリアス（major_question_no と同じ）
    major_question_no: Optional[str] = None
    minor_question_no: Optional[str] = None
    unit_name:         Optional[str] = None
    sub_unit_name:     Optional[str] = None
    question_type:     Optional[str] = None
    figure_exists:     Optional[int] = 0
    question_text:      Optional[str] = None  # GPT用エイリアス（ocr_clean_text と同じ）
    ocr_raw_text:       Optional[str] = None
    ocr_clean_text:     Optional[str] = None
    figure_description:    Optional[str] = None  # 図の説明文・式（GPT-4oが記述）
    image_base64:          Optional[str] = None  # 図の画像（300×300 白黒PNG、base64）
    question_image_base64: Optional[str] = None  # image_base64 のエイリアス
    answer_text:           Optional[str] = None
    difficulty:            Optional[int] = None  # 受け取るが現在は保存しない
    confidence:            Optional[float] = None
    status:                Optional[str] = "needs_review"

class QuestionPatch(BaseModel):
    unit_name:             Optional[str] = None
    sub_unit_name:         Optional[str] = None
    question_type:         Optional[str] = None
    ocr_clean_text:        Optional[str] = None
    figure_description:    Optional[str] = None
    question_image_base64: Optional[str] = None  # 図の画像（base64）
    image_base64:          Optional[str] = None  # question_image_base64 のエイリアス
    answer_text:           Optional[str] = None
    confidence:            Optional[float] = None
    status:                Optional[str] = None


# ---------------------------------------------------------------
# GET /  ルートエンドポイント（ChatGPT の疎通確認用）
# ---------------------------------------------------------------

@app.get("/", summary="APIの疎通確認")
def root():
    return {"message": "math_test_bank API is running", "docs": "/docs", "status": "/status"}

@app.head("/", summary="HEADリクエスト対応")
def root_head():
    from fastapi.responses import Response
    return Response()


# ---------------------------------------------------------------
# GET /status  登録件数の確認
# ---------------------------------------------------------------

@app.head("/status")
def head_status():
    from fastapi.responses import Response
    return Response()

@app.get("/status", summary="登録件数の確認")
def get_status():
    with get_db() as conn:
        def count(table, where=""):
            sql = f"SELECT COUNT(*) FROM {table}"
            if where:
                sql += f" WHERE {where}"
            return conn.execute(sql).fetchone()[0]

        return {
            "exams_total":            count("exams"),
            "exams_needs_review":     count("exams",      "status='needs_review'"),
            "pages_total":            count("exam_pages"),
            "pages_ocr_done":         count("exam_pages", "status='ocr_done'"),
            "questions_total":        count("questions"),
            "questions_needs_review": count("questions",  "status='needs_review'"),
        }


# ---------------------------------------------------------------
# GET /review_targets  要確認データの取得
# ---------------------------------------------------------------

@app.get("/review_targets", summary="要確認データの取得")
def get_review_targets(target: Optional[str] = None, limit: int = 20):
    result = {}

    with get_db() as conn:

        if target in (None, "exams"):
            rows = conn.execute(
                """
                SELECT exam_code, school_name, grade_level, school_year, term_name, status
                FROM exams
                WHERE status = 'needs_review'
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            result["exams"] = [dict(r) for r in rows]

        if target in (None, "pages"):
            rows = conn.execute(
                """
                SELECT ep.page_id, e.exam_code, ep.page_no,
                       ep.ocr_clean_text, ep.confidence, ep.status
                FROM exam_pages ep
                JOIN exams e ON ep.exam_id = e.exam_id
                WHERE ep.status = 'needs_review'
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            result["pages"] = [dict(r) for r in rows]

        if target in (None, "questions"):
            rows = conn.execute(
                """
                SELECT q.question_code, e.exam_code, ep.page_no,
                       q.major_question_no, q.minor_question_no,
                       q.unit_name, q.ocr_clean_text, q.confidence, q.status
                FROM questions q
                JOIN exam_pages ep ON q.page_id  = ep.page_id
                JOIN exams      e  ON q.exam_id  = e.exam_id
                WHERE q.status = 'needs_review'
                ORDER BY e.exam_code, ep.page_no
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            result["questions"] = [dict(r) for r in rows]

    return result


# ---------------------------------------------------------------
# POST /exams  テストの登録
# ---------------------------------------------------------------

@app.post("/exams", summary="テストの登録")
def register_exam(body: ExamInput):
    with get_db() as conn:
        # term / term_name エイリアス解決（GPTは term を送ってくる場合がある）
        term_name = body.term_name or body.term

        # exam_code が未指定の場合は自動生成
        if not body.exam_code:
            seq = conn.execute("SELECT COUNT(*) FROM exams").fetchone()[0] + 1
            parts = [
                body.school_name  or "unknown",
                body.grade_level  or "unknown",
                body.school_year  or "unknown",
                term_name         or "unknown",
                f"{seq:03d}",
            ]
            exam_code = "_".join(parts)
        else:
            exam_code = body.exam_code

        try:
            cur = conn.execute(
                """
                INSERT INTO exams
                    (exam_code, school_name, grade_level, subject, term_name,
                     school_year, exam_type, source_file_name, source_file_type,
                     source_file_path, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exam_code, body.school_name, body.grade_level, body.subject,
                    term_name, body.school_year, body.exam_type,
                    body.source_file_name, body.source_file_type,
                    body.source_file_path, body.status,
                ),
            )
            return {"success": True, "id": cur.lastrowid, "code": exam_code, "message": "登録しました"}
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail=f"exam_code '{exam_code}' はすでに登録されています")


# ---------------------------------------------------------------
# PATCH /exams/{exam_code}  テスト情報の更新
# ---------------------------------------------------------------

@app.patch("/exams/{exam_code}", summary="テスト情報の更新")
def update_exam(exam_code: str, body: ExamPatch):
    # 更新する列だけ動的に組み立てる
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="更新する値が指定されていません")

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values     = list(fields.values()) + [exam_code]

    with get_db() as conn:
        cur = conn.execute(
            f"UPDATE exams SET {set_clause} WHERE exam_code = ?",
            values,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"exam_code '{exam_code}' が見つかりません")
        return {"success": True, "updated_rows": cur.rowcount, "message": "更新しました"}


# ---------------------------------------------------------------
# POST /questions  問題の登録
# ---------------------------------------------------------------

@app.post("/questions", summary="問題の登録")
def register_question(body: QuestionInput):
    with get_db() as conn:
        # question_no / major_question_no エイリアス解決
        major_q_no  = body.major_question_no or body.question_no or "1"
        # question_text / ocr_clean_text エイリアス解決
        clean_text  = body.ocr_clean_text or body.question_text
        # image_base64 / question_image_base64 エイリアス解決
        img_b64     = body.question_image_base64 or body.image_base64

        # exam_code + page_no から exam_id / page_id を取得
        row = conn.execute(
            """
            SELECT e.exam_id, ep.page_id
            FROM exam_pages ep
            JOIN exams e ON ep.exam_id = e.exam_id
            WHERE e.exam_code = ? AND ep.page_no = ?
            """,
            (body.exam_code, body.page_no),
        ).fetchone()

        if not row:
            # exam_pages が未作成の場合（GPTフロー）: exam を確認してページを自動作成
            exam_row = conn.execute(
                "SELECT exam_id FROM exams WHERE exam_code = ?",
                (body.exam_code,),
            ).fetchone()
            if not exam_row:
                raise HTTPException(
                    status_code=404,
                    detail=f"exam_code='{body.exam_code}' が見つかりません。先にPOST /exams でテストを登録してください",
                )
            exam_id = exam_row["exam_id"]
            cur = conn.execute(
                "INSERT INTO exam_pages (exam_id, page_no, page_image_path) VALUES (?, ?, ?)",
                (exam_id, body.page_no, None),
            )
            page_id = cur.lastrowid
        else:
            exam_id, page_id = row["exam_id"], row["page_id"]

        # question_code を生成
        minor  = body.minor_question_no or "x"
        q_code = f"{body.exam_code}_q{major_q_no}_{minor}"

        # unit_name の辞書チェック（警告のみ）
        unit_warning = None
        if body.unit_name:
            exists = conn.execute(
                "SELECT 1 FROM unit_dictionary WHERE unit_name = ?",
                (body.unit_name,),
            ).fetchone()
            if not exists:
                unit_warning = f"unit_name='{body.unit_name}' は辞書に未登録です"

        try:
            cur = conn.execute(
                """
                INSERT INTO questions
                    (exam_id, page_id, major_question_no, minor_question_no,
                     question_code, unit_name, sub_unit_name, question_type,
                     figure_exists, figure_description, question_image_base64,
                     ocr_raw_text, ocr_clean_text,
                     answer_text, confidence, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exam_id, page_id,
                    major_q_no, body.minor_question_no,
                    q_code, body.unit_name, body.sub_unit_name, body.question_type,
                    body.figure_exists, body.figure_description, img_b64,
                    body.ocr_raw_text, clean_text,
                    body.answer_text, body.confidence, body.status,
                ),
            )
            result = {"success": True, "id": cur.lastrowid, "code": q_code, "message": "登録しました"}
            if unit_warning:
                result["warning"] = unit_warning
            return result
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail=f"question_code '{q_code}' はすでに登録されています")


# ---------------------------------------------------------------
# PATCH /questions/{question_code}  問題情報の更新
# ---------------------------------------------------------------

@app.patch("/questions/{question_code}", summary="問題情報の更新")
def update_question(question_code: str, body: QuestionPatch):
    data = body.model_dump()
    # image_base64 → question_image_base64 エイリアス解決
    if data.get("image_base64") and not data.get("question_image_base64"):
        data["question_image_base64"] = data["image_base64"]
    data.pop("image_base64", None)

    # 画像が送られた場合は figure_exists を自動的に 1 にする
    if data.get("question_image_base64"):
        data["figure_exists"] = 1

    fields = {k: v for k, v in data.items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="更新する値が指定されていません")

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values     = list(fields.values()) + [question_code]

    with get_db() as conn:
        cur = conn.execute(
            f"UPDATE questions SET {set_clause} WHERE question_code = ?",
            values,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"question_code '{question_code}' が見つかりません")
        return {"success": True, "updated_rows": cur.rowcount, "message": "更新しました"}



# ---------------------------------------------------------------
# GET /questions/recent  直近の登録内容確認（デバッグ用）
# ---------------------------------------------------------------

@app.get("/questions/recent", summary="直近の登録内容確認")
def get_recent_questions(limit: int = 5):
    """登録後の確認用。直近limit件の問題を返す。"""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                q.question_code, q.major_question_no, q.minor_question_no,
                e.exam_code, e.school_name, e.grade_level,
                ep.page_no,
                q.unit_name, q.sub_unit_name, q.question_type,
                q.ocr_clean_text, q.answer_text,
                q.figure_exists, q.figure_description,
                CASE WHEN q.question_image_base64 IS NOT NULL THEN 1 ELSE 0 END AS has_image,
                q.confidence, q.status
            FROM questions q
            JOIN exam_pages ep ON q.page_id = ep.page_id
            JOIN exams      e  ON q.exam_id = e.exam_id
            ORDER BY q.question_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return {"count": len(rows), "questions": [dict(r) for r in rows]}


# ---------------------------------------------------------------
# DELETE /questions/{question_code}  問題の削除
# ---------------------------------------------------------------

@app.delete("/questions/{question_code}", summary="問題の削除")
def delete_question(question_code: str):
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM questions WHERE question_code = ?",
            (question_code,),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"question_code '{question_code}' が見つかりません")
        return {"success": True, "message": f"'{question_code}' を削除しました"}


# ---------------------------------------------------------------
# DELETE /exams/{exam_code}  テストと紐づく問題を全て削除
# ---------------------------------------------------------------

@app.delete("/exams/{exam_code}", summary="テストと問題を削除")
def delete_exam(exam_code: str):
    with get_db() as conn:
        # exam_id を取得
        row = conn.execute(
            "SELECT exam_id FROM exams WHERE exam_code = ?", (exam_code,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"exam_code '{exam_code}' が見つかりません")
        exam_id = row["exam_id"]

        # 関連する問題・ページを削除してからテストを削除
        q_count  = conn.execute("SELECT COUNT(*) FROM questions  WHERE exam_id = ?", (exam_id,)).fetchone()[0]
        p_count  = conn.execute("SELECT COUNT(*) FROM exam_pages WHERE exam_id = ?", (exam_id,)).fetchone()[0]
        conn.execute("DELETE FROM questions  WHERE exam_id = ?", (exam_id,))
        conn.execute("DELETE FROM exam_pages WHERE exam_id = ?", (exam_id,))
        conn.execute("DELETE FROM exams      WHERE exam_id = ?", (exam_id,))
        return {
            "success": True,
            "message": f"'{exam_code}' と問題{q_count}件・ページ{p_count}件を削除しました",
        }


# ---------------------------------------------------------------
# GET /questions/search  単元・条件で問題を検索
# ---------------------------------------------------------------

@app.get("/questions/search", summary="問題の検索")
def search_questions(
    unit_name:     Optional[str] = None,
    sub_unit_name: Optional[str] = None,
    question_type: Optional[str] = None,
    school_name:   Optional[str] = None,
    grade_level:   Optional[str] = None,
    school_year:   Optional[str] = None,
    status:        Optional[str] = None,
    limit:         int = 10,
):
    """
    条件に合う問題を返す。
    例: /questions/search?unit_name=一次関数&limit=5
    """
    conditions = []
    params     = []

    if unit_name:
        conditions.append("q.unit_name LIKE ?")
        params.append(f"%{unit_name}%")
    if sub_unit_name:
        conditions.append("q.sub_unit_name LIKE ?")
        params.append(f"%{sub_unit_name}%")
    if question_type:
        conditions.append("q.question_type = ?")
        params.append(question_type)
    if school_name:
        conditions.append("e.school_name LIKE ?")
        params.append(f"%{school_name}%")
    if grade_level:
        conditions.append("e.grade_level = ?")
        params.append(grade_level)
    if school_year:
        conditions.append("e.school_year = ?")
        params.append(school_year)
    if status:
        conditions.append("q.status = ?")
        params.append(status)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT
                q.question_id,
                q.question_code,
                e.exam_code,
                e.school_name,
                e.grade_level,
                e.school_year,
                e.term_name,
                ep.page_no,
                q.major_question_no,
                q.minor_question_no,
                q.unit_name,
                q.sub_unit_name,
                q.question_type,
                q.figure_exists,
                q.figure_description,
                CASE WHEN q.question_image_base64 IS NOT NULL THEN 1 ELSE 0 END AS has_image,
                q.ocr_clean_text,
                q.answer_text,
                q.confidence,
                q.status
            FROM questions q
            JOIN exam_pages ep ON q.page_id  = ep.page_id
            JOIN exams      e  ON q.exam_id  = e.exam_id
            {where}
            ORDER BY q.question_id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return {"total": len(rows), "questions": [dict(r) for r in rows]}


# ---------------------------------------------------------------
# GET /questions/{question_code}  問題1件の詳細取得
# ---------------------------------------------------------------

@app.get("/questions/{question_code}", summary="問題の詳細取得")
def get_question(question_code: str):
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT
                q.*,
                e.exam_code,
                e.school_name,
                e.grade_level,
                e.school_year,
                e.term_name,
                ep.page_no,
                ep.page_image_path
            FROM questions q
            JOIN exam_pages ep ON q.page_id = ep.page_id
            JOIN exams      e  ON q.exam_id = e.exam_id
            WHERE q.question_code = ?
            """,
            (question_code,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"question_code '{question_code}' が見つかりません")
        return dict(row)


# ---------------------------------------------------------------
# GET /exams/list  テスト一覧の取得
# ---------------------------------------------------------------

@app.get("/exams/list", summary="テスト一覧の取得")
def list_exams(
    school_name: Optional[str] = None,
    grade_level: Optional[str] = None,
    school_year: Optional[str] = None,
    limit:       int = 20,
):
    conditions = []
    params     = []

    if school_name:
        conditions.append("school_name LIKE ?")
        params.append(f"%{school_name}%")
    if grade_level:
        conditions.append("grade_level = ?")
        params.append(grade_level)
    if school_year:
        conditions.append("school_year = ?")
        params.append(school_year)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT
                exam_id, exam_code, school_name, grade_level,
                school_year, term_name, exam_type,
                source_file_type, page_count, status, imported_at
            FROM exams
            {where}
            ORDER BY imported_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return {"total": len(rows), "exams": [dict(r) for r in rows]}


# ---------------------------------------------------------------
# GET /units  単元辞書の取得
# ---------------------------------------------------------------

@app.get("/units", summary="単元辞書の取得")
def get_units(unit_name: Optional[str] = None):
    with get_db() as conn:
        if unit_name:
            rows = conn.execute(
                """
                SELECT unit_id, unit_name, sub_unit_name, sort_order
                FROM unit_dictionary
                WHERE unit_name LIKE ? AND is_active = 1
                ORDER BY sort_order
                """,
                (f"%{unit_name}%",),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT unit_id, unit_name, sub_unit_name, sort_order
                FROM unit_dictionary
                WHERE is_active = 1
                ORDER BY sort_order
                """
            ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------
# GET /stats/by_unit  単元別の問題数集計
# ---------------------------------------------------------------

@app.get("/stats/by_unit", summary="単元別の問題数集計")
def get_stats_by_unit():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                unit_name,
                COUNT(*)                                    AS total,
                SUM(CASE WHEN status='needs_review' THEN 1 ELSE 0 END) AS needs_review
            FROM questions
            WHERE unit_name IS NOT NULL
            GROUP BY unit_name
            ORDER BY total DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------
# GET /stats/by_school  学校別のテスト数集計
# ---------------------------------------------------------------

@app.get("/stats/by_school", summary="学校別のテスト数集計")
def get_stats_by_school():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                COALESCE(school_name, '（未設定）') AS school_name,
                COUNT(*) AS total
            FROM exams
            GROUP BY school_name
            ORDER BY total DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------
# POST /admin/upload_db  ローカルDBをRenderにアップロード
# ---------------------------------------------------------------

@app.post("/admin/upload_db", summary="ローカルDBをサーバーにアップロード")
async def upload_db(file: UploadFile = File(...)):
    """
    ローカルで作成した math_test_bank.db を Render サーバーに送信して上書きする。
    tools/push_db_to_render.py から呼び出す。
    """
    if not file.filename.endswith(".db"):
        raise HTTPException(status_code=400, detail=".db ファイルのみアップロードできます")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    contents = await file.read()

    # バックアップを残してから上書き
    backup = DB_PATH.with_suffix(".db.bak")
    if DB_PATH.exists():
        import shutil
        shutil.copy2(DB_PATH, backup)

    DB_PATH.write_bytes(contents)
    size_kb = len(contents) // 1024
    return {"success": True, "message": f"DBをアップロードしました ({size_kb} KB)", "backup": str(backup)}


# ---------------------------------------------------------------
# GET /admin/download_db  RenderのDBをローカルにダウンロード
# ---------------------------------------------------------------

@app.get("/admin/download_db", summary="サーバーのDBをダウンロード")
def download_db():
    """
    Render 上の math_test_bank.db をダウンロードする。
    登録作業後にローカルへバックアップするために使う。
    tools/pull_db_from_render.py から呼び出す。
    """
    from fastapi.responses import FileResponse
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="DBが見つかりません")
    return FileResponse(
        path=str(DB_PATH),
        media_type="application/octet-stream",
        filename="math_test_bank.db",
    )


# ---------------------------------------------------------------
# 起動
# ---------------------------------------------------------------

if __name__ == "__main__":
    print(f"DB パス: {DB_PATH}")
    print(f"起動後に http://localhost:{PORT}/docs でAPIの動作確認ができます")
    # app オブジェクトを直接渡す（モジュールパス解決の問題を回避）
    uvicorn.run(app, host="0.0.0.0", port=PORT)
