import telebot
from telebot import types
from pymongo import MongoClient
import time
import dns.resolver
from flask import Flask
from threading import Thread
import os  # <--- Ye line zaruri hai secrets ke liye

# ==========================================
# 1. WEB SERVER
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Secure Bot is Running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 2. SECURE CONFIGURATION (Secrets Chupana)
# ==========================================
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8']

# AB HUM PASSWORD CODE ME NAHI LIKHENGE
# Hum Server se mangenge
API_TOKEN = os.environ.get('BOT_TOKEN')
MONGO_URL = os.environ.get('MONGO_URL')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '1234567890')) # Default ID agar na mile
MUST_JOIN_CHANNEL = '@whitewolfteam_TG' 

PER_REFER_BONUS = 10
DAILY_BONUS_AMOUNT = 5
MIN_WITHDRAW = 50

# ==========================================
# 3. DATABASE CONNECTION
# ==========================================
try:
    if not MONGO_URL:
        print("❌ Error: MONGO_URL setup nahi hai Environment Variables mein!")
    
    client = MongoClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
    db = client['TelegramBotDB']
    users_col = db['users']
    withdraw_col = db['withdrawals']
    channels_col = db['channels']
except Exception as e:
    print(f"DB Error: {e}")

# Check if Token exists
if not API_TOKEN:
    print("❌ Error: BOT_TOKEN setup nahi hai!")
else:
    bot = telebot.TeleBot(API_TOKEN)

# --- FUNCTIONS ---

def get_all_required_channels():
    try:
        db_channels = [ch['username'] for ch in channels_col.find({})]
        all_channels = [MUST_JOIN_CHANNEL] + db_channels
        return list(set(all_channels))
    except: return [MUST_JOIN_CHANNEL]

def check_user_joined(user_id):
    required = get_all_required_channels()
    not_joined = []
    for ch_username in required:
        try:
            status = bot.get_chat_member(ch_username, user_id).status
            if status not in ['creator', 'administrator', 'member']:
                not_joined.append(ch_username)
        except: pass 
    return not_joined

def add_user(user_id, referrer_id=None):
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({
            "user_id": user_id, "balance": 0, "referrals": 0,
            "joined_date": time.time(), "last_bonus": 0
        })
        if referrer_id and referrer_id != user_id:
            users_col.update_one({"user_id": referrer_id}, {"$inc": {"balance": PER_REFER_BONUS, "referrals": 1}})
            try: bot.send_message(referrer_id, f"🎉 New Referral! (+{PER_REFER_BONUS})")
            except: pass

# --- HANDLERS ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.chat.id
    text = message.text.split()
    referrer = None
    if len(text) > 1:
        try: referrer = int(text[1])
        except: pass
    
    add_user(user_id, referrer)
    
    pending = check_user_joined(user_id)
    if pending:
        markup = types.InlineKeyboardMarkup()
        for ch in pending:
            clean_ch = ch.replace('@', '')
            markup.add(types.InlineKeyboardButton(f"Join {ch}", url=f"https://t.me/{clean_ch}"))
        markup.add(types.InlineKeyboardButton("✅ Joined All", callback_data="check_join_status"))
        bot.send_message(user_id, "⚠️ Join Channels First:", reply_markup=markup)
    else:
        main_menu(user_id)

@bot.callback_query_handler(func=lambda c: c.data == "check_join_status")
def verify_join(c):
    if not check_user_joined(c.message.chat.id):
        bot.delete_message(c.message.chat.id, c.message.message_id)
        main_menu(c.message.chat.id)
    else:
        bot.answer_callback_query(c.id, "❌ Join nahi kiya!", show_alert=True)

def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Balance", "🎁 Daily Bonus")
    markup.row("👫 Refer & Earn", "🏦 Withdraw")
    markup.row("🏆 Leaderboard", "📞 Support")
    if user_id == ADMIN_ID: markup.row("📢 Broadcast", "⚙️ Manage Channels")
    bot.send_message(user_id, "👋 Menu:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "💰 Balance")
def bal(m):
    d = users_col.find_one({"user_id": m.chat.id})
    if d: bot.reply_to(m, f"💰 Bal: {d.get('balance',0)}")

@bot.message_handler(func=lambda m: m.text == "🎁 Daily Bonus")
def bonus(m):
    uid = m.chat.id
    d = users_col.find_one({"user_id": uid})
    now = time.time()
    if now - d.get('last_bonus', 0) > 86400:
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": DAILY_BONUS_AMOUNT}, "$set": {"last_bonus": now}})
        bot.reply_to(m, f"✅ +{DAILY_BONUS_AMOUNT} Bonus!")
    else: bot.reply_to(m, "❌ Kal aana!")

@bot.message_handler(func=lambda m: m.text == "👫 Refer & Earn")
def ref(m):
    link = f"https://t.me/{bot.get_me().username}?start={m.chat.id}"
    bot.reply_to(m, f"🔗 Link: {link}")

@bot.message_handler(func=lambda m: m.text == "🏆 Leaderboard")
def lead(m):
    tops = users_col.find().sort("referrals", -1).limit(10)
    msg = "🏆 Top 10:\n"
    for i, u in enumerate(tops): msg += f"{i+1}. {u['referrals']} Refs\n"
    bot.send_message(m.chat.id, msg)

@bot.message_handler(func=lambda m: m.text == "📞 Support")
def sup(m):
    msg = bot.send_message(m.chat.id, "✏️ Message likhein:")
    bot.register_next_step_handler(msg, lambda mm: [bot.send_message(ADMIN_ID, f"📩 Support: {mm.text}\nID: {mm.chat.id}\nCmd: `/reply {mm.chat.id} msg`", parse_mode="Markdown"), bot.reply_to(mm, "✅ Sent")])

@bot.message_handler(commands=['reply'])
def rep(m):
    if m.chat.id==ADMIN_ID:
        try:
            parts = m.text.split(maxsplit=2)
            bot.send_message(int(parts[1]), f"👨‍💻 Reply: {parts[2]}")
            bot.reply_to(m, "✅ Done")
        except: pass

@bot.message_handler(func=lambda m: m.text == "🏦 Withdraw")
def with_req(m):
    if check_user_joined(m.chat.id):
        bot.reply_to(m, "❌ Join Channels first")
        return
    if users_col.find_one({"user_id": m.chat.id}).get('balance', 0) >= MIN_WITHDRAW:
        bot.register_next_step_handler(bot.send_message(m.chat.id, "Number?"), process_pay)
    else: bot.reply_to(m, f"Min: {MIN_WITHDRAW}")

def process_pay(m):
    try:
        uid, amt = m.chat.id, users_col.find_one({"user_id": m.chat.id})['balance']
        users_col.update_one({"user_id": uid}, {"$set": {"balance": 0}})
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("✅", callback_data=f"p_y_{uid}_{amt}"), types.InlineKeyboardButton("❌", callback_data=f"p_n_{uid}_{amt}"))
        bot.send_message(ADMIN_ID, f"Withdraw: {amt}\nNum: {m.text}", reply_markup=mk)
        bot.send_message(uid, "✅ Requested")
    except: pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("p_"))
def adm_act(c):
    if c.message.chat.id!=ADMIN_ID: return
    act, uid, amt = c.data.split("_")[1], int(c.data.split("_")[2]), int(c.data.split("_")[3])
    if act=="y": bot.send_message(uid, "✅ Paid"); bot.delete_message(c.message.chat.id, c.message.message_id)
    else: users_col.update_one({"user_id": uid}, {"$inc": {"balance": amt}}); bot.send_message(uid, "❌ Rejected"); bot.delete_message(c.message.chat.id, c.message.message_id)

# --- ADMIN COMMANDS ---
@bot.message_handler(commands=['addchannel'])
def ac(m): 
    if m.chat.id==ADMIN_ID: channels_col.insert_one({"username": m.text.split()[1]}); bot.reply_to(m, "Done")

@bot.message_handler(commands=['removechannel'])
def rc(m): 
    if m.chat.id==ADMIN_ID: channels_col.delete_one({"username": m.text.split()[1]}); bot.reply_to(m, "Done")

@bot.message_handler(func=lambda m: m.text == "📢 Broadcast")
def bc(m): 
    if m.chat.id==ADMIN_ID: bot.register_next_step_handler(bot.send_message(m.chat.id, "Msg?"), lambda mm: [bot.copy_message(u['user_id'], mm.chat.id, mm.message_id) for u in users_col.find({})])

keep_alive()
if API_TOKEN:
    bot.infinity_polling()
