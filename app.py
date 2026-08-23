import os
import re
import calendar
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
    records = sheet.get_all_records()
    row_index = None

    for i, row in enumerate(records, start=2):
        if str(row.get('Date', '')) == date_str:
            row_index = i
            break

    day_num = int(date_str.split('-')[2])

    if row_index:
        sheet.update_cell(row_index, 2, "ปะยาง")
        sheet.update_cell(row_index, 3, amount)
    else:
        sheet.append_row([date_str, "ปะยาง", amount])

    return (
        f"✅บันทึกยอดวันที่ {day_num} เรียบร้อยครับ\n"
        f"💵ปะยางวันนี้ได้ {amount:,} บาท"
    )

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

    # 1. เมนูช่วยเหลือ
    if user_msg == "htz32151":
        help_text = (
            "📌 คู่มือการใช้งานบอทบันทึกยอดปะยาง\n\n"
            "1. บันทึกยอดวันนี้:\n"
            "   พิมพ์ 'ปะยาง [จำนวนเงิน]'\n"
            "   ตัวอย่าง: ปะยาง 1,200\n\n"
            "2. บันทึกย้อนหลัง:\n"
            "   พิมพ์ 'บันทึกย้อนหลัง [YYYY-MM-DD] [จำนวนเงิน]'\n"
            "   ตัวอย่าง: บันทึกย้อนหลัง 2026-08-20 1,200\n\n"
            "3. ดูสรุปยอด:\n"
            "   - พิมพ์ 'รวมยอด' (ดูเดือนปัจจุบัน)\n"
            "   - พิมพ์ 'รวมยอด 08/2026' (ดูระบุเดือน/ปี)"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=help_text))

    # 2. ดูสรุปยอด
    elif user_msg.startswith("รวมยอด"):
        match_month = re.search(r'(\d{2})/(\d{4})', user_msg)
        if match_month:
            target_month = int(match_month.group(1))
            target_year = int(match_month.group(2))
        else:
            target_month = now.month
            target_year = now.year

        search_prefix = f"{target_year}-{target_month:02d}"
        month_display = f"{target_month:02d}/{target_year}"

        _, total_days_in_month = calendar.monthrange(target_year, target_month)

        try:
            client = get_gspread_client()
            sheet = client.open("LINE_Tire_Income").sheet1
            records = sheet.get_all_records()
            total_sum = 0
            work_days = 0

            for row in records:
                if str(row.get('Date', '')).startswith(search_prefix):
                    raw_val = str(row.get('Amount', 0)).replace(',', '')
                    val = float(raw_val) if raw_val else 0
                    if val > 0:
                        total_sum += val
                        work_days += 1

            off_days = total_days_in_month - work_days

            reply_txt = (
                f"📊สรุปยอดปะยาง เดือน {month_display}\n"
                f"🟢ทำงาน : {work_days}วัน 🔴หยุด : {off_days}วัน\n"
                f"💰ยอดรวม : {total_sum:,.0f} บาท"
            )
        except Exception as e:
            reply_txt = f"เกิดข้อผิดพลาด: {str(e)}"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_txt))

    # 3. บันทึกย้อนหลัง
    elif user_msg.startswith("บันทึกย้อนหลัง"):
        match = re.search(r'(\d{4}-\d{2}-\d{2})\s+([\d,]+)', user_msg)
        if match:
            target_date = match.group(1)
            amount_str = match.group(2).replace(',', '')
            amount = int(amount_str)
            try:
                client = get_gspread_client()
                sheet = client.open("LINE_Tire_Income").sheet1
                reply_txt = save_or_update_entry(sheet, target_date, amount)
            except Exception as e:
                reply_txt = f"บันทึกไม่สำเร็จ: {str(e)}"
        else:
            reply_txt = "⚠️ รูปแบบไม่ถูกต้อง ตัวอย่าง:\nบันทึกย้อนหลัง 2026-08-20 1,200"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_txt))

    # 4. บันทึกยอดวันนี้
    elif "ปะยาง" in user_msg:
        clean_msg = user_msg.replace("ปะยาง", "")
        numbers = re.findall(r'[\d,]+', clean_msg)
        if numbers:
            amount_str = numbers[0].replace(',', '')
            if amount_str.isdigit():
                amount = int(amount_str)
                try:
                    client = get_gspread_client()
                    sheet = client.open("LINE_Tire_Income").sheet1
                    reply_txt = save_or_update_entry(sheet, today_date_str, amount)
                except Exception as e:
                    reply_txt = f"บันทึกไม่สำเร็จ: {str(e)}"

                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_txt))