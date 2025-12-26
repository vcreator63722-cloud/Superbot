import telebot
from telebot import types
from pymongo import MongoClient
import time
import dns.resolver
from flask import Flask
from threading import Thread
import os 

# ==========================================
# 1. WEB SERVER
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Ultra Pro Bot is Live!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 2. CONFIGURATION & DATABASE
# ==========================================
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8']

API_TOKEN = os.environ.get('BOT_TOKEN')
MONGO_URL = os.environ.get('MONGO_URL')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '1234567890'))

# --- SETTINGS ---
PER_REFER_BONUS = 10
DAILY_BONUS_AMOUNT = 5
MIN_WITHDRAW = 50

try:
    if not MONGO_URL: print("❌ Error: MONGO_URL missing!")
    client = MongoClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
    db = client['TelegramBotDB']
    users_col = db['users']
    withdraw_col = db['withdrawals']
    channels_col = db['channels'] # Ab isme ID aur Link dono honge
except Exception as e:
    print(f"DB Error: {e}")

if API_TOKEN:
    bot = telebot.TeleBot(API_TOKEN)
else:
    print("❌ Error: BOT_TOKEN missing!")

# --- FUNCTIONS ---

def get_required_channels():
    # Database se saare channels nikalo
    return list(channels_col.find({}))

def check_user_joined(user_id):
    channels = get_required_channels()
    not_joined = []
    
    for ch in channels:
        try:
            # chat_id use karenge (Public ke liye @username, Private ke liye -100...)
            status = bot.get_chat_member(ch['chat_id'], user_id).status
            if status not in ['creator', 'administrator', 'member']:
                not_joined.append(ch) # Pura channel object store karo (Link ke liye)
        except Exception as e:
            # Agar bot admin nahi hai ya channel delete ho gaya
            pass 
            
    return not_joined

def add_user(user_id, referrer_id=None):
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({
            "user_id": user_id, "balance": 0, "referrals": 0,
            "joined_date": time.time(), "last_bonus": 0
        })
        if referrer_id and referrer_id != user_id:
            users_col.update_one({"user_id": referrer_id}, {"$inc": {"balance": PER_REFER_BONUS, "referrals": 1}})
            try: 
                bot.send_message(referrer_id, f"🎉 **New Referral!**\nUser: `{user_id}`\nBonus: +{PER_REFER_BONUS}", parse_mode="Markdown")
            except: pass

# --- START & FORCE JOIN ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.chat.id
    text = message.text.split()
    referrer = None
    if len(text) > 1:
        try: referrer = int(text[1])
        except: pass
    
    add_user(user_id, referrer)
    
    pending_channels = check_user_joined(user_id)
    if pending_channels:
        markup = types.InlineKeyboardMarkup()
        for ch in pending_channels:
            # Button par naam aur Link database se aayega
            btn_text = f"🔔 Join {ch['name']}"
            markup.add(types.InlineKeyboardButton(btn_text, url=ch['link']))
        
        markup.add(types.InlineKeyboardButton("✅ Maine Join Kar Liya", callback_data="check_join_status"))
        
        msg = f"""
🚧 **ACCESS DENIED** 🚧

Bot use karne ke liye niche diye gaye **Channels Join** karein:
"""
        bot.send_message(user_id, msg, reply_markup=markup, parse_mode="Markdown")
    else:
        main_menu(user_id)

@bot.callback_query_handler(func=lambda c: c.data == "check_join_status")
def verify_join(c):
    if not check_user_joined(c.message.chat.id):
        bot.delete_message(c.message.chat.id, c.message.message_id)
        bot.answer_callback_query(c.id, "✅ Success!")
        main_menu(c.message.chat.id)
    else:
        bot.answer_callback_query(c.id, "❌ Aapne abhi tak saare channels join nahi kiye!", show_alert=True)

def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 Balance", "🎁 Daily Bonus")
    markup.add("👫 Refer & Earn", "🏦 Withdraw")
    markup.add("🏆 Leaderboard", "📞 Support")
    if user_id == ADMIN_ID: 
        markup.add("📢 Broadcast", "⚙️ Add Channel")
        markup.add("🗑 Delete Channel")
    
    bot.send_message(user_id, "👋 **Main Menu:**", reply_markup=markup, parse_mode="Markdown")

# --- FEATURES ---
# (Baaki features same rahenge, bas channel add karne ka tareeka badal gaya hai)

@bot.message_handler(func=lambda m: m.text == "💰 Balance")
def bal(m):
    d = users_col.find_one({"user_id": m.chat.id})
    if d: bot.reply_to(m, f"💰 **Balance:** `{d.get('balance',0)}` Points\n👥 **Invites:** `{d.get('referrals',0)}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎁 Daily Bonus")
def bonus(m):
    uid = m.chat.id
    d = users_col.find_one({"user_id": uid})
    now = time.time()
    if now - d.get('last_bonus', 0) > 86400:
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": DAILY_BONUS_AMOUNT}, "$set": {"last_bonus": now}})
        bot.reply_to(m, f"✅ **Bonus Claimed:** +{DAILY_BONUS_AMOUNT} Points", parse_mode="Markdown")
    else:
        bot.reply_to(m, "⏳ **Wait:** Kal aana!")

@bot.message_handler(func=lambda m: m.text == "👫 Refer & Earn")
def ref(m):
    link = f"https://t.me/{bot.get_me().username}?start={m.chat.id}"
    bot.reply_to(m, f"🔗 **Refer Link:**\n`{link}`\n\n🎁 **Bonus:** {PER_REFER_BONUS} Points per refer", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🏆 Leaderboard")
def lead(m):
    tops = users_col.find().sort("referrals", -1).limit(10)
    msg = "🏆 **Top 10:**\n"
    for i, u in enumerate(tops): msg += f"{i+1}. `{str(u['user_id'])[:5]}..` : {u['referrals']} Refs\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📞 Support")
def sup(m):
    msg = bot.send_message(m.chat.id, "✏️ **Message likhein:**")
    bot.register_next_step_handler(msg, lambda mm: [bot.send_message(ADMIN_ID, f"📩 **Support:** `{mm.chat.id}`\n{mm.text}\n`/reply {mm.chat.id} msg`", parse_mode="Markdown"), bot.reply_to(mm, "✅ Sent")])

@bot.message_handler(commands=['reply'])
def rep(m):
    if m.chat.id==ADMIN_ID:
        try:
            parts = m.text.split(maxsplit=2)
            bot.send_message(int(parts[1]), f"👨‍💻 **Admin:** {parts[2]}")
            bot.reply_to(m, "✅ Sent")
        except: pass

@bot.message_handler(func=lambda m: m.text == "🏦 Withdraw")
def with_req(m):
    if check_user_joined(m.chat.id):
        bot.reply_to(m, "❌ Channels Join Karein!")
        return
    if users_col.find_one({"user_id": m.chat.id}).get('balance', 0) >= MIN_WITHDRAW:
        bot.register_next_step_handler(bot.send_message(m.chat.id, "📱 **Number Bhejein:**", parse_mode="Markdown"), process_pay)
    else: bot.reply_to(m, f"❌ Min Withdraw: {MIN_WITHDRAW}")

def process_pay(m):
    try:
        uid, amt = m.chat.id, users_col.find_one({"user_id": m.chat.id})['balance']
        users_col.update_one({"user_id": uid}, {"$set": {"balance": 0}})
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"p_y_{uid}_{amt}"), types.InlineKeyboardButton("❌ Reject", callback_data=f"p_n_{uid}_{amt}"))
        bot.send_message(ADMIN_ID, f"💸 **Withdraw:** `{amt}`\n👤 User: `{uid}`\n📱 Num: `{m.text}`", reply_markup=mk, parse_mode="Markdown")
        bot.send_message(uid, "✅ Request Submitted!")
    except: pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("p_"))
def adm_act(c):
    if c.message.chat.id!=ADMIN_ID: return
    act, uid, amt = c.data.split("_")[1], int(c.data.split("_")[2]), int(c.data.split("_")[3])
    if act=="y": bot.send_message(uid, f"✅ **Paid:** {amt}"); bot.edit_message_text(f"✅ Paid {uid}", c.message.chat.id, c.message.message_id)
    else: users_col.update_one({"user_id": uid}, {"$inc": {"balance": amt}}); bot.send_message(uid, "❌ Rejected"); bot.edit_message_text(f"❌ Rejected {uid}", c.message.chat.id, c.message.message_id)

# --- ADMIN: ADD CHANNEL (UPDATED) ---

@bot.message_handler(func=lambda m: m.text == "⚙️ Add Channel")
def add_ch_ask(m):
    if m.chat.id != ADMIN_ID: return
    msg = """
🔗 **Channel Add Karein**

Format (Public):
`@Username`

Format (Private):
`ID Link Name`
Example: `-100123456 https://t.me/+Abc.. MyChannel`

👇 Details Bhejein:
"""
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")
    bot.register_next_step_handler(m, save_channel)

def save_channel(m):
    text = m.text.strip()
    
    # Logic for Public Channel (@username)
    if text.startswith("@"):
        channel_data = {
            "chat_id": text,       # @Username hi ID hai
            "link": f"https://t.me/{text.replace('@','')}",
            "name": text
        }
    
    # Logic for Private Channel (ID Link Name)
    elif text.startswith("-100"):
        try:
            parts = text.split()
            channel_data = {
                "chat_id": parts[0],  # ID (-100...)
                "link": parts[1],     # Invite Link
                "name": " ".join(parts[2:]) # Baaki bacha hua Naam
            }
        except:
            bot.reply_to(m, "❌ Galat Format! Example: `-100123 https://t.me/xx ChannelName`", parse_mode="Markdown")
            return
    else:
        bot.reply_to(m, "❌ Invalid! @ se start karo ya -100 se.")
        return

    # Database mein save karna
    channels_col.insert_one(channel_data)
    bot.reply_to(m, f"✅ **Channel Added!**\nName: {channel_data['name']}\nID: {channel_data['chat_id']}", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🗑 Delete Channel")
def del_ch_ask(m):
    if m.chat.id != ADMIN_ID: return
    bot.send_message(m.chat.id, "🗑 Channel ID ya Username bhejein delete karne ke liye:")
    bot.register_next_step_handler(m, lambda mm: [channels_col.delete_one({"chat_id": mm.text}), bot.reply_to(mm, "✅ Deleted")])

@bot.message_handler(func=lambda m: m.text == "📢 Broadcast")
def bc(m): 
    if m.chat.id==ADMIN_ID: bot.register_next_step_handler(bot.send_message(m.chat.id, "Msg?"), lambda mm: [bot.copy_message(u['user_id'], mm.chat.id, mm.message_id) for u in users_col.find({})])

keep_alive()
if API_TOKEN:
    bot.infinity_polling()
