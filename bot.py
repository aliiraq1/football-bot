import os
import requests
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ================= الإعدادات الأساسية =================
# ضع التوكن الخاص بك هنا (من BotFather)
TOKEN = "8685821581:AAEBPYLDm11al-zz9-szgx9QqkFWA8sKpZY"
# ضع مفتاح API Football الخاص بك هنا
API_KEY = "a33db71c29eda79b9ec098d2c337d619"
# معرف القناة
CHANNEL_USER = "@Ali1Sports" 

BASE_URL = "https://v3.football.api-sports.io"
headers = {"x-apisports-key": API_KEY}

# معرفات الدوريات الكبرى
MAJOR_LEAGUES = [39, 140, 135, 78, 61, 2, 3, 17, 307, 268]

last_scores = {}
sent_lineups = set()
morning_sent = False
last_checked_day = ""

# ================= خادم Flask لجعل ريندر يعمل =================
server = Flask('')
@server.route('/')
def home(): return "⚽ Ali1Sports PRO is Online & Ready!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

# ================= وظائف جلب البيانات =================

def get_lineups_and_injuries(fixture_id):
    try:
        lineup_res = requests.get(f"{BASE_URL}/fixtures/lineups?fixture={fixture_id}", headers=headers, timeout=10).json()
        injuries_res = requests.get(f"{BASE_URL}/injuries?fixture={fixture_id}", headers=headers, timeout=10).json()
        
        text = ""
        if lineup_res.get("response"):
            for team in lineup_res["response"]:
                text += f"👤 **تشكيلة {team['team']['name']} ({team['formation']}):**\n"
                for player in team['startXI']:
                    text += f"• {player['player']['name']} ({player['player']['pos']})\n"
                text += "\n"
        
        if injuries_res.get("response"):
            text += "🚑 **الغيابات المؤكدة:**\n"
            for inj in injuries_res["response"][:10]:
                text += f"• {inj['player']['name']} ({inj['team']['name']}) - {inj['player']['type']}\n"
        
        return text if text else None
    except: return None

def get_daily_fixtures():
    try:
        # توقيت العراق/السعودية
        now_iq = datetime.now(timezone.utc) + timedelta(hours=3)
        today = now_iq.strftime('%Y-%m-%d')
        text = f"📅 **أهم مباريات اليوم ({today})**\n━━━━━━━━━━━━━━\n\n"
        
        found = False
        for league_id in MAJOR_LEAGUES:
            r = requests.get(f"{BASE_URL}/fixtures?date={today}&league={league_id}&season=2024", headers=headers, timeout=10).json()
            if r.get("response"):
                found = True
                text += f"🏆 **{r['response'][0]['league']['name']}**\n"
                for m in r["response"][:5]:
                    # تحويل وقت المباراة لتوقيت العراق
                    utc_dt = datetime.fromisoformat(m['fixture']['date'].replace('Z', '+00:00'))
                    iq_dt = utc_dt + timedelta(hours=3)
                    text += f"⏰ {iq_dt.strftime('%I:%M %p')} | {m['teams']['home']['name']} 🆚 {m['teams']['away']['name']}\n"
                text += " \n"
        return text if found else "⚠️ لا توجد مباريات كبرى مجدولة اليوم."
    except Exception as e:
        return f"❌ خطأ في جلب البيانات: {e}"

# ================= المحرك الرئيسي الذكي =================

async def main_engine(app):
    global last_scores, sent_lineups, morning_sent, last_checked_day
    
    while True:
        try:
            # الحصول على الوقت الحالي (العراق/السعودية)
            now_iq = datetime.now(timezone.utc) + timedelta(hours=3)
            current_day = now_iq.strftime('%Y-%m-%d')

            # إعادة تصفير الإرسال والذاكرة عند تغير اليوم
            if current_day != last_checked_day:
                morning_sent = False
                last_checked_day = current_day
                sent_lineups.clear()
                last_scores.clear()
                print(f"--- يوم جديد: {current_day} - تم تصفير الذاكرة ---")

            # 1. إرسال الجدول اليومي (عند الساعة 12 ظهراً)
            if now_iq.hour == 12 and not morning_sent:
                print("--- إرسال جدول المباريات الآن ---")
                await app.bot.send_message(chat_id=CHANNEL_USER, text=get_daily_fixtures(), parse_mode="Markdown")
                morning_sent = True

            # 2. فحص الأهداف والتشكيلات الحية
            r = requests.get(f"{BASE_URL}/fixtures?date={current_day}", headers=headers, timeout=10).json()
            
            if r.get("response"):
                for m in r["response"]:
                    f_id = m["fixture"]["id"]
                    if m["league"]["id"] in MAJOR_LEAGUES:
                        status = m["fixture"]["status"]["short"]
                        
                        # التشكيلة الرسمية (قبل المباراة بـ 40 دقيقة)
                        if status == "NS" and f_id not in sent_lineups:
                            match_time = datetime.fromisoformat(m['fixture']['date'].replace('Z', '+00:00'))
                            time_diff = (match_time - datetime.now(timezone.utc)).total_seconds() / 60
                            if 0 < time_diff <= 45:
                                info = get_lineups_and_injuries(f_id)
                                if info:
                                    msg = f"📋 **التشكيلة الرسمية**\n⚽ {m['teams']['home']['name']} 🆚 {m['teams']['away']['name']}\n\n" + info
                                    await app.bot.send_message(chat_id=CHANNEL_USER, text=msg, parse_mode="Markdown")
                                    sent_lineups.add(f_id)

                        # تنبيه الأهداف الحية
                        if status in ["1H", "2H", "ET", "P"]:
                            score = f"{m['goals']['home']} - {m['goals']['away']}"
                            if f_id in last_scores and last_scores[f_id] != score:
                                goal_msg = (
                                    f"GOOOOAL !! 🥅⚽️\n\n"
                                    f"🔥 **تغير في النتيجة**\n"
                                    f"━━━━━━━━━━━━\n"
                                    f"🏠 {m['teams']['home']['name']}\n"
                                    f"  【 {score} 】 \n"
                                    f"🚌 {m['teams']['away']['name']}\n"
                                    f"━━━━━━━━━━━━\n"
                                    f"🏆 {m['league']['name']}\n"
                                    f"📢 {CHANNEL_USER}"
                                )
                                await app.bot.send_message(chat_id=CHANNEL_USER, text=goal_msg, parse_mode="Markdown")
                            last_scores[f_id] = score
        except Exception as e:
            print(f"Engine Loop Error: {e}")
            
        await asyncio.sleep(60) # فحص كل دقيقة

# ================= التشغيل =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ البوت يعمل بنجاح ويراقب القناة حالياً.")

if __name__ == "__main__":
    # تشغيل Flask في خيط منفصل
    Thread(target=run_flask, daemon=True).start()
    
    # إعداد بوت تلجرام
    bot_app = ApplicationBuilder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    
    # ربط المحرك بالبوت
    async def setup_engine(application):
        asyncio.create_task(main_engine(application))

    bot_app.post_init = setup_engine
    print("--- Ali1Sports PRO Bot is Running (Fixed & Stable) ---")
    
    # تشغيل البوت (Polling)
    bot_app.run_polling(drop_pending_updates=True)
