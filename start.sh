#!/bin/bash
# Render 起動時に実行されるスクリプト。
# 1. DB フォルダを作成
# 2. DBが未初期化なら init_test_db.py を実行
# 3. API サーバーを起動

set -e

echo "=== math_test_bank API サーバー起動 ==="
echo "DB パス: ${DB_PATH:-./db/math_test_bank.db}"

# db/ フォルダを作成（Render の永続ディスクがマウントされるパス）
mkdir -p "$(dirname "${DB_PATH:-./db/math_test_bank.db}")"

# DBが存在しなければ初期化する
if [ ! -f "${DB_PATH:-./db/math_test_bank.db}" ]; then
    echo "DB が見つかりません。初期化します..."
    python tools/init_test_db.py
fi

echo "API サーバーを起動します..."
python tools/api_server.py
