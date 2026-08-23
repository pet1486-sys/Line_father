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

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

def get_gspread_client():
    import json
    creds_json = json.loads(os.environ.get('GOOGLE_CREDENTIALS_JSON'))
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
    return gspread.authorize(creds)

def save_or_update_entry(sheet, date_str, amount):
    """ฟังก์ชันเช็กว่ามีวันที่นี้หรือยัง ถ้ามีให้อัปเดตทับ ถ้าไม่มีให้บันทึกใหม่"""
    records = sheet.get_all_records()
    row_index = None

    # ค้นหาว่ามี Date นี้ในตารางแล้วหรือยัง (นับรวม Header เป็นแถวที่ 1)
    for i, row in enumerate(records, start=2):
        if str(row.get('Date', '')) == date_str:
            row_index = i
            break

    if row_index:
        # มีวันที่นี้แล้ว -> เขียนอัปเดตทับในแถวเดิม (Col 1: Date, Col 2: Type, Col 3: Amount)
        sheet.update_cell(row_index, 2, "ปะยาง")
        sheet.update_cell(row_index, 3, amount)
        return f"🔄 อัปเดตยอดวันที่ {date_str} เป็น {amount:,} บาท เรียบร้อยครับ"
    else:
        # ยังไม่มีวันที่นี้ -> เพิ่มแถวใหม่
        sheet.append_row([date_str, "ปะยาง", amount])
        return f"✅ บันทึกยอดวันที่ {date_str} จำนวน {amount:,} บาท เรียบร้อยครับ"

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
    today_date_str = now.strftime("%Y-%m-%d")
    current_month_year = now.strftime("%Y-%m")

    # 1. เมนูช่วยเหลือ
    if user_msg == "htz32151":
        help_text = (
            "📌 คู่มือการใช้งานบอทบันทึกยอดปะยาง\n\n"
            "1. บันทึกยอดวันนี้:\n"
            "   พิมพ์ 'ปะยาง [จำนวนเงิน]'\n"
            "   ตัวอย่าง: ปะยาง 800\n"
            "   (หากพิมพ์ซ้ำในวันเดียวกัน ระบบจะอัปเดตทับยอดเดิม)\n\n"
            "2. บันทึกย้อนหลัง:\n"
            "   พิมพ์ 'บันทึกย้อนหลัง [ปี-เดือน-วัน] [จำนวนเงิน]'\n"
            "   ตัวอย่าง: บันทึกย้อนหลัง 2026-08-20 500\n\n"
            "3. ดูสรุปยอดประจำเดือน:\n"
            "   พิมพ์ 'รวมยอด'"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=help_text))

    # 2. รวมยอดประจำเดือน
    elif user_msg == "รวมยอด":
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
            reply_txt = (
                f"📊 สรุปยอดปะยาง เดือน {month_name}\n"
                f"จำนวนวันที่บันทึก: {count} วัน\n"
                f"ยอดรวมทั้งหมด: {total_sum:,.2f} บาท"
            )
        except Exception as e:
            reply_txt = f"เกิดข้อผิดพลาด: {str(e)}"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_txt))

    # 3. บันทึกย้อนหลัง
    elif user_msg.startswith("บันทึกย้อนหลัง"):
        # แกะเอาวันที่ YYYY-MM-DD และจำนวนเงิน
        match = re.search(r'(\d{4}-\d{2}-\d{2})\s+(\d+)', user_msg)
        if match:
            target_date = match.group(1)
            amount = int(match.group(2))
            try:
                client = get_gspread_client()
                sheet = client.open("LINE_Tire_Income").sheet1
                reply_txt = save_or_update_entry(sheet, target_date, amount)
            except Exception as e:
                reply_txt = f"บันทึกไม่สำเร็จ: {str(e)}"
        else:
            reply_txt = "⚠️ รูปแบบไม่ถูกต้อง ตัวอย่างที่ถูกต้อง:\nบันทึกย้อนหลัง 2026-08-20 500"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_txt))

    # 4. บันทึกยอดวันนี้ (คำว่า ปะยาง)
    elif "ปะยาง" in user_msg:
        numbers = re.findall(r'\d+', user_msg)
        if numbers:
            amount = int(numbers[0])
            try:
                client = get_gspread_client()
                sheet = client.open("LINE_Tire_Income").sheet1
                reply_txt = save_or_update_entry(sheet, today_date_str, amount)
            except Exception as e:
                reply_txt = f"บันทึกไม่สำเร็จ: {str(e)}"

            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_txt))