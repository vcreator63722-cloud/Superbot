import telebot
from telebot import types
from pymongo import MongoClient
import time
import datetime
import dns.resolver
from flask import Flask
from threading import Thread
import os

# ==========================================
# 1. SERVER (24/7 Alive)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Professional Bot Live!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 2. DATABASE & CONFIG
# ==========================================
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8']

API_TOKEN = os.environ.get('BOT_TOKEN')
MONGO_URL = os.environ.get('MONGO_URL')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '1234567890'))

try:
    client = MongoClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
    db = client['TelegramBotDB']
    users_col = db['users']
    withdraw_col = db['withdrawals']
    channels_col = db['channels']
    settings_col = db['settings'] # Naya: Settings save karne ke liye
except Exception as e:
    print(f"DB Error: {e}")

bot = telebot.TeleBot(API_TOKEN) if API_TOKEN else None

# --- DEFAULT SETTINGS (Agar DB me nahi hai to ye use honge) ---
DEFAULT_CONFIG = {
    "refer_bonus": 5.0,
    "min_withdraw": 15.0,
    "daily_bonus": 1.0,
    "tutorial_link": "https://t.me/YourChannel", # How to earn link
    "currency": "₹"
}

def get_setting(key):
    conf = settings_col.find_one({"_id": "config"})
    if not conf:
        settings_col.insert_one({"_id": "config", **DEFAULT_CONFIG})
        return DEFAULT_CONFIG[key]
    return conf.get(key, DEFAULT_CONFIG[key])

def update_setting(key, value):
    settings_col.update_one({"_id": "config"}, {"$set": {key: value}}, upsert=True)

# --- HELPER FUNCTIONS ---

def get_user(user_id):
    return users_col.find_one({"user_id": user_id})

def check_joined(user_id):
    channels = list(channels_col.find({}))
    not_joined = []
    for ch in channels:
        try:
            status = bot.get_chat_member(ch['chat_id'], user_id).status
            if status not in ['creator', 'administrator', 'member']:
                not_joined.append(ch)
        except: pass
    return not_joined

def add_new_user(user_id, referrer_id=None):
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({
            "user_id": user_id,
            "balance": 0.0,
            "referrals": 0,
            "joined_date": datetime.datetime.now(),
            "last_bonus": 0,
            "payout_method": "Not Set",
            "payout_details": "Not Set"
        })
        # Refer Logic
        bonus = get_setting("refer_bonus")
        if referrer_id and referrer_id != user_id:
            users_col.update_one({"user_id": referrer_id}, {"$inc": {"balance": bonus, "referrals": 1}})
            try: bot.send_message(referrer_id, f"🎉 **New Referral!**\nYou earned ₹{bonus}", parse_mode="Markdown")
            except: pass

# ==========================================
# 3. BOT FLOW
# ==========================================

@bot.message_handler(commands=['start'])
def start(m):
    user_id = m.chat.id
    ref_id = None
    try: ref_id = int(m.text.split()[1])
    except: pass
    
    add_new_user(user_id, ref_id)
    
    # Text aur Link Database se aayega
    tut_link = get_setting("tutorial_link")
    
    pending = check_joined(user_id)
    if pending:
        # EXACT TEXT JO AAPNE MANGA
        msg = f"""
🏡 **Welcome To UPI Giveaway Bot!**

How to Earn : (( [CLICK HERE]({tut_link}) ))

🛑 **Must Join Total Channel To Use Our Bot**
👇 **After Joining Click Claim**
"""
        markup = types.InlineKeyboardMarkup(row_width=2)
        for ch in pending:
            markup.add(types.InlineKeyboardButton(f"Join {ch['name']}", url=ch['link']))
        markup.add(types.InlineKeyboardButton("🔒 Claim Reward", callback_data="check_join"))
        
        # Link preview disable taki message clean dikhe
        bot.send_message(user_id, msg, reply_markup=markup, parse_mode="Markdown", disable_web_page_preview=True)
    else:
        main_menu(user_id)

@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def check_join_btn(c):
    if not check_joined(c.message.chat.id):
        bot.delete_message(c.message.chat.id, c.message.message_id)
        bot.answer_callback_query(c.id, "✅ Verified!", show_alert=False)
        main_menu(c.message.chat.id)
    else:
        bot.answer_callback_query(c.id, "❌ Join all channels first!", show_alert=True)

def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 Balance", "🗣 Refer Earn")
    markup.add("🎁 Bonus", "💸 Withdraw")
    markup.add("🏦 Payout Method", "📍 Earn More")
    
    if user_id == ADMIN_ID: markup.add("⚙️ Admin Panel")
    
    tut_link = get_setting("tutorial_link")
    msg = f"""
👋 **Hey There User Welcome To Bot!**

How to Earn : (( [CLICK HERE]({tut_link}) ))
"""
    bot.send_message(user_id, msg, reply_markup=markup, parse_mode="Markdown", disable_web_page_preview=True)

# --- REFER EARN (EXACT TEXT) ---
@bot.message_handler(func=lambda m: m.text == "🗣 Refer Earn")
def refer(m):
    bonus = get_setting("refer_bonus")
    link = f"https://t.me/{bot.get_me().username}?start={m.chat.id}"
    
    # EXACT TEXT JO AAPNE MANGA
    msg = f"""
💰 **Per Refer Rs.{bonus} Upi Cash**

👤 **Your Refferal Link:** {link}

Share With Your Friend's & Family And Earn Refer Bonus Easily ✨🤑
"""
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✨ My Invites", callback_data="my_invites"),
               types.InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard"))
    
    bot.reply_to(m, msg, reply_markup=markup, disable_web_page_preview=True)

@bot.callback_query_handler(func=lambda c: c.data == "my_invites")
def invites(c):
    u = get_user(c.message.chat.id)
    bot.answer_callback_query(c.id, f"Total Invites: {u['referrals']}", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data == "leaderboard")
def lb(c):
    tops = users_col.find().sort("referrals", -1).limit(10)
    msg = "🏆 **Leaderboard**\n"
    for i, u in enumerate(tops): msg += f"#{i+1} - {u['referrals']} Refs\n"
    bot.send_message(c.message.chat.id, msg)

# --- BALANCE ---
@bot.message_handler(func=lambda m: m.text == "💰 Balance")
def balance(m):
    u = get_user(m.chat.id)
    msg = f"💰 **Balance:** ₹{u['balance']:.2f}\n\nUse 'Withdraw' button to withdraw your balance to upi"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Withdraw History 📊", callback_data="history"))
    bot.reply_to(m, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "history")
def history(c):
    txs = list(withdraw_col.find({"user_id": c.message.chat.id}).sort("date", -1).limit(5))
    msg = "📜 **Withdraw History**\n"
    for t in txs: msg += f"₹{t['amount']} | {t['status']}\n"
    bot.send_message(c.message.chat.id, msg if txs else "No history.")

# --- BONUS ---
@bot.message_handler(func=lambda m: m.text == "🎁 Bonus")
def bonus(m):
    u = get_user(m.chat.id)
    now = time.time()
    amt = get_setting("daily_bonus")
    if now - u.get('last_bonus', 0) > 86400:
        users_col.update_one({"user_id": m.chat.id}, {"$inc": {"balance": amt}, "$set": {"last_bonus": now}})
        bot.reply_to(m, f"✅ **Daily Bonus Claimed!**\nReceived ₹{amt}")
    else:
        bot.reply_to(m, "⏳ Come back tomorrow!")

# --- PAYOUT METHOD ---
@bot.message_handler(func=lambda m: m.text == "🏦 Payout Method")
def payout(m):
    u = get_user(m.chat.id)
    msg = f"**Choose Desired Payment Method From Below 👇**\n\nYour Current UPI - {u.get('payout_details', 'not set')}"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🏦 Set UPI ID", callback_data="set_upi"))
    bot.reply_to(m, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "set_upi")
def setupi(c):
    msg = bot.send_message(c.message.chat.id, "👇 **Send your UPI ID:**")
    bot.register_next_step_handler(msg, save_upi)

def save_upi(m):
    users_col.update_one({"user_id": m.chat.id}, {"$set": {"payout_method": "UPI", "payout_details": m.text}})
    bot.reply_to(m, "✅ UPI Set Successfully!")

# --- WITHDRAW ---
@bot.message_handler(func=lambda m: m.text == "💸 Withdraw")
def withdraw(m):
    u = get_user(m.chat.id)
    min_wd = get_setting("min_withdraw")
    
    if u['balance'] < min_wd:
        bot.reply_to(m, f"🤑 **You need minimum ₹{min_wd} in balance to withdraw**")
        return
    if u.get('payout_method') == "Not Set":
        bot.reply_to(m, "❌ Set Payout Method First!")
        return
    
    users_col.update_one({"user_id": m.chat.id}, {"$set": {"balance": 0}})
    withdraw_col.insert_one({"user_id": m.chat.id, "amount": u['balance'], "details": u['payout_details'], "status": "Pending", "date": datetime.datetime.now()})
    
    mark = types.InlineKeyboardMarkup()
    mark.add(types.InlineKeyboardButton("✅ Pay", callback_data=f"py_{m.chat.id}_{u['balance']}"), types.InlineKeyboardButton("❌ Reject", callback_data=f"pn_{m.chat.id}_{u['balance']}"))
    bot.send_message(ADMIN_ID, f"🔔 Withdraw: ₹{u['balance']}\nUPI: `{u['payout_details']}`", reply_markup=mark, parse_mode="Markdown")
    bot.reply_to(m, "✅ Request Submitted.")

# --- EARN MORE ---
@bot.message_handler(func=lambda m: m.text == "📍 Earn More")
def earn(m):
    tut_link = get_setting("tutorial_link")
    msg = f"🤩 **Free Loots & Offers**\n\n(( [CLICK HERE]({tut_link}) ))"
    bot.reply_to(m, msg, parse_mode="Markdown", disable_web_page_preview=True)

# ==========================================
# 4. ADMIN PANEL (MANAGE EVERYTHING)
# ==========================================

@bot.message_handler(func=lambda m: m.text == "⚙️ Admin Panel")
def admin(m):
    if m.chat.id != ADMIN_ID: return
    
    msg = f"""
👮‍♂️ **Boss Panel**

Current Settings:
💰 Refer Bonus: ₹{get_setting('refer_bonus')}
💸 Min Withdraw: ₹{get_setting('min_withdraw')}
🔗 Link: {get_setting('tutorial_link')}

👇 **Select what to change:**
"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✏️ Set Refer Bonus", callback_data="set_ref"),
        types.InlineKeyboardButton("✏️ Set Min Withdraw", callback_data="set_min"),
        types.InlineKeyboardButton("✏️ Set Link", callback_data="set_link"),
        types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_bc"),
        types.InlineKeyboardButton("➕ Add Channel", callback_data="adm_ch"),
        types.InlineKeyboardButton("🗑 Remove Channel", callback_data="adm_rem")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, disable_web_page_preview=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_") or c.data.startswith("set_"))
def admin_ops(c):
    if c.message.chat.id != ADMIN_ID: return
    op = c.data
    
    if op == "set_ref":
        msg = bot.send_message(ADMIN_ID, "👇 Send New Refer Bonus Amount (e.g. 10):")
        bot.register_next_step_handler(msg, lambda m: [update_setting("refer_bonus", float(m.text)), bot.reply_to(m, "✅ Updated")])
        
    elif op == "set_min":
        msg = bot.send_message(ADMIN_ID, "👇 Send New Min Withdraw Amount (e.g. 50):")
        bot.register_next_step_handler(msg, lambda m: [update_setting("min_withdraw", float(m.text)), bot.reply_to(m, "✅ Updated")])
        
    elif op == "set_link":
        msg = bot.send_message(ADMIN_ID, "👇 Send New 'How to Earn' Link:")
        bot.register_next_step_handler(msg, lambda m: [update_setting("tutorial_link", m.text), bot.reply_to(m, "✅ Updated")])
        
    elif op == "adm_ch":
        msg = bot.send_message(ADMIN_ID, "Send Channel: `@username` OR `-100ID Link Name`")
        bot.register_next_step_handler(msg, add_channel_db)
        
    elif op == "adm_rem":
        msg = bot.send_message(ADMIN_ID, "Send ID/@username to remove:")
        bot.register_next_step_handler(msg, lambda m: [channels_col.delete_one({"chat_id": m.text}), bot.reply_to(m, "✅ Removed")])

    elif op == "adm_bc":
        msg = bot.send_message(ADMIN_ID, "Send Message to Broadcast:")
        bot.register_next_step_handler(msg, lambda m: [bot.copy_message(u['user_id'], m.chat.id, m.message_id) for u in users_col.find({})])

def add_channel_db(m):
    text = m.text
    if text.startswith("@"):
        channels_col.insert_one({"chat_id": text, "link": f"https://t.me/{text.replace('@','')}", "name": text})
    elif text.startswith("-100"):
        p = text.split()
        channels_col.insert_one({"chat_id": p[0], "link": p[1], "name": " ".join(p[2:])})
    bot.reply_to(m, "✅ Channel Added")

# Admin Pay Logic
@bot.callback_query_handler(func=lambda c: c.data.startswith("py_") or c.data.startswith("pn_"))
def pay_logic(c):
    if c.message.chat.id != ADMIN_ID: return
    act, uid, amt = c.data[:2], int(c.data.split("_")[1]), float(c.data.split("_")[2])
    if act == "py":
        withdraw_col.update_one({"user_id": uid, "status": "Pending"}, {"$set": {"status": "Paid"}})
        bot.edit_message_text(f"✅ Paid {uid}", c.message.chat.id, c.message.message_id)
        try: bot.send_message(uid, f"✅ Payment Received: ₹{amt}")
        except: pass
    else:
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": amt}})
        withdraw_col.update_one({"user_id": uid, "status": "Pending"}, {"$set": {"status": "Rejected"}})
        bot.edit_message_text(f"❌ Rejected {uid}", c.message.chat.id, c.message.message_id)
        try: bot.send_message(uid, "❌ Payment Rejected. Refunded.")
        except: pass

keep_alive()
if API_TOKEN:
    bot.infinity_polling()
