import os
import requests
import asyncio
import logging
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ================= الإعدادات الأساسية =================
# ضع التوكن الخاص بك هنا
TOKEN = "8685821581:AAEBPYLDm11al-zz9-szgx9QqkFWA8sKpZY"
# ضع مفتاح API-Football هنا
API_KEY = "a33db71c29eda79b9ec098d2c337d619"
# معرف قناتك
CHANNEL_USER = "@Ali1Sports" 

BASE_URL = "https://v3.football.api-sports.io"
headers = {"x-apisports-key": API_KEY}

# الدوريات الكبرى (إنجلترا، إسبانيا، إيطاليا، ألمانيا، فرنسا، الأبطال، الدوري السعودي، الدوري العراقي)
MAJOR_LEAGUES = [39, 140, 135, 78, 61, 2, 3, 17, 307, 268]

last_scores = {}
sent_lineups = set()

# ================= خادم Flask للبقاء حياً =================
server = Flask('')
@server.route('/')
def home(): return "⚽ Ali1Sports Bot is LIVE!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

# ================= وظائف جلب البيانات =================

def get_lineups_and_injuries(fixture_id):
    """جلب التشكيلة الرسمية والغيابات قبل المباراة"""
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
        
        if injuries_res.get("response") and len(injuries_res["response"]) > 0:
            text += "🚑 **الغيابات المؤكدة:**\n"
            for inj in injuries_res["response"][:10]: # عرض أول 10 غيابات فقط
                text += f"• {inj['player']['name']} ({inj['team']['name']}) - {inj['player']['type']}\n"
        
        return text if text else None
    except Exception as e:
        print(f"Error fetching lineups: {e}")
        return None

def get_daily_fixtures():
    """جدول مباريات اليوم بتوقيت العراق (12:00 م)"""
    try:
        iq_time = datetime.utcnow() + timedelta(hours=3)
        today = iq_time.strftime('%Y-%m-%d')
        text = f"📅 **أهم مباريات اليوم ({today})**\n━━━━━━━━━━━━━━\n\n"
        
        found = False
        for league_id in MAJOR_LEAGUES:
            r = requests.get(f"{BASE_URL}/fixtures?date={today}&league={league_id}&season=2024", headers=headers, timeout=10).json()
            if r.get("response"):
                found = True
                text += f"🏆 **{r['response'][0]['league']['name']}**\n"
                for m in r["response"][:5]:
                    # تحويل الوقت لتوقيت العراق
                    utc_dt = datetime.fromisoformat(m['fixture']['date'].replace('Z', '+00:00'))
                    iq_dt = utc_dt + timedelta(hours=3)
                    text += f"⏰ {iq_dt.strftime('%I:%M %p')} | {m['teams']['home']['name']} 🆚 {m['teams']['away']['name']}\n"
                text += " \n"
        
        text += f"\n📢 تابعونا لتغطية الأهداف والتشكيلات: {CHANNEL_USER}"
        return text if found else "⚠️ لا توجد مباريات كبرى مجدولة اليوم."
    except Exception as e:
        print(f"Error fetching fixtures: {e}")
        return "❌ عذراً، تعذر جلب جدول المباريات حالياً."

# ================= المحرك الذكي (Background Engine) =================

async def main_engine(app):
    global last_scores, sent_lineups
    morning_sent = False 
    
    while True:
        try:
            now_iq = datetime.utcnow() + timedelta(hours=3)
            
            # 1. إرسال جدول المباريات الساعة 12:00 م بتوقيت العراق
            if now_iq.hour == 12 and now_iq.minute == 0 and not morning_sent:
                await app.bot.send_message(chat_id=CHANNEL_USER, text=get_daily_fixtures(), parse_mode="Markdown")
                morning_sent = True
            
            # إعادة الضبط للسماح بإرسال جدول اليوم التالي
            if now_iq.hour == 0: morning_sent = False

            # 2. مراقبة التشكيلات والأهداف
            today_str = now_iq.strftime('%Y-%m-%d')
            r = requests.get(f"{BASE_URL}/fixtures?date={today_str}", headers=headers, timeout=10).json()
            
            if r.get("response"):
                for m in r["response"]:
                    f_id = m["fixture"]["id"]
                    l_id = m["league"]["id"]
                    
                    if l_id in MAJOR_LEAGUES:
                        status = m["fixture"]["status"]["short"]
                        
                        # --- ميزة التشكيلة (قبل 40 دقيقة) ---
                        if status == "NS" and f_id not in sent_lineups:
                            match_time = datetime.fromisoformat(m['fixture']['date'].replace('Z', '+00:00'))
                            if (match_time - datetime.utcnow()).total_seconds() / 60 <= 40:
                                lineup_info = get_lineups_and_injuries(f_id)
                                if lineup_info:
                                    msg = f"📋 **التشكيلة الرسمية والغيابات**\n⚽ {m['teams']['home']['name']} 🆚 {m['teams']['away']['name']}\n\n" + lineup_info
                                    await app.bot.send_message(chat_id=CHANNEL_USER, text=msg, parse_mode="Markdown")
                                    sent_lineups.add(f_id)

                        # --- ميزة الأهداف المباشرة ---
                        if status in ["1H", "2H", "ET", "P"]:
                            score = f"{m['goals']['home']} - {m['goals']['away']}"
                            if f_id in last_scores and last_scores[f_id] != score:
                                goal_msg = (
                                    f"GOOOOAL !! 🥅⚽️\n\n"
                                    f"🔥 **هدف جديد الآن**\n"
                                    f"━━━━━━━━━━━━\n"
                                    f"🏠 {m['teams']['home']['name']}\n"
                                    f"  【 {score} 】 \n"
                                    f"🚌 {m['teams']['away']['name']}\n"
                                    f"━━━━━━━━━━━━\n"
                                    f"📢 {CHANNEL_USER}"
                                )
                                await app.bot.send_message(chat_id=CHANNEL_USER, text=goal_msg, parse_mode="Markdown")
                                last_scores[f_id] = score
                            elif f_id not in last_scores:
                                last_scores[f_id] = score
        except Exception as e:
            print(f"Engine Loop Error: {e}")
            
        await asyncio.sleep(60) # فحص كل دقيقة

# ================= التشغيل =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ البوت متصل بنجاح.\nسيتم تزويد القناة بالأهداف، التشكيلات، وجداول المباريات آلياً.")

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    
    bot_app = ApplicationBuilder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    
    async def setup_engine(application):
        asyncio.create_task(main_engine(application))

    bot_app.post_init = setup_engine
    print("--- Ali1Sports PRO Bot is Running ---")
    bot_app.run_polling(drop_pending_updates=True)
