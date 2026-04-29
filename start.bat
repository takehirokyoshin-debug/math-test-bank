@echo off
echo Math Test Bank を起動します...

start "API Server" python "C:\Users\fujihara\Documents\math_test_bank\tools\api_server.py"

timeout /t 3 /nobreak > nul

start "ngrok" ngrok http --domain=scuttle-crisply-ladies.ngrok-free.dev 8000

echo.
echo ========================================
echo 起動完了！
echo API: https://scuttle-crisply-ladies.ngrok-free.dev
echo ========================================
echo.
echo このウィンドウは閉じても構いません。
echo 終了するには API Server と ngrok のウィンドウを閉じてください。
pause
