import os
import requests
import asyncio
import json
from datetime import datetime, timedelta, timezone
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ================= 1. الإعدادات الأساسية =================
TOKEN = "8685821581:AAEBPYLDm11al-zz9-szgx9QqkFWA8sKpZY"  # ضع توكن البوت هنا
API_KEY = "a33db71c29eda79b9ec098d2c337d619"  # ضع مفتاح API هنا
CHANNEL_USER = "@Ali1Sports"  # اسم القناة

BASE_URL = "https://v3.football.api-sports.io"
headers = {"x-apisports-key": API_KEY, "x-rapidapi-host": "v3.football.api-sports.io"}
CURRENT_SEASON = "2025"

MAJOR_LEAGUES = {
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 الدوري الإنجليزي": 39,
    "🇪🇸 الدوري الإسباني": 140,
    "🇩🇪 الدوري الألماني": 78,
    "🇮🇹 الدوري الإيطالي": 135,
    "🇫🇷 الدوري الفرنسي": 61
}

# تخزين بيانات المستخدمين (للاستخدام المؤقت)
user_favorites = {}  # {user_id: team_id}
user_fav_names = {}  # {user_id: team_name}
last_scores = {}
morning_sent_date = ""

# ================= 2. خادم Flask لـ Render =================
server = Flask(__name__)

@server.route('/')
def home():
    return "✅ Ali1Sports PRO Bot is Running on Render!"

@server.route('/health')
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

# ================= 3. دوال جلب البيانات =================

def get_fixtures_today():
    """جلب مباريات اليوم للدوريات الكبرى"""
    try:
        now_iq = datetime.now(timezone.utc) + timedelta(hours=3)
        today = now_iq.strftime('%Y-%m-%d')
        
        all_matches = []
        for league_name, league_id in MAJOR_LEAGUES.items():
            try:
                url = f"{BASE_URL}/fixtures"
                params = {
                    "league": league_id,
                    "season": CURRENT_SEASON,
                    "date": today
                }
                r = requests.get(url, headers=headers, params=params, timeout=10)
                data = r.json()
                
                if data.get("response"):
                    for m in data["response"]:
                        all_matches.append({
                            "league": league_name,
                            "home": m['teams']['home']['name'],
                            "away": m['teams']['away']['name'],
                            "time": m['fixture']['date']
                        })
            except:
                continue
        
        if not all_matches:
            return "📭 لا توجد مباريات في الدوريات الكبرى اليوم."
        
        # ترتيب المباريات حسب الوقت
        all_matches.sort(key=lambda x: x['time'])
        
        text = f"📅 **مباريات اليوم ({today})**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for m in all_matches:
            utc_dt = datetime.fromisoformat(m['time'].replace('Z', '+00:00'))
            iq_time = (utc_dt + timedelta(hours=3)).strftime('%I:%M %p')
            text += f"🏆 **{m['league']}**\n"
            text += f"🏠 {m['home']} 🆚 {m['away']}\n"
            text += f"⏰ {iq_time}\n"
            text += "➖➖➖➖➖➖➖➖➖\n\n"
        
        return text
    except Exception as e:
        print(f"Error in get_fixtures_today: {e}")
        return "❌ حدث خطأ في جلب المباريات."

def get_standings(league_id):
    """جلب ترتيب الدوري"""
    try:
        url = f"{BASE_URL}/standings"
        params = {
            "league": league_id,
            "season": CURRENT_SEASON
        }
        r = requests.get(url, headers=headers, params=params, timeout=10)
        data = r.json()
        
        if not data.get("response"):
            return "⚠️ لا توجد بيانات ترتيب حالياً."
        
        standings = data["response"][0]["league"]["standings"][0]
        
        text = "🏆 **جدول الترتيب**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, team in enumerate(standings[:10], 1):
            text += f"{i}. {team['team']['name']}\n"
            text += f"   🎯 {team['points']} نقطة | 🥅 {team['goalsDiff']}\n\n"
        
        return text
    except Exception as e:
        print(f"Error in get_standings: {e}")
        return "❌ فشل جلب الترتيب."

def get_scorers(league_id):
    """جلب قائمة الهدافين"""
    try:
        url = f"{BASE_URL}/players/topscorers"
        params = {
            "league": league_id,
            "season": CURRENT_SEASON
        }
        r = requests.get(url, headers=headers, params=params, timeout=10)
        data = r.json()
        
        if not data.get("response"):
            return "⚠️ لا توجد بيانات هدافين."
        
        text = "🔥 **قائمة الهدافين**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, player in enumerate(data["response"][:10], 1):
            name = player['player']['name']
            team = player['statistics'][0]['team']['name']
            goals = player['statistics'][0]['goals']['total']
            text += f"{i}. ⚽ {name}\n"
            text += f"   🏢 {team} | {goals} هدف\n\n"
        
        return text
    except Exception as e:
        print(f"Error in get_scorers: {e}")
        return "❌ فشل جلب الهدافين."

def get_teams_kb(league_id):
    """جلب قائمة الفرق للدوري"""
    try:
        url = f"{BASE_URL}/teams"
        params = {
            "league": league_id,
            "season": CURRENT_SEASON
        }
        r = requests.get(url, headers=headers, params=params, timeout=10)
        data = r.json()
        
        teams = data.get("response", [])
        if not teams:
            return None
        
        keyboard = []
        row = []
        for team in sorted(teams, key=lambda x: x['team']['name'])[:20]:  # عرض أول 20 فريق فقط
            t_name = team['team']['name']
            t_id = team['team']['id']
            btn = InlineKeyboardButton(t_name[:20], callback_data=f"savef_{t_id}_{t_name}")
            row.append(btn)
            if len(row) == 2:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
        
        return keyboard
    except Exception as e:
        print(f"Error in get_teams_kb: {e}")
        return None

def get_live_scores():
    """جلب النتائج المباشرة"""
    try:
        url = f"{BASE_URL}/fixtures"
        params = {"live": "all"}
        r = requests.get(url, headers=headers, params=params, timeout=10)
        data = r.json()
        
        matches = data.get("response", [])
        if not matches:
            return "📭 لا توجد مباريات مباشرة الآن."
        
        text = "🏟️ **المباريات الجارية**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        for m in matches[:10]:
            home = m['teams']['home']['name']
            away = m['teams']['away']['name']
            home_score = m['goals']['home'] if m['goals']['home'] is not None else 0
            away_score = m['goals']['away'] if m['goals']['away'] is not None else 0
            elapsed = m['fixture']['status']['elapsed'] or 0
            
            text += f"⚽ {home} {home_score} - {away_score} {away}\n"
            text += f"⏱️ الدقيقة {elapsed}\n"
            text += "➖➖➖➖➖➖➖\n\n"
        
        return text
    except Exception as e:
        print(f"Error in get_live_scores: {e}")
        return "❌ خطأ في جلب النتائج."

# ================= 4. أوامر البوت =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء البوت"""
    user_id = update.effective_user.id
    
    # حفظ بيانات المستخدم
    if user_id not in user_fav_names:
        user_fav_names[user_id] = "لم يتم الاختيار"
    
    fav_name = user_fav_names.get(user_id, "لم يتم الاختيار")
    
    keyboard = [
        [InlineKeyboardButton("📅 مباريات اليوم", callback_data='btn_fix')],
        [InlineKeyboardButton("🏆 جدول الترتيب", callback_data='nav_std'), 
         InlineKeyboardButton("🔥 الهدافين", callback_data='nav_scr')],
        [InlineKeyboardButton("⭐ اختيار فريق مفضل", callback_data='nav_fav_list')],
        [InlineKeyboardButton("📊 نتائج مباشرة", callback_data='btn_live')]
    ]
    
    if user_id in user_favorites:
        keyboard.append([InlineKeyboardButton(f"❌ إلغاء متابعة {fav_name}", callback_data='btn_unfav')])
    
    keyboard.append([InlineKeyboardButton("📢 قناة البوت", url=f"https://t.me/{CHANNEL_USER[1:]}")])
    
    msg = f"⚽ **مرحباً بك في Ali1Sports PRO**\n\n"
    msg += f"🌟 فريقك المفضل: **{fav_name}**\n"
    msg += f"📢 القناة: {CHANNEL_USER}\n\n"
    msg += f"اختر إحدى الخدمات من القائمة:"
    
    if update.message:
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأزرار"""
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    await query.answer()
    
    # قائمة المباريات
    if data == 'btn_fix':
        text = get_fixtures_today()
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_kb())
    
    # النتائج المباشرة
    elif data == 'btn_live':
        text = get_live_scores()
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_kb())
    
    # عرض قائمة الدوريات
    elif data in ['nav_std', 'nav_scr', 'nav_fav_list']:
        prefix = "getstd_" if data == 'nav_std' else "getscr_" if data == 'nav_scr' else "listf_"
        keyboard = []
        for name, lid in MAJOR_LEAGUES.items():
            keyboard.append([InlineKeyboardButton(name, callback_data=f"{prefix}{lid}")])
        keyboard.append([InlineKeyboardButton("⬅️ رجوع", callback_data='main_menu')])
        
        title = "🏆 اختر الدوري لعرض الترتيب:" if data == 'nav_std' else "🔥 اختر الدوري لعرض الهدافين:" if data == 'nav_scr' else "⭐ اختر الدوري لاختيار فريقك المفضل:"
        await query.edit_message_text(title, reply_markup=InlineKeyboardMarkup(keyboard))
    
    # عرض قائمة الفرق
    elif data.startswith('listf_'):
        league_id = data.split('_')[1]
        keyboard = get_teams_kb(league_id)
        if keyboard:
            keyboard.append([InlineKeyboardButton("⬅️ رجوع", callback_data='nav_fav_list')])
            await query.edit_message_text("⭐ اختر فريقك المفضل:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("⚠️ لا توجد فرق متاحة حالياً.", reply_markup=back_kb())
    
    # عرض الترتيب
    elif data.startswith('getstd_'):
        league_id = data.split('_')[1]
        text = get_standings(league_id)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_kb())
    
    # عرض الهدافين
    elif data.startswith('getscr_'):
        league_id = data.split('_')[1]
        text = get_scorers(league_id)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_kb())
    
    # حفظ الفريق المفضل
    elif data.startswith('savef_'):
        try:
            parts = data.split('_', 2)
            if len(parts) >= 3:
                team_id = int(parts[1])
                team_name = parts[2]
                
                user_favorites[user_id] = team_id
                user_fav_names[user_id] = team_name
                
                await query.edit_message_text(
                    f"✅ تم حفظ **{team_name}** كفريقك المفضل!\n\n"
                    f"سأقوم بإرسال تنبيهات خاصة عند تسجيل أهدافه.",
                    parse_mode="Markdown",
                    reply_markup=back_kb()
                )
            else:
                await query.edit_message_text("❌ حدث خطأ في حفظ الفريق.", reply_markup=back_kb())
        except Exception as e:
            print(f"Error saving favorite: {e}")
            await query.edit_message_text("❌ حدث خطأ في حفظ الفريق.", reply_markup=back_kb())
    
    # إلغاء المتابعة
    elif data == 'btn_unfav':
        if user_id in user_favorites:
            del user_favorites[user_id]
        if user_id in user_fav_names:
            user_fav_names[user_id] = "لا يوجد"
        await start(update, context)
    
    # العودة للقائمة الرئيسية
    elif data == 'main_menu':
        await start(update, context)

def back_kb():
    """زر العودة"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ القائمة الرئيسية", callback_data='main_menu')]])

# ================= 5. المحرك التلقائي =================

async def auto_engine(app):
    """المحرك التلقائي للنشر والتنبيهات"""
    global last_scores, morning_sent_date
    
    while True:
        try:
            now_iq = datetime.now(timezone.utc) + timedelta(hours=3)
            today = now_iq.strftime('%Y-%m-%d')
            
            # النشر الصباحي الساعة 11:00
            if now_iq.hour == 11 and morning_sent_date != today:
                fixtures_text = get_fixtures_today()
                try:
                    await app.bot.send_message(
                        chat_id=CHANNEL_USER,
                        text=f"🌅 **نشرة مباريات اليوم**\n\n{fixtures_text}",
                        parse_mode="Markdown"
                    )
                    morning_sent_date = today
                    print(f"✅ تم النشر الصباحي في {now_iq.strftime('%H:%M')}")
                except Exception as e:
                    print(f"خطأ في النشر الصباحي: {e}")
            
            # مراقبة الأهداف في المباريات المباشرة
            try:
                url = f"{BASE_URL}/fixtures"
                params = {"live": "all"}
                r = requests.get(url, headers=headers, params=params, timeout=10)
                live_matches = r.json().get("response", [])
                
                for match in live_matches:
                    match_id = match["fixture"]["id"]
                    home_score = match['goals']['home'] if match['goals']['home'] is not None else 0
                    away_score = match['goals']['away'] if match['goals']['away'] is not None else 0
                    current_score = f"{home_score}-{away_score}"
                    
                    # التحقق من تغيير النتيجة
                    if match_id in last_scores and last_scores[match_id] != current_score:
                        # إرسال للقناة
                        try:
                            await app.bot.send_message(
                                chat_id=CHANNEL_USER,
                                text=f"⚽ **تحديث النتيجة**\n\n"
                                     f"{match['teams']['home']['name']} {current_score} {match['teams']['away']['name']}\n"
                                     f"⏱️ الدقيقة: {match['fixture']['status']['elapsed'] or 0}",
                                parse_mode="Markdown"
                            )
                        except:
                            pass
                        
                        # إرسال للمشتركين المفضلين
                        home_id = match['teams']['home']['id']
                        away_id = match['teams']['away']['id']
                        
                        for user_id, fav_id in user_favorites.items():
                            if fav_id in [home_id, away_id]:
                                try:
                                    await app.bot.send_message(
                                        chat_id=user_id,
                                        text=f"⭐ **تنبيه! هدف لفريقك المفضل!**\n\n"
                                             f"{match['teams']['home']['name']} {current_score} {match['teams']['away']['name']}\n"
                                             f"⏱️ الدقيقة: {match['fixture']['status']['elapsed'] or 0}",
                                        parse_mode="Markdown"
                                    )
                                except:
                                    pass
                    
                    last_scores[match_id] = current_score
                
                # تنظيف المباريات المنتهية
                current_ids = [m["fixture"]["id"] for m in live_matches]
                for old_id in list(last_scores.keys()):
                    if old_id not in current_ids:
                        del last_scores[old_id]
                        
            except Exception as e:
                print(f"خطأ في مراقبة الأهداف: {e}")
            
            await asyncio.sleep(60)  # انتظار دقيقة
            
        except Exception as e:
            print(f"خطأ في المحرك التلقائي: {e}")
            await asyncio.sleep(60)

# ================= 6. التشغيل =================

if __name__ == "__main__":
    # تشغيل Flask في thread منفصل
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # إعداد البوت
    application = ApplicationBuilder().token(TOKEN).build()
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(callback_handler))
    
    # تشغيل المحرك التلقائي
    async def post_init(application):
        asyncio.create_task(auto_engine(application))
    
    application.post_init = post_init
    
    print("🚀 Ali1Sports PRO Bot is Running on Render!")
    print(f"✅ Bot Token: {TOKEN[:10]}...")
    print(f"✅ Channel: {CHANNEL_USER}")
    print(f"✅ Major Leagues: {len(MAJOR_LEAGUES)}")
    
    # تشغيل البوت
    application.run_polling(allowed_updates=Update.ALL_TYPES)
