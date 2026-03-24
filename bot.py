import os
import requests
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ================= 1. الإعدادات الأساسية =================
TOKEN = "8685821581:AAEBPYLDm11al-zz9-szgx9QqkFWA8sKpZY"  # ضع توكن البوت هنا
API_KEY = "a33db71c29eda79b9ec098d2c337d619"  # ضع مفتاح API هنا
CHANNEL_USER = "@Ali1Sports"       # معرف القناة

BASE_URL = "https://v3.football.api-sports.io"
headers = {"x-apisports-key": API_KEY}

# تحديد الموسم الحالي ديناميكياً (2025/2026)
CURRENT_SEASON = str(datetime.now().year if datetime.now().month > 6 else datetime.now().year - 1)

MAJOR_LEAGUES = {
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 الدوري الإنجليزي": 39,
    "🇪🇸 الدوري الإسباني": 140,
    "🇩🇪 الدوري الألماني": 78,
    "🇮🇹 الدوري الإيطالي": 135,
    "🇫🇷 الدوري الفرنسي": 61
}

# الذاكرة المؤقتة (تصفّر عند إعادة تشغيل السيرفر)
user_favorites = {} 
last_scores = {}
morning_sent = False
last_checked_day = ""

# ================= 2. خادم Flask (لضمان عمل Render) =================
server = Flask('')
@server.route('/')
def home(): return "⚽ Ali1Sports PRO System is Fully Online!"

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
            r = requests.get(f"{BASE_URL}/fixtures?date={today}&league={l_id}&season={CURRENT_SEASON}", headers=headers, timeout=10).json()
            if r.get("response"):
                found = True
                text += f"🏆 **{l_name}**\n"
                for m in r["response"]:
                    home, away = m['teams']['home']['name'], m['teams']['away']['name']
                    utc_dt = datetime.fromisoformat(m['fixture']['date'].replace('Z', '+00:00'))
                    iq_time = (utc_dt + timedelta(hours=3)).strftime('%I:%M %p')
                    text += f"🏠 **الأرض:** {home}\n🚌 **الزائر:** {away}\n⏰ **الوقت:** {iq_time}\n"
                text += "----------- \n"
        return text if found else "📭 لا توجد مباريات كبرى اليوم."
    except: return "❌ خطأ في جلب المواعيد."

def get_standings(league_id):
    try:
        r = requests.get(f"{BASE_URL}/standings?league={league_id}&season={CURRENT_SEASON}", headers=headers).json()
        if not r.get("response") or not r["response"][0]["league"].get("standings"):
            return "⚠️ لا توجد بيانات ترتيب حالياً لهذا الموسم."
        st = r["response"][0]["league"]["standings"][0]
        text = f"📊 **ترتيب الدوري (أول 10):**\n\n"
        for t in st[:10]:
            text += f"{t['rank']}. {t['team']['name']} - {t['points']}ن\n"
        return text
    except: return "❌ خطأ في الجلب."

def get_top_scorers(league_id):
    try:
        r = requests.get(f"{BASE_URL}/players/topscorers?league={league_id}&season={CURRENT_SEASON}", headers=headers).json()
        if not r.get("response"): return "⚠️ لا توجد بيانات هدافين حالياً."
        text = "⚽ **قائمة الهدافين:**\n\n"
        for p in r["response"][:7]:
            name = p['player']['name']
            goals = p['statistics'][0]['goals']['total']
            team = p['statistics'][0]['team']['name']
            text += f"👤 {name} ({team}) - ⚽ {goals}\n"
        return text
    except: return "❌ خطأ في جلب الهدافين."

def get_teams_by_league(league_id):
    try:
        r = requests.get(f"{BASE_URL}/teams?league={league_id}&season={CURRENT_SEASON}", headers=headers).json()
        teams = r.get("response", [])
        keyboard, row = [], []
        for t in teams:
            t_name, t_id = t['team']['name'], t['team']['id']
            row.append(InlineKeyboardButton(t_name, callback_data=f"save_{t_id}_{t_name}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        return keyboard
    except: return []

# ================= 4. معالجة التفاعل (الخاص) =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    fav_name = context.user_data.get('fav_team_name', "لا يوجد")
    keyboard = [
        [InlineKeyboardButton("📅 مواعيد المباريات", callback_data='btn_fixtures')],
        [InlineKeyboardButton("📊 نتائج مباشرة", callback_data='btn_live')],
        [InlineKeyboardButton("🏆 الترتيب", callback_data='nav_std'), InlineKeyboardButton("🔥 الهدافين", callback_data='nav_scr')],
        [InlineKeyboardButton("⭐ اختر فريقك المفضل", callback_data='nav_fav')],
    ]
    if user_id in user_favorites:
        keyboard.append([InlineKeyboardButton(f"❌ إلغاء متابعة {fav_name}", callback_data='btn_unfav')])
    
    keyboard.append([InlineKeyboardButton("📢 القناة الرسمية", url=f"https://t.me/{CHANNEL_USER[1:]}")])
    msg = f"⚽ **Ali1Sports PRO**\n🌟 فريقك الحالي: **{fav_name}**\n\nاختر من القائمة:"
    
    if update.message: await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else: await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()
    
    if data == 'btn_fixtures':
        await query.edit_message_text(get_detailed_fixtures(), parse_mode="Markdown", reply_markup=back_kb())
    
    elif data == 'btn_live':
        r = requests.get(f"{BASE_URL}/fixtures?live=all", headers=headers).json()
        res = "🏟️ **النتائج الحية:**\n\n" + "\n".join([f"⚽ {m['teams']['home']['name']} {m['goals']['home']}-{m['goals']['away']} {m['teams']['away']['name']}" for m in r.get("response", [])[:10]])
        await query.edit_message_text(res if "home" in res else "📭 لا توجد مباريات مباشرة حالياً.", reply_markup=back_kb())
    
    elif data in ['nav_std', 'nav_scr', 'nav_fav']:
        prefix = "getstd_" if data == 'nav_std' else "getscr_" if data == 'nav_scr' else "favl_"
        kb = [[InlineKeyboardButton(name, callback_data=f"{prefix}{id}")] for name, id in MAJOR_LEAGUES.items()]
        kb.append([InlineKeyboardButton("⬅️ عودة", callback_data='back_main')])
        await query.edit_message_text("اختر الدوري المطلوب:", reply_markup=InlineKeyboardMarkup(kb))
    
    elif data.startswith('favl_'):
        l_id = data.split('_')[1]
        kb = get_teams_by_league(l_id)
        kb.append([InlineKeyboardButton("⬅️ عودة", callback_data='nav_fav')])
        await query.edit_message_text("اختر فريقك من القائمة:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith('getstd_'):
        l_id = data.split('_')[1]
        await query.edit_message_text(get_standings(l_id), parse_mode="Markdown", reply_markup=back_kb())

    elif data.startswith('getscr_'):
        l_id = data.split('_')[1]
        await query.edit_message_text(get_top_scorers(l_id), parse_mode="Markdown", reply_markup=back_kb())

    elif data.startswith('save_'):
        _, t_id, t_name = data.split('_')
        user_favorites[query.from_user.id] = int(t_id)
        context.user_data['fav_team_name'] = t_name
        await query.edit_message_text(f"✅ تم حفظ **{t_name}** كفريقك المفضل!", reply_markup=back_kb())

    elif data == 'btn_unfav':
        user_favorites.pop(query.from_user.id, None)
        context.user_data['fav_team_name'] = "لا يوجد"
        await start(update, context)
    
    elif data == 'back_main': await start(update, context)

def back_kb(): return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data='back_main')]])

# ================= 5. المحرك التلقائي للقناة والتنبيهات =================

async def main_engine(app):
    global last_scores, morning_sent, last_checked_day
    while True:
        try:
            now_iq = datetime.now(timezone.utc) + timedelta(hours=3)
            today = now_iq.strftime('%Y-%m-%d')
            if today != last_checked_day: morning_sent, last_checked_day = False, today
            
            # إرسال جدول الصباح
            if now_iq.hour == 12 and not morning_sent:
                await app.bot.send_message(chat_id=CHANNEL_USER, text=get_detailed_fixtures(), parse_mode="Markdown")
                morning_sent = True

            # فحص الأهداف
            r = requests.get(f"{BASE_URL}/fixtures?live=all", headers=headers, timeout=10).json()
            for m in r.get("response", []):
                f_id, score = m["fixture"]["id"], f"{m['goals']['home']}-{m['goals']['away']}"
                if f_id in last_scores and last_scores[f_id] != score:
                    # القناة
                    await app.bot.send_message(chat_id=CHANNEL_USER, text=f"⚽ هدف!! {m['teams']['home']['name']} {score} {m['teams']['away']['name']}")
                    # التنبيه الخاص
                    h_id, a_id = m['teams']['home']['id'], m['teams']['away']['id']
                    for u_id, fav_id in user_favorites.items():
                        if fav_id in [h_id, a_id]: await app.bot.send_message(chat_id=u_id, text=f"⭐ فريقك سجل/استقبل هدفاً!\nالنتيجة: {score}")
                last_scores[f_id] = score
        except: pass
        await asyncio.sleep(60)

# ================= 6. التشغيل =================
if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot_app = ApplicationBuilder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(callback_handler))
    
    async def setup(application): asyncio.create_task(main_engine(application))
    bot_app.post_init = setup
    
    print("--- Ali1Sports PRO System is Running ---")
    bot_app.run_polling(drop_pending_updates=True)
