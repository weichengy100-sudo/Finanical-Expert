import os
import google.generativeai as genai
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# 從環境變數讀取金鑰
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))
genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))

# 簡化版的系統指令
model = genai.GenerativeModel('gemini-1.5-flash', 
    system_instruction="你是一個家庭理財助理，請用繁體中文簡短回答。")

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
    # 【測試版修改】：移除關鍵字判斷，直接把訊息丟給 Gemini
    user_text = event.message.text
    try:
        response = model.generate_content(user_text)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=response.text)
        )
    except Exception as e:
        # 如果出錯，直接在 Line 回傳錯誤訊息，方便我們除錯
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"發生錯誤：{str(e)}")
        )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
