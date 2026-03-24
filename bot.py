import os
import requests
import asyncio
import threading
from datetime import datetime, timedelta, timezone
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ================= 1. الإعدادات الأساسية =================
TOKEN = "8685821581:AAEBPYLDm11al-zz9-szgx9QqkFWA8sKpZY"  # ضع توكن البوت هنا
API_KEY = "a33db71c29eda79b9ec098d2c337d619"  # ضع مفتاح API هنا
CHANNEL_USER = "@Ali1Sports"

BASE_URL = "https://v3.football.api-sports.io"
headers = {"x-apisports-key": API_KEY}
CURRENT_SEASON = "2025"

MAJOR_LEAGUES = {
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 الدوري الإنجليزي": 39,
    "🇪🇸 الدوري الإسباني": 140,
    "🇩🇪 الدوري الألماني": 78,
    "🇮🇹 الدوري الإيطالي": 135,
    "🇫🇷 الدوري الفرنسي": 61
}

# تخزين البيانات في الذاكرة (يفضل استخدام قاعدة بيانات مستقبلاً)
user_favorites = {}  
user_fav_names = {}  
last_scores = {}
morning_sent_date = ""

# ================= 2. خادم Flask (للبقاء حياً على Render) =================
server = Flask(__name__)

@server.route('/')
def home():
    return "✅ Ali1Sports PRO Bot is Running!", 200

@server.route('/health')
def health():
    return "OK", 200

def run_flask():
    # Render يستخدم المنفذ 10000 افتراضياً أو المتغير المحيطي PORT
    port = int(os.environ.get("PORT", 10000))
    server.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ================= 3. دوال جلب البيانات (كما هي مع تحسين طفيف) =================

def get_fixtures_today():
    try:
        now_iq = datetime.now(timezone.utc) + timedelta(hours=3)
        today = now_iq.strftime('%Y-%m-%d')
        all_matches = []
        for league_name, league_id in MAJOR_LEAGUES.items():
            params = {"league": league_id, "season": CURRENT_SEASON, "date": today}
            r = requests.get(f"{BASE_URL}/fixtures", headers=headers, params=params, timeout=10)
            data = r.json()
            if data.get("response"):
                for m in data["response"]:
                    all_matches.append({
                        "league": league_name,
                        "home": m['teams']['home']['name'],
                        "away": m['teams']['away']['name'],
                        "time": m['fixture']['date']
                    })
        
        if not all_matches: return "📭 لا توجد مباريات كبرى اليوم."
        
        all_matches.sort(key=lambda x: x['time'])
        text = f"📅 **مباريات اليوم ({today})**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for m in all_matches:
            utc_dt = datetime.fromisoformat(m['time'].replace('Z', '+00:00'))
            iq_time = (utc_dt + timedelta(hours=3)).strftime('%I:%M %p')
            text += f"🏆 **{m['league']}**\n🏠 {m['home']} 🆚 {m['away']}\n⏰ {iq_time}\n" + "➖➖➖➖➖➖➖➖➖\n\n"
        return text
    except Exception as e:
        return f"❌ خطأ: {e}"

def get_standings(league_id):
    try:
        params = {"league": league_id, "season": CURRENT_SEASON}
        r = requests.get(f"{BASE_URL}/standings", headers=headers, params=params, timeout=10)
        data = r.json()
        if not data.get("response"): return "⚠️ لا توجد بيانات."
        standings = data["response"][0]["league"]["standings"][0]
        text = "🏆 **جدول الترتيب**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, team in enumerate(standings[:10], 1):
            text += f"{i}. {team['team']['name']}\n    🎯 {team['points']} نقطة\n\n"
        return text
    except: return "❌ فشل جلب الترتيب."

def get_scorers(league_id):
    try:
        params = {"league": league_id, "season": CURRENT_SEASON}
        r = requests.get(f"{BASE_URL}/players/topscorers", headers=headers, params=params, timeout=10)
        data = r.json()
        if not data.get("response"): return "⚠️ لا توجد بيانات."
        text = "🔥 **قائمة الهدافين**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, p in enumerate(data["response"][:10], 1):
            text += f"{i}. ⚽ {p['player']['name']} ({p['statistics'][0]['goals']['total']})\n"
        return text
    except: return "❌ فشل جلب الهدافين."

def get_live_scores():
    try:
        params = {"live": "all"}
        r = requests.get(f"{BASE_URL}/fixtures", headers=headers, params=params, timeout=10)
        matches = r.json().get("response", [])
        if not matches: return "📭 لا توجد مباريات مباشرة الآن."
        text = "🏟️ **المباريات الجارية**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for m in matches[:10]:
            text += f"⚽ {m['teams']['home']['name']} {m['goals']['home']}-{m['goals']['away']} {m['teams']['away']['name']}\n⏱️ الدقيقة {m['fixture']['status']['elapsed']}\n➖➖➖➖➖➖➖\n\n"
        return text
    except: return "❌ خطأ في جلب النتائج."

def get_teams_kb(league_id):
    try:
        params = {"league": league_id, "season": CURRENT_SEASON}
        r = requests.get(f"{BASE_URL}/teams", headers=headers, params=params, timeout=10)
        teams = r.json().get("response", [])
        keyboard = []
        row = []
        for team in sorted(teams, key=lambda x: x['team']['name'])[:20]:
            btn = InlineKeyboardButton(team['team']['name'][:20], callback_data=f"savef_{team['team']['id']}_{team['team']['name']}")
            row.append(btn)
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        return keyboard
    except: return None

# ================= 4. أوامر البوت والمعالجات =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    fav_name = user_fav_names.get(user_id, "لم يتم الاختيار")
    
    keyboard = [
        [InlineKeyboardButton("📅 مباريات اليوم", callback_data='btn_fix')],
        [InlineKeyboardButton("🏆 جدول الترتيب", callback_data='nav_std'), InlineKeyboardButton("🔥 الهدافين", callback_data='nav_scr')],
        [InlineKeyboardButton("⭐ اختيار فريق مفضل", callback_data='nav_fav_list')],
        [InlineKeyboardButton("📊 نتائج مباشرة", callback_data='btn_live')]
    ]
    if user_id in user_favorites:
        keyboard.append([InlineKeyboardButton(f"❌ إلغاء متابعة {fav_name}", callback_data='btn_unfav')])
    
    keyboard.append([InlineKeyboardButton("📢 قناة البوت", url=f"https://t.me/{CHANNEL_USER[1:]}")])
    
    msg = f"⚽ **Ali1Sports PRO**\n🌟 فريقك المفضل: **{fav_name}**\n\nاختر من القائمة:"
    
    if update.message:
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    await query.answer()
    
    if data == 'btn_fix':
        await query.edit_message_text(get_fixtures_today(), parse_mode="Markdown", reply_markup=back_kb())
    elif data == 'btn_live':
        await query.edit_message_text(get_live_scores(), parse_mode="Markdown", reply_markup=back_kb())
    elif data in ['nav_std', 'nav_scr', 'nav_fav_list']:
        prefix = "getstd_" if data == 'nav_std' else "getscr_" if data == 'nav_scr' else "listf_"
        kb = [[InlineKeyboardButton(name, callback_data=f"{prefix}{lid}")] for name, lid in MAJOR_LEAGUES.items()]
        kb.append([InlineKeyboardButton("⬅️ رجوع", callback_data='main_menu')])
        await query.edit_message_text("🏆 اختر الدوري:", reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith('listf_'):
        kb = get_teams_kb(data.split('_')[1])
        if kb:
            kb.append([InlineKeyboardButton("⬅️ رجوع", callback_data='nav_fav_list')])
            await query.edit_message_text("⭐ اختر فريقك المفضل:", reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith('getstd_'):
        await query.edit_message_text(get_standings(data.split('_')[1]), parse_mode="Markdown", reply_markup=back_kb())
    elif data.startswith('getscr_'):
        await query.edit_message_text(get_scorers(data.split('_')[1]), parse_mode="Markdown", reply_markup=back_kb())
    elif data.startswith('savef_'):
        parts = data.split('_', 2)
        user_favorites[user_id], user_fav_names[user_id] = int(parts[1]), parts[2]
        await query.edit_message_text(f"✅ تم حفظ **{parts[2]}** كفريقك المفضل!", parse_mode="Markdown", reply_markup=back_kb())
    elif data == 'btn_unfav':
        user_favorites.pop(user_id, None)
        user_fav_names[user_id] = "لا يوجد"
        await start(update, context)
    elif data == 'main_menu':
        await start(update, context)

def back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data='main_menu')]])

# ================= 5. المحرك التلقائي =================

async def auto_engine(application: Application):
    global last_scores, morning_sent_date
    while True:
        try:
            now_iq = datetime.now(timezone.utc) + timedelta(hours=3)
            today = now_iq.strftime('%Y-%m-%d')
            
            # نشرة الصباح (الساعة 11:00)
            if now_iq.hour == 11 and morning_sent_date != today:
                msg = f"🌅 **نشرة مباريات اليوم**\n\n{get_fixtures_today()}"
                await application.bot.send_message(chat_id=CHANNEL_USER, text=msg, parse_mode="Markdown")
                morning_sent_date = today

            # مراقبة الأهداف
            r = requests.get(f"{BASE_URL}/fixtures", headers=headers, params={"live": "all"}, timeout=10)
            live_matches = r.json().get("response", [])
            for m in live_matches:
                mid = m["fixture"]["id"]
                score = f"{m['goals']['home']}-{m['goals']['away']}"
                if mid in last_scores and last_scores[mid] != score:
                    txt = f"⚽ **تحديث النتيجة**\n\n{m['teams']['home']['name']} {score} {m['teams']['away']['name']}"
                    await application.bot.send_message(chat_id=CHANNEL_USER, text=txt)
                    # تنبيه المشتركين
                    for uid, fid in user_favorites.items():
                        if fid in [m['teams']['home']['id'], m['teams']['away']['id']]:
                            try: await application.bot.send_message(chat_id=uid, text=f"⭐ هدف لفريقك!\n{txt}")
                            except: pass
                last_scores[mid] = score
        except Exception as e: print(f"Loop Error: {e}")
        await asyncio.sleep(60)

# ================= 6. التشغيل النهائي =================

async def main():
    # 1. تشغيل Flask في Thread منفصل
    threading.Thread(target=run_flask, daemon=True).start()

    # 2. بناء تطبيق التليجرام
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(callback_handler))

    # 3. تشغيل المحرك التلقائي و البوت
    async with application:
        await application.initialize()
        await application.start()
        # تشغيل المحرك التلقائي كـ Task
        asyncio.create_task(auto_engine(application))
        print("🚀 Bot is LIVE!")
        # تشغيل الـ Polling بشكل صحيح ضمن الـ Loop
        await application.updater.start_polling(drop_pending_updates=True)
        # إبقاء الـ Loop يعمل
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
