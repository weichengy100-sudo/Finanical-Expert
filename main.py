import os
import re
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from google import genai
from google.genai import types

app = Flask(__name__)

# --- 1. 設定 LINE 參數 ---
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

try:
    BOT_USER_ID = line_bot_api.get_bot_info().user_id
except Exception as e:
    print(f"無法取得機器人資訊，請檢查 Access Token: {e}")
    BOT_USER_ID = None

# --- 2. 設定 Gemini 參數 ---
client = genai.Client(api_key=os.getenv('GOOGLE_API_KEY'))

# --- 3. 統一管理 System Instruction ---
SYSTEM_INSTRUCTION = (
    "你負責回覆韋誠家人親友的問題。"
    "請保持專業、親切且具備長遠思考的特質。"
    "若問題不明確，請溫柔地引導對方提供更多資訊。"
    "回覆請保持簡潔，盡量在 150 字以內完成。"
)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    should_respond = False
    raw_text = event.message.text

    # --- 4. 判斷回覆觸發條件 ---
    if event.source.type == 'user':
        should_respond = True
        clean_text = raw_text.strip()
    else:
        if hasattr(event.message, 'mention') and event.message.mention:
            for mentionee in event.message.mention.mentionees:
                if mentionee.user_id == BOT_USER_ID:
                    should_respond = True
                    break

        if should_respond:
            clean_text = re.sub(r'@[^\s]+\s?', '', raw_text).strip()
        else:
            clean_text = ""

    if not should_respond or not clean_text:
        return

    try:
        # --- 5. 呼叫 Gemini 產生內容 ---
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite-preview',
            contents=clean_text,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.7,
                max_output_tokens=300,  # 約 150~200 個中文字
            )
        )

        reply_text = response.text

        # --- 6. 回傳訊息給 LINE ---
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )

    except Exception as e:
        print(f"Gemini 呼叫失敗: {e}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="目前暫時連不上線，請稍後再試試看喔！")
        )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
