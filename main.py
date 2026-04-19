import os
import json
import hashlib
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

LARK_APP_ID = os.environ.get("LARK_APP_ID")
LARK_APP_SECRET = os.environ.get("LARK_APP_SECRET")
LARK_VERIFICATION_TOKEN = os.environ.get("LARK_VERIFICATION_TOKEN")
KIMI_API_KEY = os.environ.get("KIMI_API_KEY")

processed_message_ids = set()

def get_lark_token():
    url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={
        "app_id": LARK_APP_ID,
        "app_secret": LARK_APP_SECRET
    })
    return resp.json().get("tenant_access_token")

def send_lark_message(open_id, text):
    token = get_lark_token()
    url = "https://open.larksuite.com/open-apis/im/v1/messages?receive_id_type=open_id"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "receive_id": open_id,
        "msg_type": "text",
        "content": json.dumps({"text": text})
    }
    requests.post(url, headers=headers, json=payload)

def ask_kimi(user_message):
    url = "https://api.moonshot.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {KIMI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "moonshot-v1-8k",
        "messages": [
            {"role": "system", "content": "你是一个智能助手，请用中文简洁地回答问题。"},
            {"role": "user", "content": user_message}
        ]
    }
    resp = requests.post(url, headers=headers, json=payload)
    return resp.json()["choices"][0]["message"]["content"]

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    # URL 验证（第一次配置时 Lark 会发一个验证请求）
    if data.get("type") == "url_verification":
        token = data.get("token", "")
        if token == LARK_VERIFICATION_TOKEN:
            return jsonify({"challenge": data.get("challenge")})
        return jsonify({"error": "invalid token"}), 403

    # 处理正常消息事件
    event = data.get("event", {})
    message = event.get("message", {})
    message_id = message.get("message_id", "")

    # 防止重复处理同一条消息
    if message_id in processed_message_ids:
        return jsonify({"code": 0})
    processed_message_ids.add(message_id)

    # 只处理私信文本消息
    if message.get("chat_type") != "p2p":
        return jsonify({"code": 0})
    if message.get("message_type") != "text":
        return jsonify({"code": 0})

    # 拿到用户发的文字
    content = json.loads(message.get("content", "{}"))
    user_text = content.get("text", "").strip()
    if not user_text:
        return jsonify({"code": 0})

    # 拿到发消息的人的 open_id
    sender_open_id = event.get("sender", {}).get("sender_id", {}).get("open_id", "")
    if not sender_open_id:
        return jsonify({"code": 0})

    # 去问 Kimi，把回答发回给用户
    try:
        reply = ask_kimi(user_text)
        send_lark_message(sender_open_id, reply)
    except Exception as e:
        send_lark_message(sender_open_id, f"出错了，请稍后再试：{str(e)}")

    return jsonify({"code": 0})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
