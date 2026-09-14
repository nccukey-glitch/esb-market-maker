#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
if [ -d "$DIR/esb_market_maker" ]; then
    APP_DIR="$DIR/esb_market_maker"
else
    APP_DIR="$DIR"
fi
cd "$APP_DIR"

echo "=========================================================="
echo "📈 興櫃市場籌碼與推薦券商價差獲利設算系統 — 雲端服務啟動中..."
echo "=========================================================="
echo "📂 資料庫與歷史資料儲存路徑 (Google Drive):"
echo "   /Users/lilinsung/Library/CloudStorage/GoogleDrive-keynes3495@gmail.com/我的雲端硬碟/ESM_DATE"
echo "----------------------------------------------------------"

# 1. 殺死舊的殘留行程
pkill -f "streamlit run app.py" 2>/dev/null
pkill -f "cloudflared tunnel" 2>/dev/null
sleep 1

# 2. 啟動 Streamlit
"$APP_DIR/venv/bin/streamlit" run app.py --server.headless=true > /dev/null 2>&1 &
STREAMLIT_PID=$!

echo "⏳ 正在建立 Cloudflare 專屬安全雲端通道 (請稍候 3~5 秒)..."

# 3. 啟動 Cloudflare Tunnel 並擷取網址
LOG_FILE="/tmp/esb_tunnel.log"
rm -f "$LOG_FILE"
"$APP_DIR/venv/bin/cloudflared" tunnel --url http://localhost:8501 > "$LOG_FILE" 2>&1 &
CLOUDFLARED_PID=$!

TUNNEL_URL=""
for i in {1..30}; do
    sleep 1
    TUNNEL_URL=$(grep -o 'https://[-a-zA-Z0-9.]*\.trycloudflare\.com' "$LOG_FILE" 2>/dev/null | head -n 1)
    if [ -n "$TUNNEL_URL" ]; then
        break
    fi
done

echo ""
echo "=========================================================="
if [ -n "$TUNNEL_URL" ]; then
    echo "🎉 雲端連線通道建立成功！"
    echo ""
    echo "📱 手機與同事瀏覽器專屬網址："
    echo "👉 $TUNNEL_URL"
    echo ""
    echo "(網址已自動複製至剪貼簿！可直接按 Cmd+V 貼上分享給同事或手機)"
    echo "$TUNNEL_URL" | pbcopy
else
    echo "⚠️ 外部通道建立超時，同 Wi-Fi 區域網路仍可正常使用："
    echo "👉 http://192.168.1.2:8501"
fi
echo "💻 Mac 本機網址："
echo "👉 http://localhost:8501"
echo "=========================================================="
echo "💡 提示：本視窗請保持開啟（最小化即可）。關閉此視窗或按下 Ctrl+C 即可停止服務。"
echo ""

# 當使用者關閉或中斷時，清理背景行程
trap "kill $STREAMLIT_PID $CLOUDFLARED_PID 2>/dev/null; exit" INT TERM HUP
wait $STREAMLIT_PID
