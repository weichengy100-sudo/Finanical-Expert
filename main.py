import os
import re
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
# 導入 2026 最新 Google GenAI SDK
from google import genai
from google.genai import types

app = Flask(__name__)

# --- 1. 設定 LINE 參數 ---
# 請確保在 Cloud Run 或環境變數中設定這些數值
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# 取得機器人自身的 User ID，用於後續比對群組中的 @標記
try:
    BOT_USER_ID = line_bot_api.get_bot_info().user_id
except Exception as e:
    print(f"無法取得機器人資訊，請檢查 Access Token: {e}")
    BOT_USER_ID = None

# --- 2. 設定 Gemini 參數 ---
client = genai.Client(api_key=os.getenv('GOOGLE_API_KEY'))

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
    # 預設不觸發 AI
    should_respond = False
    raw_text = event.message.text
    
    # --- 3. 判斷回覆觸發條件 ---
    if event.source.type == 'user':
        # 情況 A: 1對1 私訊，直接回覆
        should_respond = True
        clean_text = raw_text.strip()
    else:
        # 情況 B: 群組或聊天室，檢查是否被標記 (@Mention)
        if hasattr(event.message, 'mention') and event.message.mention:
            for mentionee in event.message.mention.mentionees:
                if mentionee.user_id == BOT_USER_ID:
                    should_respond = True
                    break
        
        # 如果確定要回覆，過濾掉訊息中的 @名稱 文字，避免干擾 Gemini
        if should_respond:
            # 使用正則表達式移除所有 @開頭的標記，並修剪空白
            clean_text = re.sub(r'@[^\s]+\s?', '', raw_text).strip()
        else:
            clean_text = ""

    # 如果不需回覆或過濾後沒有內容，則跳過
    if not should_respond or not clean_text:
        return

    try:
        # --- 4. 呼叫 Gemini 產生內容 ---
        response = client.models.generate_content(
            model='gemini-3.0-flash', 
            contents=clean_text,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "你是韋誠的AI好友，負責回覆家人親友的問題。"
                    "請保持專業、親切且具備長遠思考的特質。"
                    "若問題不明確，請溫柔地引導對方提供更多資訊。"
                ),
                temperature=0.7,
            )
        )
        
        reply_text = response.text
        
        # --- 5. 回傳訊息給 LINE ---
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        
    except Exception as e:
        print(f"Gemini 呼叫失敗: {e}")
        # 發生錯誤時的友善回覆
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="我的大腦暫時連不上線，請稍後再試試看喔！")
        )

if __name__ == "__main__":
    # Cloud Run 會提供 PORT 環境變數
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
