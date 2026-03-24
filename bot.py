import os
import requests
import asyncio
import logging
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ================= الإعدادات الأساسية =================
TOKEN = "8685821581:AAEBPYLDm11al-zz9-szgx9QqkFWA8sKpZY"
API_KEY = "a33db71c29eda79b9ec098d2c337d619"
CHANNEL_USER = "@Ali1Sports" 
BASE_URL = "https://v3.football.api-sports.io"
headers = {"x-apisports-key": API_KEY}

# مخازن البيانات
user_data = {}
last_scores = {}

# إعداد السجلات (Logging)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ================= خادم Flask (لضمان عمل Render 24/7) =================
server = Flask('')

@server.route('/')
def home(): 
    return "⚽ LiveScore Bot is Online!"

def run_flask():
    # Render يمرر المنفذ تلقائياً عبر متغير PORT
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

# ================= الوظائف المساعدة =================
async def is_subscribed(app, user_id):
    """التحقق من وجود المستخدم في القناة"""
    try:
        member = await app.bot.get_chat_member(chat_id=CHANNEL_USER, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

def get_live_scores():
    """جلب المباريات المباشرة من الـ API"""
    try:
        r = requests.get(f"{BASE_URL}/fixtures?live=all", headers=headers, timeout=10).json()
        if not r.get("response"): return "⚠️ لا توجد مباريات مباشرة حالياً."
        
        text = "🔴 **النتائج المباشرة الآن:**\n\n"
        for m in r["response"][:10]:
            home = m["teams"]["home"]["name"]
            away = m["teams"]["away"]["name"]
            gh = m["goals"]["home"]
            ga = m["goals"]["away"]
            text += f"• {home}  `{gh} - {ga}`  {away}\n"
        return text
    except:
        return "❌ خطأ في الاتصال بالسيرفر."

def get_standings(league_id):
    """جلب جدول الترتيب لدوري معين"""
    try:
        # ملاحظة: تم استخدام موسم 2025 لجلب أحدث بيانات متوفرة
        r = requests.get(f"{BASE_URL}/standings?league={league_id}&season=2025", headers=headers, timeout=10).json()
        if not r.get("response"):
            # محاولة مع موسم 2024 في حال لم يبدأ 2025 بعد لبعض الدوريات
            r = requests.get(f"{BASE_URL}/standings?league={league_id}&season=2024", headers=headers, timeout=10).json()
            
        standings = r["response"][0]["league"]["standings"][0]
        league_name = r["response"][0]["league"]["name"]
        
        text = f"📊 **ترتيب {league_name}:**\n\n"
        for t in standings[:10]:
            text += f"{t['rank']}. {t['team']['name']} - {t['points']}ن\n"
        return text
    except:
        return "⚠️ البيانات غير متوفرة لهذا الدوري حالياً."

# ================= التعامل مع الأوامر والأزرار =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # فحص الاشتراك الإجباري
    if not await is_subscribed(context.application, user_id):
        keyboard = [
            [InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{CHANNEL_USER[1:]}")],
            [InlineKeyboardButton("✅ تم الاشتراك، ابدأ الآن", callback_data="check_sub")]
        ]
        await update.message.reply_text(
            f"⚠️ **تنبيه!**\n\nيجب عليك الاشتراك في القناة الرسمية أولاً لتتمكن من استخدام البوت:\n{CHANNEL_USER}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # القائمة الرئيسية
    keyboard = [
        [InlineKeyboardButton("🔴 المباريات المباشرة", callback_data="live")],
        [InlineKeyboardButton("📊 الدوريات العالمية", callback_data="leagues")],
        [InlineKeyboardButton("🏆 اختيار فريقك المفضل", callback_data="teams")]
    ]
    await update.message.reply_text(
        "⚽ **أهلاً بك في LiveScore PRO**\n\nتابع نتائج فريقك المفضل وجداول الترتيب لحظة بلحظة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    await query.answer()

    if data == "check_sub":
        if await is_subscribed(context.application, user_id):
            await query.message.delete()
            await start(update, context)
        else:
            await context.bot.send_message(chat_id=user_id, text="❌ لم تشترك بعد! اشترك ثم اضغط على الزر.")
        return

    if data == "live":
        await query.edit_message_text(get_live_scores(), parse_mode="Markdown")

    elif data == "leagues":
        keyboard = [
            [InlineKeyboardButton("🇬🇧 إنجلترا", callback_data="league_39"), InlineKeyboardButton("🇪🇸 إسبانيا", callback_data="league_140")],
            [InlineKeyboardButton("🇮🇹 إيطاليا", callback_data="league_135"), InlineKeyboardButton("🇩🇪 ألمانيا", callback_data="league_78")],
            [InlineKeyboardButton("🏆 دوري الأبطال", callback_data="league_2"), InlineKeyboardButton("🇪🇺 الدوري الأوروبي", callback_data="league_3")],
            [InlineKeyboardButton("🇸🇦 السعودية", callback_data="league_307"), InlineKeyboardButton("🇦🇪 الإمارات", callback_data="league_301")],
            [InlineKeyboardButton("🇪🇬 مصر", callback_data="league_233"), InlineKeyboardButton("🇲🇦 المغرب", callback_data="league_200")],
            [InlineKeyboardButton("🇮🇶 العراق", callback_data="league_268"), InlineKeyboardButton("🇶🇦 قطر", callback_data="league_305")],
            [InlineKeyboardButton("🌏 أبطال آسيا", callback_data="league_17"), InlineKeyboardButton("🌍 أبطال أفريقيا", callback_data="league_12")],
            [InlineKeyboardButton("🇫🇷 فرنسا", callback_data="league_61"), InlineKeyboardButton("🇵🇹 البرتغال", callback_data="league_94")],
            [InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="back_main")]
        ]
        await query.edit_message_text("📊 **اختر البطولة لعرض الترتيب:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "back_main":
        await query.message.delete()
        await start(update, context)

    elif data == "teams":
        keyboard = [
            [InlineKeyboardButton("🇪🇸 ريال مدريد", callback_data="team_real madrid")],
            [InlineKeyboardButton("🔵 برشلونة", callback_data="team_barcelona")],
            [InlineKeyboardButton("🔙 العودة", callback_data="back_main")]
        ]
        await query.edit_message_text("🏆 اختر فريقك المفضل لتلقي تنبيهات الأهداف:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("team_"):
        team_name = data.replace("team_", "")
        user_data[user_id] = {"team": team_name}
        await query.edit_message_text(f"✅ تم تفعيل التنبيهات لـ: **{team_name}**", parse_mode="Markdown")

    elif data.startswith("league_"):
        l_id = data.replace("league_", "")
        await query.edit_message_text(get_standings(l_id), parse_mode="Markdown")

# ================= محرك الأهداف (يعمل في الخلفية) =================
async def goal_engine(app):
    global last_scores
    while True:
        try:
            r = requests.get(f"{BASE_URL}/fixtures?live=all", headers=headers, timeout=10).json()
            for m in r.get("response", []):
                m_id = m["fixture"]["id"]
                score = f"{m['goals']['home']}-{m['goals']['away']}"
                h_name, a_name = m["teams"]["home"]["name"], m["teams"]["away"]["name"]

                if m_id in last_scores and last_scores[m_id] != score:
                    for uid, info in user_data.items():
                        fav = info.get("team", "").lower()
                        if fav in h_name.lower() or fav in a_name.lower():
                            await app.bot.send_message(chat_id=uid, text=f"⚽ **هدف جديد!!**\n\n{h_name}  `{score}`  {a_name}", parse_mode="Markdown")
                last_scores[m_id] = score
        except:
            pass
        await asyncio.sleep(45)

# ================= التشغيل الرئيسي =================
if __name__ == "__main__":
    # تشغيل Flask
    Thread(target=run_flask).start()
    
    # بناء التطبيق
    bot_app = ApplicationBuilder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(button_handler))
    
    # تشغيل محرك الأهداف
    loop = asyncio.get_event_loop()
    loop.create_task(goal_engine(bot_app))
    
    print("--- Bot Started Successfully ---")
    bot_app.run_polling()
