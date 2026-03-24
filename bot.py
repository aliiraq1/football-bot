import os
import requests
import asyncio
from datetime import datetime, timedelta, timezone
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ================= 1. الإعدادات الأساسية =================
TOKEN = "8685821581:AAEBPYLDm11al-zz9-szgx9QqkFWA8sKpZY" 
API_KEY = "a33db71c29eda79b9ec098d2c337d619" 
CHANNEL_USER = "@Ali1Sports" 

BASE_URL = "https://v3.football.api-sports.io"
headers = {"x-apisports-key": API_KEY}

# تحديد الموسم الحالي بدقة (نهاية موسم 2025 وبداية 2026)
SEASON = "2025" 

MAJOR_LEAGUES = {
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 الدوري الإنجليزي": 39,
    "🇪🇸 الدوري الإسباني": 140,
    "🇩🇪 الدوري الألماني": 78,
    "🇮🇹 الدوري الإيطالي": 135,
    "🇫🇷 الدوري الفرنسي": 61
}

# ذاكرة السيرفر (تصفّر عند الرستارت)
user_favorites = {} # {chat_id: team_id}
last_scores = {}
morning_sent_date = ""

# ================= 2. خادم Flask (للبقاء حياً على Render) =================
server = Flask('')
@server.route('/')
def home(): return "Ali1Sports PRO is Online!"

def run_flask():
    server.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# ================= 3. وظائف جلب البيانات الاحترافية =================

def get_fixtures_data():
    try:
        now_iq = datetime.now(timezone.utc) + timedelta(hours=3)
        today = now_iq.strftime('%Y-%m-%d')
        text = f"📅 **مباريات اليوم ({today})**\n━━━━━━━━━━━━━━\n\n"
        found = False
        r = requests.get(f"{BASE_URL}/fixtures?date={today}", headers=headers, timeout=10).json()
        if r.get("response"):
            for m in r["response"]:
                if m["league"]["id"] in MAJOR_LEAGUES.values():
                    found = True
                    home, away = m['teams']['home']['name'], m['teams']['away']['name']
                    utc_dt = datetime.fromisoformat(m['fixture']['date'].replace('Z', '+00:00'))
                    iq_time = (utc_dt + timedelta(hours=3)).strftime('%I:%M %p')
                    text += f"🏠 **الأرض:** {home}\n🚌 **الزائر:** {away}\n⏰ **الوقت:** {iq_time}\n"
                    text += "----------- \n"
        return text if found else "📭 لا توجد مباريات كبرى اليوم."
    except: return "❌ تعذر جلب المواعيد حالياً."

def get_league_standings(league_id):
    try:
        r = requests.get(f"{BASE_URL}/standings?league={league_id}&season={SEASON}", headers=headers, timeout=10).json()
        if not r.get("response"): return "⚠️ لا توجد بيانات ترتيب حالياً."
        st = r["response"][0]["league"]["standings"][0]
        text = f"📊 **الترتيب (أول 10):**\n\n"
        for t in st[:10]:
            text += f"{t['rank']}. {t['team']['name']} - {t['points']}ن\n"
        return text
    except: return "❌ فشل جلب الترتيب."

def get_league_scorers(league_id):
    try:
        r = requests.get(f"{BASE_URL}/players/topscorers?league={league_id}&season={SEASON}", headers=headers, timeout=10).json()
        if not r.get("response"): return "⚠️ لا توجد بيانات هدافين."
        text = "⚽ **أفضل الهدافين:**\n\n"
        for p in r["response"][:7]:
            text += f"👤 {p['player']['name']} ({p['statistics'][0]['team']['name']}) - ⚽ {p['statistics'][0]['goals']['total']}\n"
        return text
    except: return "❌ فشل جلب الهدافين."

def get_teams_list(league_id):
    try:
        r = requests.get(f"{BASE_URL}/teams?league={league_id}&season={SEASON}", headers=headers, timeout=15).json()
        teams = r.get("response", [])
        keyboard, row = [], []
        for t in teams:
            t_name, t_id = t['team']['name'], t['team']['id']
            row.append(InlineKeyboardButton(t_name, callback_data=f"savefav_{t_id}_{t_name}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row: keyboard.append(row)
        return keyboard
    except: return []

# ================= 4. نظام التفاعل والواجهات =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    fav_name = context.user_data.get('fav_team_name', "لم يتم الاختيار")
    
    keyboard = [
        [InlineKeyboardButton("📅 مواعيد المباريات اليوم", callback_data='cmd_fixtures')],
        [InlineKeyboardButton("🏆 الترتيب", callback_data='nav_std'), InlineKeyboardButton("🔥 الهدافين", callback_data='nav_scr')],
        [InlineKeyboardButton("⭐ اختيار فريق مفضل", callback_data='nav_fav')],
        [InlineKeyboardButton("📊 نتائج مباشرة (الآن)", callback_data='cmd_live')]
    ]
    if user_id in user_favorites:
        keyboard.append([InlineKeyboardButton(f"❌ إلغاء متابعة {fav_name}", callback_data='cmd_unfav')])
    
    keyboard.append([InlineKeyboardButton("📢 قناة Ali1Sports", url=f"https://t.me/{CHANNEL_USER[1:]}")])
    
    msg = f"⚽ **أهلاً بك في بوت Ali1Sports الاحترافي**\n🌟 فريقك المفضل: **{fav_name}**\n\nاختر ما تريد من القائمة:"
    if update.message: await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else: await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data == 'cmd_fixtures':
        await query.edit_message_text(get_fixtures_data(), parse_mode="Markdown", reply_markup=back_kb())
    
    elif data == 'cmd_live':
        r = requests.get(f"{BASE_URL}/fixtures?live=all", headers=headers).json()
        res = "🏟️ **المباريات الجارية حالياً:**\n\n"
        matches = r.get("response", [])
        if matches:
            for m in matches[:10]:
                res += f"⚽ {m['teams']['home']['name']} {m['goals']['home']}-{m['goals']['away']} {m['teams']['away']['name']} ({m['fixture']['status']['elapsed']}')\n"
        else: res = "📭 لا توجد مباريات مباشرة في الوقت الحالي."
        await query.edit_message_text(res, reply_markup=back_kb())

    elif data in ['nav_std', 'nav_scr', 'nav_fav']:
        prefix = "getstd_" if data == 'nav_std' else "getscr_" if data == 'nav_scr' else "listf_"
        kb = [[InlineKeyboardButton(name, callback_data=f"{prefix}{id}")] for name, id in MAJOR_LEAGUES.items()]
        kb.append([InlineKeyboardButton("⬅️ عودة للقائمة الرئيسية", callback_data='main_menu')])
        await query.edit_message_text("اختر الدوري المطلوب:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith('listf_'):
        l_id = data.split('_')[1]
        kb = get_teams_list(l_id)
        if kb:
            kb.append([InlineKeyboardButton("⬅️ عودة للدوريات", callback_data='nav_fav')])
            await query.edit_message_text("اختر فريقك المفضل من القائمة التالية:", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await query.edit_message_text("⚠️ لم يتم العثور على فرق لهذا الدوري حالياً.", reply_markup=back_kb())

    elif data.startswith('getstd_'):
        await query.edit_message_text(get_league_standings(data.split('_')[1]), parse_mode="Markdown", reply_markup=back_kb())

    elif data.startswith('getscr_'):
        await query.edit_message_text(get_league_scorers(data.split('_')[1]), parse_mode="Markdown", reply_markup=back_kb())

    elif data.startswith('savefav_'):
        _, t_id, t_name = data.split('_')
        user_favorites[query.from_user.id] = int(t_id)
        context.user_data['fav_team_name'] = t_name
        await query.edit_message_text(f"✅ تم حفظ **{t_name}** بنجاح! ستصلك تنبيهات بأهدافه هنا.", reply_markup=back_kb())

    elif data == 'cmd_unfav':
        user_favorites.pop(query.from_user.id, None)
        context.user_data['fav_team_name'] = "لا يوجد"
        await start(update, context)
    
    elif data == 'main_menu': await start(update, context)

def back_kb(): return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data='main_menu')]])

# ================= 5. المحرك التلقائي الذكي =================

async def auto_engine(app):
    global last_scores, morning_sent_date
    while True:
        try:
            now_iq = datetime.now(timezone.utc) + timedelta(hours=3)
            today = now_iq.strftime('%Y-%m-%d')
            
            # نشر جدول اليوم تلقائياً الساعة 11:00 صباحاً
            if now_iq.hour == 11 and morning_sent_date != today:
                await app.bot.send_message(chat_id=CHANNEL_USER, text=get_fixtures_data(), parse_mode="Markdown")
                morning_sent_date = today

            # مراقبة الأهداف المباشرة
            live = requests.get(f"{BASE_URL}/fixtures?live=all", headers=headers, timeout=10).json()
            for m in live.get("response", []):
                f_id = m["fixture"]["id"]
                score = f"{m['goals']['home']}-{m['goals']['away']}"
                
                if f_id in last_scores and last_scores[f_id] != score:
                    # النشر في القناة
                    goal_msg = f"⚽ هدف!! {m['teams']['home']['name']} {score} {m['teams']['away']['name']}"
                    await app.bot.send_message(chat_id=CHANNEL_USER, text=goal_msg)
                    
                    # التنبيه للمشتركين في الخاص
                    h_id, a_id = m['teams']['home']['id'], m['teams']['away']['id']
                    for u_id, fav_id in user_favorites.items():
                        if fav_id in [h_id, a_id]:
                            await app.bot.send_message(chat_id=u_id, text=f"⭐ هدف لفريقك المفضل!\nالنتيجة الآن: {score}")
                
                last_scores[f_id] = score
        except: pass
        await asyncio.sleep(60)

# ================= 6. تشغيل البوت =================
if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot_app = ApplicationBuilder().token(TOKEN).build()
    
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(handle_callbacks))
    
    async def run_engine(application): asyncio.create_task(auto_engine(application))
    bot_app.post_init = run_engine
    
    print("--- Ali1Sports PRO System is Running Successfully ---")
    bot_app.run_polling(drop_pending_updates=True)
