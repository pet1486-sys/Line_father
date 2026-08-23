import os
import re
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# ดึงค่า Keys จาก Environment Variables บน Render
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ตั้งค่าเชื่อมต่อ Google Sheet ด้วยข้อมูล JSON จาก Environment Variable
def get_gspread_client():
    import json
    creds_json = json.loads(os.environ.get('GOOGLE_CREDENTIALS_JSON'))
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
    return gspread.authorize(creds)

@app.route("/", methods=['GET'])
def index():
    return "Bot is running!"

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
    user_msg = event.message.text.strip()
    now = datetime.now()
    current_month_year = now.strftime("%Y-%m")
    today_str = now.strftime("%Y-%m-%d %H:%M:%S")

    # 1. เช็กคำสั่ง "รวมยอด"
    if user_msg == "รวมยอด":
        try:
            client = get_gspread_client()
            sheet = client.open("LINE_Tire_Income").sheet1
            records = sheet.get_all_records()
            total_sum = 0
            count = 0

            for row in records:
                if str(row.get('Date', '')).startswith(current_month_year):
                    total_sum += float(row.get('Amount', 0))
                    count += 1

            month_name = now.strftime("%m/%Y")
            reply_txt = f"📊 สรุปยอดปะยาง เดือน {month_name}\n" \
                        f"จำนวนรายการ: {count} รายการ\n" \
                        f"ยอดรวมทั้งหมด: {total_sum:,.2f} บาท"
        except Exception as e:
            reply_txt = f"เกิดข้อผิดพลาดในการดึงข้อมูล: {str(e)}"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_txt))

    # 2. เช็กยอดปะยาง (เช่น "ปะยาง = 800 บาท" หรือ "ปะยาง 800")
    elif "ปะยาง" in user_msg:
        numbers = re.findall(r'\d+', user_msg)
        if numbers:
            amount = int(numbers[0])
            try:
                client = get_gspread_client()
                sheet = client.open("LINE_Tire_Income").sheet1
                sheet.append_row([today_str, "ปะยาง", amount])
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"บันทึกยอด {amount:,} บาท เรียบร้อยครับ"))
            except Exception as e:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"บันทึกไม่สำเร็จ: {str(e)}"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)