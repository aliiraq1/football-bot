import os
import requests
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ================= 1. الإعدادات الأساسية =================
TOKEN = "8685821581:AAEBPYLDm11al-zz9-szgx9QqkFWA8sKpZY"  # ضع توكن البوت هنا
API_KEY = "a33db71c29eda79b9ec098d2c337d619"  # ضع مفتاح API هنا
CHANNEL_USER = "@Ali1Sports"       # معرف القناة

BASE_URL = "https://v3.football.api-sports.io"
headers = {"x-apisports-key": API_KEY}

# الدوريات الكبرى المدعومة
MAJOR_LEAGUES = {
    "الدوري الإنجليزي": 39,
    "الدوري الإسباني": 140,
    "الدوري الألماني": 78,
    "الدوري الإيطالي": 135,
    "الدوري الفرنسي": 61
}
LEAGUE_IDS_LIST = list(MAJOR_LEAGUES.values())

# الذاكرة المؤقتة
user_favorites = {} # {user_id: team_id}
last_scores = {}
sent_lineups = set()
morning_sent = False
last_checked_day = ""

# ================= 2. خادم Flask (لضمان عمل الاستضافة) =================
server = Flask('')
@server.route('/')
def home(): return "⚽ Ali1Sports System is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

# ================= 3. وظائف جلب البيانات من API =================

def get_detailed_fixtures():
    try:
        now_iq = datetime.now(timezone.utc) + timedelta(hours=3)
        today = now_iq.strftime('%Y-%m-%d')
        text = f"📅 **مباريات اليوم ({today})**\n━━━━━━━━━━━━━━\n\n"
        
        found = False
        for l_name, l_id in MAJOR_LEAGUES.items():
            r = requests.get(f"{BASE_URL}/fixtures?date={today}&league={l_id}&season=2024", headers=headers, timeout=10).json()
            if r.get("response"):
                found = True
                text += f"🏆 **{l_name}**\n"
                for m in r["response"]:
                    home = m['teams']['home']['name']
                    away = m['teams']['away']['name']
                    utc_dt = datetime.fromisoformat(m['fixture']['date'].replace('Z', '+00:00'))
                    iq_time = (utc_dt + timedelta(hours=3)).strftime('%I:%M %p')
                    
                    text += f"🏠 **الأرض:** {home}\n"
                    text += f"🚌 **الزائر:** {away}\n"
                    text += f"⏰ **الوقت:** {iq_time}\n"
                    text += "----------- \n"
        return text if found else "📭 لا توجد مباريات كبرى اليوم."
    except: return "❌ خطأ في جلب المواعيد."

def get_standings(league_id):
    try:
        r = requests.get(f"{BASE_URL}/standings?league={league_id}&season=2024", headers=headers).json()
        if not r.get("response"): return "⚠️ لا توجد بيانات حالياً."
        st = r["response"][0]["league"]["standings"][0]
        text = f"📊 **ترتيب الدوري:**\n\n"
        for t in st[:10]:
            text += f"{t['rank']}. {t['team']['name']} - {t['points']}ن\n"
        return text
    except: return "❌ خطأ في الجلب."

def get_top_scorers(league_id):
    try:
        r = requests.get(f"{BASE_URL}/players/topscorers?league={league_id}&season=2024", headers=headers).json()
        if not r.get("response"): return "⚠️ لا توجد بيانات."
        text = f"⚽ **قائمة الهدافين:**\n\n"
        for p in r["response"][:5]:
            text += f"👤 {p['player']['name']} - ⚽ {p['statistics'][0]['goals']['total']}\n"
        return text
    except: return "❌ خطأ."

def get_live_scores():
    try:
        r = requests.get(f"{BASE_URL}/fixtures?live=all", headers=headers).json()
        if not r.get("response"): return "📭 لا توجد مباريات مباشرة الآن."
        text = "🏟️ **النتائج الحية:**\n\n"
        for m in r["response"][:10]:
            text += f"⚽ {m['teams']['home']['name']} {m['goals']['home']} - {m['goals']['away']} {m['teams']['away']['name']} ({m['fixture']['status']['elapsed']}')\n"
        return text
    except: return "❌ خطأ."

# ================= 4. معالجة التفاعل مع المستخدم (الخاص) =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    fav_name = context.user_data.get('fav_team_name', "لا يوجد")
    
    keyboard = [
        [InlineKeyboardButton("📅 مواعيد المباريات", callback_data='btn_fixtures')],
        [InlineKeyboardButton("📊 نتائج مباشرة", callback_data='btn_live')],
        [InlineKeyboardButton("🏆 الترتيب", callback_data='menu_standings'), InlineKeyboardButton("🔥 الهدافين", callback_data='menu_scorers')],
        [InlineKeyboardButton("⭐ فريقك المفضل", callback_data='btn_fav_setup')],
    ]
    
    if user_id in user_favorites:
        keyboard.append([InlineKeyboardButton(f"❌ إلغاء متابعة {fav_name}", callback_data='btn_unfav')])
    
    keyboard.append([InlineKeyboardButton("📢 القناة الرسمية", url=f"https://t.me/{CHANNEL_USER[1:]}")])
    
    msg = f"⚽ **مرحباً بك في Ali1Sports**\n🌟 فريقك المفضل: {fav_name}\n\nاختر من القائمة:"
    if update.message: await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else: await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'btn_fixtures':
        await query.edit_message_text(get_detailed_fixtures(), parse_mode="Markdown", reply_markup=back_menu())
    elif query.data == 'btn_live':
        await query.edit_message_text(get_live_scores(), parse_mode="Markdown", reply_markup=back_menu())
    elif query.data == 'menu_standings' or query.data == 'menu_scorers':
        type_ = "std" if "standings" in query.data else "scr"
        kb = [[InlineKeyboardButton(name, callback_data=f"{type_}_{id}")] for name, id in MAJOR_LEAGUES.items()]
        kb.append([InlineKeyboardButton("⬅️ عودة", callback_data='back_main')])
        await query.edit_message_text("اختر الدوري:", reply_markup=InlineKeyboardMarkup(kb))
    
    elif query.data.startswith(('std_', 'scr_')):
        parts = query.data.split('_')
        res = get_standings(parts[1]) if parts[0] == "std" else get_top_scorers(parts[1])
        await query.edit_message_text(res, parse_mode="Markdown", reply_markup=back_menu())

    elif query.data == 'btn_fav_setup':
        await query.edit_message_text("📝 أرسل اسم فريقك بالإنجليزية (مثال: Real Madrid):")
        context.user_data['waiting'] = True
    elif query.data == 'btn_unfav':
        user_favorites.pop(query.from_user.id, None)
        context.user_data['fav_team_name'] = "لا يوجد"
        await start(update, context)
    elif query.data == 'back_main':
        await start(update, context)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting'):
        name = update.message.text
        r = requests.get(f"{BASE_URL}/teams?search={name}", headers=headers).json()
        teams = r.get("response", [])
        if not teams:
            await update.message.reply_text("❌ لم أجد الفريق، حاول مرة أخرى.")
            return
        kb = [[InlineKeyboardButton(t['team']['name'], callback_data=f"save_{t['team']['id']}_{t['team']['name']}")] for t in teams[:5]]
        await update.message.reply_text("اختر الفريق بدقة:", reply_markup=InlineKeyboardMarkup(kb))
        context.user_data['waiting'] = False

async def save_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, t_id, t_name = query.data.split('_')
    user_favorites[query.from_user.id] = int(t_id)
    context.user_data['fav_team_name'] = t_name
    await query.edit_message_text(f"✅ تم حفظ {t_name} كفريقك المفضل!", reply_markup=back_menu())

def back_menu(): return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data='back_main')]])

# ================= 5. المحرك التلقائي (القناة + التنبيهات الخاصة) =================

async def main_engine(app):
    global last_scores, morning_sent, last_checked_day
    while True:
        try:
            now_iq = datetime.now(timezone.utc) + timedelta(hours=3)
            today = now_iq.strftime('%Y-%m-%d')

            if today != last_checked_day:
                morning_sent, last_checked_day = False, today
                last_scores.clear()

            # إرسال الجدول الساعة 12 ظهراً
            if now_iq.hour == 12 and not morning_sent:
                await app.bot.send_message(chat_id=CHANNEL_USER, text=get_detailed_fixtures(), parse_mode="Markdown")
                morning_sent = True

            # فحص الأهداف المباشرة
            r = requests.get(f"{BASE_URL}/fixtures?live=all", headers=headers, timeout=10).json()
            if r.get("response"):
                for m in r["response"]:
                    f_id, score = m["fixture"]["id"], f"{m['goals']['home']}-{m['goals']['away']}"
                    if f_id in last_scores and last_scores[f_id] != score:
                        # إشعار القناة
                        goal_text = f"⚽ هدف!! {m['teams']['home']['name']} {score} {m['teams']['away']['name']}"
                        await app.bot.send_message(chat_id=CHANNEL_USER, text=goal_text)
                        # إشعار الفريق المفضل
                        h_id, a_id = m['teams']['home']['id'], m['teams']['away']['id']
                        for u_id, fav_id in user_favorites.items():
                            if fav_id in [h_id, a_id]:
                                await app.bot.send_message(chat_id=u_id, text=f"⭐ فريقك سجل/استقبل هدفاً!\nالنتيجة: {score}")
                    last_scores[f_id] = score
        except: pass
        await asyncio.sleep(60)

# ================= 6. التشغيل النهائي =================

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot_app = ApplicationBuilder().token(TOKEN).build()
    
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(callback_handler, pattern='^(btn_|menu_|back_|std_|scr_)'))
    bot_app.add_handler(CallbackQueryHandler(save_team, pattern='^save_'))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    async def setup(application): asyncio.create_task(main_engine(application))
    bot_app.post_init = setup
    
    print("--- Ali1Sports PRO System is Running Successfully ---")
    bot_app.run_polling(drop_pending_updates=True)
