#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
if [ -d "$DIR/esb_market_maker" ]; then
    APP_DIR="$DIR/esb_market_maker"
else
    APP_DIR="$DIR"
fi
cd "$APP_DIR"

PERMANENT_URL="https://finlike-shriek-basics.ngrok-free.dev"

echo "=========================================================="
echo "📈 興櫃市場籌碼與推薦券商價差獲利設算系統 — 雲端服務啟動中..."
echo "=========================================================="
echo "📂 資料庫與歷史資料儲存路徑 (Google Drive):"
echo "   /Users/lilinsung/Library/CloudStorage/GoogleDrive-keynes3495@gmail.com/我的雲端硬碟/ESM_DATE"
echo "----------------------------------------------------------"

# 1. 殺死舊的殘留行程
pkill -f "streamlit run app.py" 2>/dev/null
pkill -f "ngrok http 8501" 2>/dev/null
pkill -f "cloudflared tunnel" 2>/dev/null
sleep 1

# 2. 啟動 Streamlit
"$APP_DIR/venv/bin/streamlit" run app.py --server.headless=true > /dev/null 2>&1 &
STREAMLIT_PID=$!

echo "⏳ 正在啟動永久專屬雲端通道..."

# 3. 啟動 ngrok 永久專屬通道
"$APP_DIR/venv/bin/ngrok" http 8501 --url "$PERMANENT_URL" > /dev/null 2>&1 &
NGROK_PID=$!
sleep 2

echo ""
echo "=========================================================="
echo "🎉 專屬永久網址連線就緒！"
echo ""
echo "📱 手機與同事永久固定網址："
echo "👉 $PERMANENT_URL"
echo ""
echo "🔑 系統登入密碼："
echo "👉 $(cat "$APP_DIR/密碼設定.txt" 2>/dev/null || echo "esb888")"
echo ""
echo "(固定網址已自動複製至剪貼簿！可直接按 Cmd+V 貼上分享給同事或手機)"
echo "$PERMANENT_URL" | pbcopy
echo "💻 Mac 本機網址："
echo "👉 http://localhost:8501"
echo "=========================================================="
echo "💡 提示：本視窗請保持開啟（最小化即可）。關閉此視窗或按下 Ctrl+C 即可停止服務。"
echo ""

# 當使用者關閉或中斷時，清理背景行程
trap "kill $STREAMLIT_PID $NGROK_PID 2>/dev/null; exit" INT TERM HUP
wait $STREAMLIT_PID
