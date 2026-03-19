import os
import re
import time
from collections import defaultdict, deque
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
    "你是AI聊天機器人，可以回覆問題。"
    "請用像是導師、顧問的語氣回覆，保持理性、專業、且思考後再回覆，並確保對方能夠理解。"
    "回覆請保持簡潔，盡量在 150 字以內完成。"
)

# --- 4. 對話記憶設定 ---
MEMORY_EXPIRE_SECONDS = 30 * 60  # 記憶保留 30 分鐘
MAX_HISTORY_TURNS = 10            # 最多保留 10 輪對話

# 觸發重置對話的關鍵字
RESET_KEYWORDS = {"新對話", "重置", "清除記憶", "new chat", "reset"}

conversation_store = defaultdict(lambda: {
    "history": deque(maxlen=MAX_HISTORY_TURNS * 2),
    "last_time": 0
})

def get_user_key(event):
    """產生唯一的使用者識別 key"""
    if event.source.type == 'user':
        return event.source.user_id
    elif event.source.type == 'group':
        return f"{event.source.group_id}_{event.source.user_id}"
    return event.source.user_id

def get_history(user_key):
    """取得有效的對話歷史，若超過時間則清除"""
    store = conversation_store[user_key]
    now = time.time()
    if now - store["last_time"] > MEMORY_EXPIRE_SECONDS:
        store["history"].clear()
        print(f"[記憶清除] {user_key} 已超過 {MEMORY_EXPIRE_SECONDS // 60} 分鐘，重置對話")
    return store["history"]

def save_history(user_key, user_text, bot_reply):
    """儲存這輪對話到記憶"""
    store = conversation_store[user_key]
    store["history"].append({"role": "user",  "parts": [{"text": user_text}]})
    store["history"].append({"role": "model", "parts": [{"text": bot_reply}]})
    store["last_time"] = time.time()

def is_reset_command(text):
    """判斷是否為重置指令"""
    return text.strip().lower() in RESET_KEYWORDS

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

    # --- 5. 判斷回覆觸發條件 ---
    if event.source.type == 'user':
        # 私訊：直接回覆
        should_respond = True
        clean_text = raw_text.strip()
    else:
        # 群組：只有被正確 @ 到機器人才回覆
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

    # --- 6. 取得使用者 key ---
    user_key = get_user_key(event)

    # --- 7. 判斷是否為重置指令 ---
    if is_reset_command(clean_text):
        conversation_store[user_key]["history"].clear()
        conversation_store[user_key]["last_time"] = 0
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="✨ 已開啟新對話！之前的記憶已清除，請問有什麼我可以幫你的？")
        )
        return

    # --- 8. 取得對話記憶，組裝送給 Gemini 的內容 ---
    history = get_history(user_key)
    contents = list(history) + [{"role": "user", "parts": [{"text": clean_text}]}]

    try:
        # --- 9. 呼叫 Gemini（帶入對話歷史）---
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite-preview',
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.7,
                max_output_tokens=300,  # 約 150~200 個中文字
            )
        )

        reply_text = response.text

        # --- 10. 儲存這輪對話到記憶 ---
        save_history(user_key, clean_text, reply_text)

        # --- 11. 回傳訊息給 LINE ---
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
