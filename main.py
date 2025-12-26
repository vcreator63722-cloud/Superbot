import telebot
from telebot import types
from pymongo import MongoClient
import time
import dns.resolver
from flask import Flask
from threading import Thread

# ==========================================
# 1. WEB SERVER
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Bot is Running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 2. CONFIGURATION
# ==========================================
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8']

API_TOKEN = '8269677550:AAFv6PJBmz7rkeEUAo9Wys_ZN939WHwqHuw' 
ADMIN_ID = 2145958203 
MONGO_URL = 'mongodb+srv://Admin:637ROHITREX@cluster0.thuobo8.mongodb.net/?appName=Cluster0'
MUST_JOIN_CHANNEL = '@whitewolfteam_TG' 

PER_REFER_BONUS = 10
DAILY_BONUS_AMOUNT = 5
MIN_WITHDRAW = 50

# ==========================================
# 3. DATABASE
# ==========================================
try:
    client = MongoClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
    db = client['TelegramBotDB']
    users_col = db['users']
    withdraw_col = db['withdrawals']
    channels_col = db['channels']
except Exception as e:
    print(f"DB Error: {e}")

bot = telebot.TeleBot(API_TOKEN)

# --- FUNCTIONS ---

def get_all_required_channels():
    db_channels = [ch['username'] for ch in channels_col.find({})]
    all_channels = [MUST_JOIN_CHANNEL] + db_channels
    return list(set(all_channels))

def check_user_joined(user_id):
    required = get_all_required_channels()
    not_joined = []
    for ch_username in required:
        try:
            status = bot.get_chat_member(ch_username, user_id).status
            if status not in ['creator', 'administrator', 'member']:
                not_joined.append(ch_username)
        except:
            pass 
    return not_joined

def add_user(user_id, referrer_id=None):
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({
            "user_id": user_id,
            "balance": 0,
            "referrals": 0,
            "joined_date": time.time(),
            "last_bonus": 0
        })
        if referrer_id and referrer_id != user_id:
            users_col.update_one({"user_id": referrer_id}, {"$inc": {"balance": PER_REFER_BONUS, "referrals": 1}})
            try: bot.send_message(referrer_id, f"🎉 New Referral! (+{PER_REFER_BONUS} Points)")
            except: pass

# --- START ---

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
            markup.add(types.InlineKeyboardButton(f"🔔 Join {ch}", url=f"https://t.me/{clean_ch}"))
        markup.add(types.InlineKeyboardButton("✅ Joined All", callback_data="check_join_status"))
        bot.send_message(user_id, f"⚠️ **Access Denied!**\n\nChannels join karein:", reply_markup=markup, parse_mode="Markdown")
    else:
        main_menu(user_id)

@bot.callback_query_handler(func=lambda call: call.data == "check_join_status")
def verify_join(call):
    if not check_user_joined(call.message.chat.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        main_menu(call.message.chat.id)
    else:
        bot.answer_callback_query(call.id, "❌ Join nahi kiya!", show_alert=True)

def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Balance", "🎁 Daily Bonus")
    markup.row("👫 Refer & Earn", "🏦 Withdraw")
    markup.row("🏆 Leaderboard", "📞 Support") # Support button added
    if user_id == ADMIN_ID:
        markup.row("📢 Broadcast", "⚙️ Manage Channels")
    bot.send_message(user_id, "👋 **Menu:** Select Option:", reply_markup=markup, parse_mode="Markdown")

# --- FEATURES ---

@bot.message_handler(func=lambda m: m.text == "💰 Balance")
def bal(m):
    d = users_col.find_one({"user_id": m.chat.id})
    if d: bot.reply_to(m, f"💰 Balance: {d.get('balance',0)}\n👥 Referrals: {d.get('referrals',0)}")

@bot.message_handler(func=lambda m: m.text == "🎁 Daily Bonus")
def bonus(m):
    uid = m.chat.id
    d = users_col.find_one({"user_id": uid})
    now = time.time()
    if now - d.get('last_bonus', 0) > 86400:
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": DAILY_BONUS_AMOUNT}, "$set": {"last_bonus": now}})
        bot.reply_to(m, f"✅ +{DAILY_BONUS_AMOUNT} Bonus Added!")
    else:
        bot.reply_to(m, "❌ Kal aana!")

@bot.message_handler(func=lambda m: m.text == "👫 Refer & Earn")
def ref(m):
    link = f"https://t.me/{bot.get_me().username}?start={m.chat.id}"
    bot.reply_to(m, f"🎁 Per Refer: {PER_REFER_BONUS}\n🔗 Link: {link}")

@bot.message_handler(func=lambda m: m.text == "🏆 Leaderboard")
def lead(m):
    tops = users_col.find().sort("referrals", -1).limit(10)
    msg = "🏆 **Leaderboard**\n"
    for i, u in enumerate(tops):
        msg += f"{i+1}. ID:{str(u['user_id'])[:5]}.. - {u['referrals']} Refs\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

# --- SUPPORT SYSTEM (NEW) ---

@bot.message_handler(func=lambda m: m.text == "📞 Support")
def ask_support(m):
    msg = bot.send_message(m.chat.id, "✏️ **Apna sawal/message likh kar bhejein:**\n(Hum jald hi reply karenge)", parse_mode="Markdown")
    bot.register_next_step_handler(msg, send_to_admin)

def send_to_admin(message):
    try:
        if message.text:
            # Admin ko bhejo
            bot.send_message(ADMIN_ID, f"📩 **New Support Message!**\n\n👤 User ID: `{message.chat.id}`\n📄 Message: {message.text}\n\n👇 **Reply karne ke liye copy karein:**\n`/reply {message.chat.id} YOUR_MESSAGE`", parse_mode="Markdown")
            # User ko confirm karo
            bot.reply_to(message, "✅ **Message Sent!**\nAdmin jald hi reply karenge.")
        else:
            bot.reply_to(message, "❌ Sirf text message bhejein.")
    except Exception as e:
        bot.reply_to(message, "Error sending message.")

# --- ADMIN REPLY COMMAND ---
@bot.message_handler(commands=['reply'])
def admin_reply(message):
    if message.chat.id == ADMIN_ID:
        try:
            # Format: /reply 12345678 Message
            parts = message.text.split(maxsplit=2)
            user_id = int(parts[1])
            reply_text = parts[2]
            
            bot.send_message(user_id, f"👨‍💻 **Admin Reply:**\n\n{reply_text}", parse_mode="Markdown")
            bot.reply_to(message, "✅ Reply sent successfully!")
        except:
            bot.reply_to(message, "❌ **Error!**\nSahi format use karein:\n`/reply UserID Message`", parse_mode="Markdown")

# --- WITHDRAW & ADMIN ---
@bot.message_handler(func=lambda m: m.text == "🏦 Withdraw")
def with_req(m):
    if check_user_joined(m.chat.id):
        bot.reply_to(m, "❌ Channels leave na karein!")
        return
    d = users_col.find_one({"user_id": m.chat.id})
    if d.get('balance', 0) >= MIN_WITHDRAW:
        msg = bot.send_message(m.chat.id, "👇 Payment Number bhejein:")
        bot.register_next_step_handler(msg, process_pay)
    else:
        bot.reply_to(m, f"❌ Min Withdraw: {MIN_WITHDRAW}")

def process_pay(m):
    try:
        uid, num = m.chat.id, m.text
        amt = users_col.find_one({"user_id": uid})['balance']
        users_col.update_one({"user_id": uid}, {"$set": {"balance": 0}})
        mark = types.InlineKeyboardMarkup()
        mark.add(types.InlineKeyboardButton("✅ Pay", callback_data=f"py_yes_{uid}_{amt}"),
                 types.InlineKeyboardButton("❌ Reject", callback_data=f"py_no_{uid}_{amt}"))
        bot.send_message(uid, "✅ Request Submitted!")
        bot.send_message(ADMIN_ID, f"🔔 **Withdraw**\nUser: {uid}\nAmt: {amt}\nNum: {num}", reply_markup=mark)
    except: pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("py_"))
def admin_pay(c):
    if c.message.chat.id != ADMIN_ID: return
    act, uid, amt = c.data.split("_")[1], int(c.data.split("_")[2]), int(c.data.split("_")[3])
    if act == "yes":
        bot.edit_message_text(f"✅ Paid {uid}", c.message.chat.id, c.message.message_id)
        try: bot.send_message(uid, "✅ Payment Successful!")
        except: pass
    else:
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": amt}})
        bot.edit_message_text(f"❌ Rejected {uid}", c.message.chat.id, c.message.message_id)
        try: bot.send_message(uid, "❌ Rejected (Refunded)")
        except: pass

@bot.message_handler(commands=['addchannel'])
def addc(m):
    if m.chat.id==ADMIN_ID:
        try: channels_col.insert_one({"username": m.text.split()[1]}); bot.reply_to(m, "✅ Added")
        except: pass

@bot.message_handler(commands=['removechannel'])
def remc(m):
    if m.chat.id==ADMIN_ID:
        try: channels_col.delete_one({"username": m.text.split()[1]}); bot.reply_to(m, "🗑 Removed")
        except: pass

@bot.message_handler(func=lambda m: m.text == "📢 Broadcast")
def bcast(m):
    if m.chat.id==ADMIN_ID:
        msg = bot.send_message(m.chat.id, "Send Msg:")
        bot.register_next_step_handler(msg, lambda mm: [bot.copy_message(u['user_id'], mm.chat.id, mm.message_id) for u in users_col.find({})])

@bot.message_handler(func=lambda m: m.text == "📊 Stats")
def stats(m):
    if m.chat.id==ADMIN_ID:
        u = users_col.count_documents({})
        bot.reply_to(m, f"Total Users: {u}")

keep_alive()
print("Bot Started...")
bot.infinity_polling()
