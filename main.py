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
    return "Pro Bot is Live!"

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

# Environment Variables se data lena
API_TOKEN = os.environ.get('BOT_TOKEN')
MONGO_URL = os.environ.get('MONGO_URL')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '1234567890'))

# Fixed Channel (Jo code me hi rahega)
MUST_JOIN_CHANNEL = '@ApnaMainChannel' 

PER_REFER_BONUS = 10
DAILY_BONUS_AMOUNT = 5
MIN_WITHDRAW = 50

try:
    if not MONGO_URL: print("❌ Error: MONGO_URL missing!")
    client = MongoClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
    db = client['TelegramBotDB']
    users_col = db['users']
    withdraw_col = db['withdrawals']
    channels_col = db['channels']
except Exception as e:
    print(f"DB Error: {e}")

if API_TOKEN:
    bot = telebot.TeleBot(API_TOKEN)
else:
    print("❌ Error: BOT_TOKEN missing!")

# --- FUNCTIONS ---

def get_all_required_channels():
    try:
        # Database wale channels + Fixed channel
        db_channels = [ch['username'] for ch in channels_col.find({})]
        all_channels = [MUST_JOIN_CHANNEL] + db_channels
        # Duplicates hata kar list banao
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
            try: 
                # PRO REFER MESSAGE
                msg = f"""
🎉 **Badhai Ho! Naya Referral Aaya Hai!**

👤 User ID: `{user_id}`
💰 Bonus: +{PER_REFER_BONUS} Points

_Aise hi invite karte rahein!_
"""
                bot.send_message(referrer_id, msg, parse_mode="Markdown")
            except: pass

# --- WELCOME & MENU ---

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
        markup.add(types.InlineKeyboardButton("✅ Maine Join Kar Liya", callback_data="check_join_status"))
        
        msg = f"""
🚧 **ACCESS DENIED** 🚧

Bot use karne ke liye aapko hamare **Sponsors Channels** join karne honge.

👇 **Niche diye gaye buttons par click karein:**
"""
        bot.send_message(user_id, msg, reply_markup=markup, parse_mode="Markdown")
    else:
        main_menu(user_id)

@bot.callback_query_handler(func=lambda c: c.data == "check_join_status")
def verify_join(c):
    if not check_user_joined(c.message.chat.id):
        bot.delete_message(c.message.chat.id, c.message.message_id)
        bot.answer_callback_query(c.id, "✅ Verification Successful!")
        main_menu(c.message.chat.id)
    else:
        bot.answer_callback_query(c.id, "❌ Aapne abhi tak join nahi kiya!", show_alert=True)

def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 Balance", "🎁 Daily Bonus")
    markup.add("👫 Refer & Earn", "🏦 Withdraw")
    markup.add("🏆 Leaderboard", "📞 Support")
    if user_id == ADMIN_ID: 
        markup.add("📢 Broadcast", "⚙️ Add Channel", "🗑 Remove Channel")
    
    msg = f"""
👋 **Namaste! Welcome to Earning Bot**

Niche diye gaye menu se option select karein aur paise kamana shuru karein! 🚀
"""
    bot.send_message(user_id, msg, reply_markup=markup, parse_mode="Markdown")

# --- FEATURES (PRO MESSAGES) ---

@bot.message_handler(func=lambda m: m.text == "💰 Balance")
def bal(m):
    d = users_col.find_one({"user_id": m.chat.id})
    if d:
        msg = f"""
💰 **WALLET DASHBOARD**

👤 **User:** {m.chat.first_name}
🆔 **User ID:** `{m.chat.id}`

💸 **Current Balance:** `{d.get('balance',0)}` Points
👥 **Total Invites:** `{d.get('referrals',0)}` Users

💡 _Aur kamane ke liye Refer karein!_
"""
        bot.reply_to(m, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎁 Daily Bonus")
def bonus(m):
    uid = m.chat.id
    d = users_col.find_one({"user_id": uid})
    now = time.time()
    if now - d.get('last_bonus', 0) > 86400:
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": DAILY_BONUS_AMOUNT}, "$set": {"last_bonus": now}})
        bot.reply_to(m, f"🎉 **Congratulations!**\n\n✅ Aapne aaj ka bonus claim kar liya hai.\n💰 **Mila:** +{DAILY_BONUS_AMOUNT} Points\n\n_Kal fir aana!_ ⏰", parse_mode="Markdown")
    else:
        bot.reply_to(m, "⏳ **Abhi nahi!**\n\nAap aaj ka bonus le chuke hain. Kripya 24 ghante baad try karein.")

@bot.message_handler(func=lambda m: m.text == "👫 Refer & Earn")
def ref(m):
    link = f"https://t.me/{bot.get_me().username}?start={m.chat.id}"
    msg = f"""
🚀 **REFER AND EARN PROGRAM**

Apne doston ko invite karein aur dher saara kamayein!

🎁 **Per Refer:** {PER_REFER_BONUS} Points
🏆 **Limits:** Unlimited

👇 **Aapka Personal Link:**
`{link}`

_Is link ko WhatsApp/Telegram groups mein share karein!_
"""
    bot.reply_to(m, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🏆 Leaderboard")
def lead(m):
    tops = users_col.find().sort("referrals", -1).limit(10)
    msg = "🏆 **TOP 10 EARNERS** 🏆\n\n"
    for i, u in enumerate(tops):
        msg += f"**#{i+1}** 🆔 `{str(u['user_id'])[:5]}..` ➖ 👥 {u['referrals']} Refs\n"
    bot.send_message(m.chat.id, msg, parse_mode="Markdown")

# --- SUPPORT & WITHDRAW ---

@bot.message_handler(func=lambda m: m.text == "📞 Support")
def sup(m):
    msg = bot.send_message(m.chat.id, "✏️ **Humein Likh Kar Bhejein:**\n\nApni samasya ya sawal niche likhein, Admin jald hi reply karenge.", parse_mode="Markdown")
    bot.register_next_step_handler(msg, lambda mm: [bot.send_message(ADMIN_ID, f"📩 **SUPPORT MESSAGE**\nUser: `{mm.chat.id}`\n\nMsg: {mm.text}\n\nReply Cmd: `/reply {mm.chat.id} msg`", parse_mode="Markdown"), bot.reply_to(mm, "✅ **Message Sent!**\nHum jald hi aapse sampark karenge.")])

@bot.message_handler(commands=['reply'])
def rep(m):
    if m.chat.id==ADMIN_ID:
        try:
            parts = m.text.split(maxsplit=2)
            bot.send_message(int(parts[1]), f"👨‍💻 **ADMIN REPLY:**\n\n{parts[2]}", parse_mode="Markdown")
            bot.reply_to(m, "✅ Reply Sent!")
        except: pass

@bot.message_handler(func=lambda m: m.text == "🏦 Withdraw")
def with_req(m):
    if check_user_joined(m.chat.id):
        bot.reply_to(m, "❌ **Error!**\nAapne Channels leave kar diye hain. Withdraw ke liye wapis join karein.")
        return
    bal = users_col.find_one({"user_id": m.chat.id}).get('balance', 0)
    if bal >= MIN_WITHDRAW:
        msg = f"💳 **WITHDRAWAL REQUEST**\n\n💰 Aapka Balance: {bal}\n👇 Apna Paytm/UPI Number niche likh kar bhejein:"
        bot.register_next_step_handler(bot.send_message(m.chat.id, msg, parse_mode="Markdown"), process_pay)
    else: 
        bot.reply_to(m, f"❌ **Low Balance!**\n\nKam se kam `{MIN_WITHDRAW}` Points hone chahiye withdraw karne ke liye.", parse_mode="Markdown")

def process_pay(m):
    try:
        uid, amt = m.chat.id, users_col.find_one({"user_id": m.chat.id})['balance']
        users_col.update_one({"user_id": uid}, {"$set": {"balance": 0}})
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"p_y_{uid}_{amt}"), types.InlineKeyboardButton("❌ Reject", callback_data=f"p_n_{uid}_{amt}"))
        bot.send_message(ADMIN_ID, f"🔔 **NEW WITHDRAWAL**\n\n👤 User: `{uid}`\n💰 Amount: `{amt}`\n📱 Number: `{m.text}`", reply_markup=mk, parse_mode="Markdown")
        bot.send_message(uid, "✅ **Request Submitted!**\n\nAdmin verify karke jald hi payment bhejenge.")
    except: pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("p_"))
def adm_act(c):
    if c.message.chat.id!=ADMIN_ID: return
    act, uid, amt = c.data.split("_")[1], int(c.data.split("_")[2]), int(c.data.split("_")[3])
    if act=="y": 
        bot.send_message(uid, f"✅ **PAYMENT SUCCESSFUL!**\n\nBadhai ho! Aapka `{amt}` Points ka withdrawal approve ho gaya hai.", parse_mode="Markdown")
        bot.edit_message_text(f"✅ Paid `{uid}` - `{amt}`", c.message.chat.id, c.message.message_id, parse_mode="Markdown")
    else: 
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": amt}})
        bot.send_message(uid, f"❌ **PAYMENT REJECTED**\n\nAapka withdrawal cancel kar diya gaya hai aur points wapis add kar diye gaye hain.", parse_mode="Markdown")
        bot.edit_message_text(f"❌ Rejected `{uid}`", c.message.chat.id, c.message.message_id, parse_mode="Markdown")

# --- ADMIN CHANNEL COMMANDS (Buttons walay) ---

@bot.message_handler(func=lambda m: m.text == "⚙️ Add Channel")
def ac_btn(m): 
    if m.chat.id==ADMIN_ID: 
        msg = bot.send_message(m.chat.id, "🔗 **Naya Channel Add Karein**\n\nChannel ka username bhejein (Example: @MyChannel)\n\n_Note: Bot ko wahan Admin banana zaruri hai._", parse_mode="Markdown")
        bot.register_next_step_handler(msg, add_channel_db)

def add_channel_db(m):
    if m.text.startswith("@"):
        channels_col.insert_one({"username": m.text})
        bot.reply_to(m, f"✅ Channel `{m.text}` safalta purvak add ho gaya!", parse_mode="Markdown")
    else:
        bot.reply_to(m, "❌ Error: Username '@' se shuru hona chahiye.")

@bot.message_handler(func=lambda m: m.text == "🗑 Remove Channel")
def rc_btn(m): 
    if m.chat.id==ADMIN_ID: 
        msg = bot.send_message(m.chat.id, "🗑 **Channel Remove Karein**\n\nKaunsa channel hatana hai? Username bhejein:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, rem_channel_db)

def rem_channel_db(m):
    channels_col.delete_one({"username": m.text})
    bot.reply_to(m, f"✅ Channel `{m.text}` delete kar diya gaya.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📢 Broadcast")
def bc(m): 
    if m.chat.id==ADMIN_ID: bot.register_next_step_handler(bot.send_message(m.chat.id, "📢 **Broadcast Message Bhejein:**", parse_mode="Markdown"), lambda mm: [bot.copy_message(u['user_id'], mm.chat.id, mm.message_id) for u in users_col.find({})])

keep_alive()
if API_TOKEN:
    bot.infinity_polling()
