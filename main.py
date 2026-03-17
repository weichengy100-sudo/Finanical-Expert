import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
# 導入 2026 最新 Google GenAI SDK
from google import genai

app = Flask(__name__)

# --- 1. 設定 LINE 參數 ---
# 這些會從你 Cloud Run 的環境變數中讀取
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# --- 2. 設定 Gemini 參數 ---
# 使用最新 Client 模式，它會自動抓取環境變數中的 GOOGLE_API_KEY
client = genai.Client(api_key=os.getenv('GOOGLE_API_KEY'))

@app.route("/callback", methods=['POST'])
def callback():
    # 這是 Line Webhook 的標準驗證流程
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    
    try:
        # --- 3. 呼叫 Gemini 產生回覆 ---
        # model 使用 'gemini-2.0-flash' 或 'gemini-1.5-flash' 均可
        # 這裡不指定具體的小版本號（如 -001），讓 Google 自動導向最穩定版
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            model='gemini-3-flash',
            contents=user_text,
            config={
                'system_instruction': '你是一個溫暖的家庭理財助理，專門協助 Weicheng 的家人了解投資與理財。請用親切的繁體中文簡短回答。'
            }
        )
        
        # 將 Gemini 的文字回傳給 Line 用戶
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=response.text)
        )
        
    except Exception as e:
        # 如果出錯，將錯誤訊息傳回 Line，方便 debug
        error_msg = f"系統忙碌中，請稍後再試。\n錯誤內容：{str(e)}"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=error_msg)
        )

if __name__ == "__main__":
    # Cloud Run 預設監聽 8080 埠
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
