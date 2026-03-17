import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
# 導入最新的 Google GenAI SDK
from google import genai

app = Flask(__name__)

# LINE 設定
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# 初始化最新版 Gemini Client
# 它會自動從環境變數 GOOGLE_API_KEY 讀取金鑰，不需手動配置
client = genai.Client(api_key=os.getenv('GOOGLE_API_KEY'))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
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
        # 使用最新的呼叫方式，直接指定 gemini-1.5-flash
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=user_text,
            config={'system_instruction': '你是一個溫暖的家庭理財助理，請用繁體中文簡短回答。'}
        )
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=response.text)
        )
    except Exception as e:
        # 若發生錯誤，直接回傳報錯內容至 Line 方便除錯
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"系統忙碌中，請稍後再試。錯誤代碼：{str(e)}")
        )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
