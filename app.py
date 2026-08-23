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

THAI_MONTHS = [
    "", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
]

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
        f"ปะยางวันนี้ได้ {amount:,} บาท"
    )

def delete_entry(sheet, date_str):
    records = sheet.get_all_records()
    row_index = None

    for i, row in enumerate(records, start=2):
        if str(row.get('Date', '')) == date_str:
            row_index = i
            break

    if row_index:
        sheet.delete_rows(row_index)
        day_num = int(date_str.split('-')[2])
        return f"🗑️ ลบข้อมูลยอดปะยางวันที่ {day_num} ({date_str}) เรียบร้อยแล้วครับ"
    else:
        return f"⚠️ ไม่พบข้อมูลของวันที่ {date_str} ในตารางครับ"

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
            "   - พิมพ์ 'ปะยาง 800' หรือ 'ปะยาง = 800'\n\n"
            "2. บันทึกย้อนหลังในเดือนนี้:\n"
            "   - พิมพ์ 'ปะยางวันที่ 9 = 500'\n"
            "   - พิมพ์ 'ปะยาง วันที่10 = 800 บาท'\n"
            "   - พิมพ์ 'บันทึกย้อนหลัง 2026-08-20 1,200'\n\n"
            "3. ลบยอดเงิน:\n"
            "   - พิมพ์ 'ลบยอด32151 18/08/2026'\n"
            "   - พิมพ์ 'ลบยอด32151 วันนี้'\n\n"
            "4. ดูสรุปยอด:\n"
            "   - พิมพ์ 'รวมยอด' (ดูเดือนปัจจุบัน)\n"
            "   - พิมพ์ 'รวมยอด 08/2026' (ดูระบุเดือน/ปี)\n"
            "   - พิมพ์ 'รวมยอดปี2026' (ดูสรุปรายปี)\n"
            "   - พิมพ์ 'หยุดวันอะไร' (ดูวันที่หยุด)"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=help_text))

    # 2. คำสั่งลบยอด (เช่น "ลบยอด32151 18/08/2026" หรือ "ลบยอด32151 2026-08-18")
    elif user_msg.startswith("ลบยอด32151"):
        target_date = None
        
        if "วันนี้" in user_msg:
            target_date = today_date_str
        else:
            # รูปแบบ DD/MM/YYYY
            match_dmy = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', user_msg)
            # รูปแบบ YYYY-MM-DD
            match_ymd = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', user_msg)

            if match_dmy:
                d = int(match_dmy.group(1))
                m = int(match_dmy.group(2))
                y = int(match_dmy.group(3))
                target_date = f"{y}-{m:02d}-{d:02d}"
            elif match_ymd:
                y = int(match_ymd.group(1))
                m = int(match_ymd.group(2))
                d = int(match_ymd.group(3))
                target_date = f"{y}-{m:02d}-{d:02d}"

        if target_date:
            try:
                client = get_gspread_client()
                sheet = client.open("LINE_Tire_Income").sheet1
                reply_txt = delete_entry(sheet, target_date)
            except Exception as e:
                reply_txt = f"ลบข้อมูลไม่สำเร็จ: {str(e)}"
        else:
            reply_txt = "⚠️ รูปแบบคำสั่งไม่ถูกต้อง ตัวอย่าง:\nลบยอด32151 18/08/2026"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_txt))

    # 3. ดูวันที่หยุด
    elif user_msg.startswith("หยุดวันอะไร"):
        match_month = re.search(r'(\d{2})/(\d{4})', user_msg)
        if match_month:
            target_month = int(match_month.group(1))
            target_year = int(match_month.group(2))
        else:
            target_month = now.month
            target_year = now.year

        search_prefix = f"{target_year}-{target_month:02d}"
        month_display = f"{target_month:02d}/{target_year}"
        thai_month_name = THAI_MONTHS[target_month]

        if target_year == now.year and target_month == now.month:
            days_to_check = now.day
        elif (target_year < now.year) or (target_year == now.year and target_month < now.month):
            _, total_days = calendar.monthrange(target_year, target_month)
            days_to_check = total_days
        else:
            days_to_check = 0

        try:
            client = get_gspread_client()
            sheet = client.open("LINE_Tire_Income").sheet1
            records = sheet.get_all_records()

            recorded_days = set()
            for row in records:
                date_val = str(row.get('Date', ''))
                if date_val.startswith(search_prefix):
                    raw_val = str(row.get('Amount', 0)).replace(',', '')
                    val = float(raw_val) if raw_val else 0
                    if val > 0:
                        day = int(date_val.split('-')[2])
                        recorded_days.add(day)

            off_days_list = [d for d in range(1, days_to_check + 1) if d not in recorded_days]

            if off_days_list:
                lines = ["🔴", f"วันที่หยุดในเดือน {month_display}"]
                for d in off_days_list:
                    lines.append(f"วันที่ {d} {thai_month_name}")
                reply_txt = "\n".join(lines)
            else:
                reply_txt = f"🟢\nเดือน {month_display} ทำงานทุกวัน ไม่มีวันหยุดครับ"

        except Exception as e:
            reply_txt = f"เกิดข้อผิดพลาด: {str(e)}"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_txt))

    # 4. ดูสรุปยอดรายปี
    elif user_msg.startswith("รวมยอดปี"):
        match_year = re.search(r'\d{4}', user_msg)
        target_year = match_year.group(0) if match_year else str(now.year)

        try:
            client = get_gspread_client()
            sheet = client.open("LINE_Tire_Income").sheet1
            records = sheet.get_all_records()

            monthly_totals = {}

            for row in records:
                date_val = str(row.get('Date', ''))
                if date_val.startswith(f"{target_year}-"):
                    month = date_val.split('-')[1]
                    raw_val = str(row.get('Amount', 0)).replace(',', '')
                    val = float(raw_val) if raw_val else 0
                    if val > 0:
                        monthly_totals[month] = monthly_totals.get(month, 0) + val

            if monthly_totals:
                lines = [f"📋สรุปยอดปะยางปี {target_year}"]
                for m in sorted(monthly_totals.keys()):
                    lines.append(f"เดือน {m} = {monthly_totals[m]:,.0f} บาท")
                reply_txt = "\n".join(lines)
            else:
                reply_txt = f"📋สรุปยอดปะยางปี {target_year}\nไม่พบข้อมูลของปีนี้ครับ"

        except Exception as e:
            reply_txt = f"เกิดข้อผิดพลาด: {str(e)}"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_txt))

    # 5. ดูสรุปยอดรายเดือน
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

        if target_year == now.year and target_month == now.month:
            days_to_count = now.day
        elif (target_year < now.year) or (target_year == now.year and target_month < now.month):
            _, total_days = calendar.monthrange(target_year, target_month)
            days_to_count = total_days
        else:
            days_to_count = 0

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

            off_days = max(0, days_to_count - work_days)

            reply_txt = (
                f"📊สรุปยอดปะยาง เดือน {month_display}\n"
                f"ทำงาน : {work_days} วัน\n"
                f"หยุด : {off_days} วัน\n"
                f"ยอดรวม : {total_sum:,.0f} บาท"
            )
        except Exception as e:
            reply_txt = f"เกิดข้อผิดพลาด: {str(e)}"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_txt))

    # 6. บันทึกย้อนหลังรูปแบบเต็ม
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
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_txt))

    # 7. บันทึกย้อนหลังกรณีมีคำว่า "ปะยาง" และ "วันที่"
    elif "ปะยาง" in user_msg and "วันที่" in user_msg:
        match_day = re.search(r'วันที่\s*(\d{1,2})', user_msg)
        numbers = re.findall(r'[\d,]+', user_msg)
        
        if match_day and len(numbers) >= 2:
            day_num = int(match_day.group(1))
            amounts = [n.replace(',', '') for n in numbers if int(n.replace(',', '')) != day_num]
            if amounts and 1 <= day_num <= 31:
                amount = int(amounts[-1])
                target_date = f"{now.year}-{now.month:02d}-{day_num:02d}"
                try:
                    client = get_gspread_client()
                    sheet = client.open("LINE_Tire_Income").sheet1
                    reply_txt = save_or_update_entry(sheet, target_date, amount)
                except Exception as e:
                    reply_txt = f"บันทึกไม่สำเร็จ: {str(e)}"
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_txt))

    # 8. บันทึกยอดวันนี้
    elif "ปะยาง" in user_msg:
        numbers = re.findall(r'[\d,]+', user_msg)
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