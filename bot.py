import os
import requests
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from flask import Flask
from threading import Thread

# إعداد السجلات (Logging) لمتابعة الأخطاء على Render
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = "8685821581:AAEBPYLDm11al-zz9-szgx9QqkFWA8sKpZY"
API_KEY = "a33db71c29eda79b9ec098d2c337d619"

BASE_URL = "https://v3.football.api-sports.io"
headers = {"x-apisports-key": API_KEY}

user_data = {}
last_scores = {}

# --- Flask App لتجاوز إغلاق Render للمشروع ---
server = Flask('')

@server.route('/')
def home():
    return "Bot is Running!"

def run_flask():
    # Render يعطي منفذ تلقائي في المتغير PORT
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

# --- وظائف البوت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔴 المباريات المباشرة", callback_data="live")],
        [InlineKeyboardButton("🏆 اختيار فريق", callback_data="teams")],
        [InlineKeyboardButton("📊 الدوريات", callback_data="leagues")]
    ]
    await update.message.reply_text(
        "⚽ مرحباً بك في بوت LiveScore PRO MAX",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.message.chat_id
    data = query.data

    if data == "live":
        await query.edit_message_text(get_live())
    elif data == "teams":
        keyboard = [
            [InlineKeyboardButton("🇪🇸 ريال مدريد", callback_data="team_real madrid")],
            [InlineKeyboardButton("🔵 برشلونة", callback_data="team_barcelona")],
            [InlineKeyboardButton("🔴 مانشستر يونايتد", callback_data="team_man united")]
        ]
        await query.edit_message_text("اختر فريقك 👇", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "leagues":
        keyboard = [
            [InlineKeyboardButton("🇬🇧 إنجلترا", callback_data="league_39")],
            [InlineKeyboardButton("🇪🇸 إسبانيا", callback_data="league_140")],
            [InlineKeyboardButton("🇮🇹 إيطاليا", callback_data="league_135")],
            [InlineKeyboardButton("🏆 دوري الأبطال", callback_data="league_2")],
            [InlineKeyboardButton("🇸🇦 السعودية", callback_data="league_307")]
        ]
        await query.edit_message_text("🏆 اختر البطولة:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("team_"):
        team = data.replace("team_", "")
        user_data[user_id] = {"team": team}
        await query.edit_message_text(f"✅ تم اختيار فريقك: {team}")
    elif data.startswith("league_"):
        league = data.replace("league_", "")
        await query.edit_message_text(get_standings(league))

def get_live():
    try:
        url = f"{BASE_URL}/fixtures?live=all"
        r = requests.get(url, headers=headers, timeout=10).json()
        if not r.get("response"): return "⚠️ لا توجد مباريات حالياً"
        text = "🔴 المباريات المباشرة:\n\n"
        for m in r["response"][:8]:
            home = m["teams"]["home"]["name"]; away = m["teams"]["away"]["name"]
            hg = m["goals"]["home"]; ag = m["goals"]["away"]
            text += f"{home} {hg} - {ag} {away}\n"
        return text
    except: return "❌ خطأ في الاتصال بالبيانات"

def get_standings(league):
    try:
        url = f"{BASE_URL}/standings?league={league}&season=2024"
        r = requests.get(url, headers=headers, timeout=10).json()
        table = r["response"][0]["league"]["standings"][0]
        text = "📊 الترتيب:\n\n"
        for t in table[:10]:
            text += f"{t['rank']}. {t['team']['name']} - {t['points']}ن\n"
        return text
    except: return "⚠️ لا توجد بيانات حالياً"

async def goal_engine(app):
    global last_scores
    while True:
        try:
            url = f"{BASE_URL}/fixtures?live=all"
            r = requests.get(url, headers=headers, timeout=10).json()
            for m in r.get("response", []):
                match_id = m["fixture"]["id"]
                score = f"{m['goals']['home']}-{m['goals']['away']}"
                home = m["teams"]["home"]["name"]
                away = m["teams"]["away"]["name"]

                if match_id in last_scores and last_scores[match_id] != score:
                    for user_id, data in user_data.items():
                        team = data.get("team", "")
                        if team.lower() in home.lower() or team.lower() in away.lower():
                            await app.bot.send_message(chat_id=user_id, text=f"⚽ GOAL!\n{home} {score} {away}")
                last_scores[match_id] = score
        except Exception as e:
            logging.error(f"Error in engine: {e}")
        await asyncio.sleep(30) # زيادة الوقت قليلاً لتجنب الحظر من API

# --- تشغيل البوت ---
if __name__ == "__main__":
    # تشغيل Flask في خلفية منفصلة
    Thread(target=run_flask).start()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))

    # إضافة مهمة فحص الأهداف للحلقة (Loop)
    loop = asyncio.get_event_loop()
    loop.create_task(goal_engine(app))
    
    print("Bot is starting...")
    app.run_polling()
