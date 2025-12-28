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
# 1. SERVER (24/7 ALIVE)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Bot Fixed & Running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 2. CONFIG & DATABASE
# ==========================================
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['8.8.8.8']

API_TOKEN = os.environ.get('BOT_TOKEN')
MONGO_URL = os.environ.get('MONGO_URL')
# 👇 YAHAN APNA NUMBER DALEIN
ADMIN_ID = 2145958203 

try:
    client = MongoClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
    db = client['TelegramBotDB']
    users_col = db['users']
    withdraw_col = db['withdrawals']
    channels_col = db['channels']
    settings_col = db['settings']
    gift_codes_col = db['gift_codes']
except Exception as e:
    print(f"DB Error: {e}")

bot = telebot.TeleBot(API_TOKEN) if API_TOKEN else None

# --- DEFAULT SETTINGS ---
DEFAULT_EARN_MSG = """
🤩 *High Paying Tasks*

1️⃣ *Install App & Register*
💰 Reward: ₹10
🔗 (( [Click Here](https://google.com) ))

_Complete tasks to fill your wallet fast!_
"""

DEFAULT_CONFIG = {
    "refer_bonus": 3.0,
    "min_withdraw": 15.0,
    "daily_bonus": 1.0,
    "tutorial_link": "https://t.me/YourChannel",
    "earn_more_msg": DEFAULT_EARN_MSG
}

def get_setting(key):
    conf = settings_col.find_one({"_id": "config"})
    if not conf:
        settings_col.insert_one({"_id": "config", **DEFAULT_CONFIG})
        return DEFAULT_CONFIG[key]
    return conf.get(key, DEFAULT_CONFIG.get(key, ""))

def update_setting(key, value):
    settings_col.update_one({"_id": "config"}, {"$set": {key: value}}, upsert=True)

# --- HELPER FUNCTIONS ---

def get_user(user_id, first_name="User"):
    u = users_col.find_one({"user_id": user_id})
    if not u: return None
    if 'total_earned' not in u: users_col.update_one({"user_id": user_id}, {"$set": {"total_earned": 0.0}})
    return u

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
            "user_id": user_id, "balance": 0.0, "referrals": 0,
            "total_earned": 0.0, "joined_date": datetime.datetime.now(),
            "last_bonus": 0, "payout_method": "Not Set", "payout_details": "Not Set"
        })
        bonus = get_setting("refer_bonus")
        if referrer_id and referrer_id != user_id:
            users_col.update_one({"user_id": referrer_id}, {"$inc": {"balance": bonus, "referrals": 1, "total_earned": bonus}})
            try: bot.send_message(referrer_id, f"🎉 *New Referral!*\nAdded ₹{bonus}", parse_mode="Markdown")
            except: pass

# --- FORCE JOIN CHECKER ---
def send_force_join_msg(user_id):
    pending = check_joined(user_id)
    tut_link = get_setting("tutorial_link")
    
    msg = f"""
🏡 *Welcome To UPI Giveaway Bot!*

How to Earn : (( [CLICK HERE]({tut_link}) ))

🛑 *Must Join Total Channel To Use Our Bot*
👇 *After Joining Click Claim*
"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    for ch in pending:
        markup.add(types.InlineKeyboardButton(f"Join {ch['name']}", url=ch['link']))
    markup.add(types.InlineKeyboardButton("🔒 Claim Reward", callback_data="check_join"))
    
    try: bot.send_message(user_id, msg, reply_markup=markup, parse_mode="Markdown", disable_web_page_preview=True)
    except: pass

def is_verified(m):
    if check_joined(m.chat.id):
        send_force_join_msg(m.chat.id)
        return False
    return True

# ==========================================
# 3. BOT COMMANDS
# ==========================================

@bot.message_handler(commands=['start'])
def start(m):
    bot.clear_step_handler_by_chat_id(m.chat.id)
    user_id = m.chat.id
    ref_id = None
    try: ref_id = int(m.text.split()[1])
    except: pass
    
    add_new_user(user_id, ref_id)
    
    if check_joined(user_id):
        send_force_join_msg(user_id)
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
👋 *Hey There User Welcome To Bot!*

How to Earn : (( [CLICK HERE]({tut_link}) ))
"""
    try:
        bot.send_message(user_id, msg, reply_markup=markup, parse_mode="Markdown", disable_web_page_preview=True)
    except:
        bot.send_message(user_id, msg, reply_markup=markup, parse_mode=None, disable_web_page_preview=True)

# --- REFER EARN ---
@bot.message_handler(func=lambda m: m.text == "🗣 Refer Earn")
def refer(m):
    if not is_verified(m): return
    bonus = get_setting("refer_bonus")
    link = f"https://t.me/{bot.get_me().username}?start={m.chat.id}"
    msg = f"""
💰 *Per Refer Rs.{bonus} Upi Cash*

👤 *Your Refferal Link:* {link}

Share With Your Friend's & Family And Earn Refer Bonus Easily ✨🤑
"""
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✨ My Invites", callback_data="my_invites"),
               types.InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard"))
    bot.reply_to(m, msg, reply_markup=markup, disable_web_page_preview=True, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "my_invites")
def invites(c):
    u = get_user(c.message.chat.id)
    bot.answer_callback_query(c.id, f"Total Invites: {u['referrals']}", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data == "leaderboard")
def lb(c):
    tops = users_col.find().sort("referrals", -1).limit(10)
    msg = "🏆 *Top 10 Leaders*\n\n"
    for i, u in enumerate(tops): msg += f"#{i+1} (`{str(u['user_id'])[:5]}..`) - {u['referrals']} Refs\n"
    bot.send_message(c.message.chat.id, msg, parse_mode="Markdown")

# --- BALANCE ---
@bot.message_handler(func=lambda m: m.text == "💰 Balance")
def balance(m):
    if not is_verified(m): return
    u = get_user(m.chat.id)
    msg = f"💰 *Balance:* ₹{u['balance']:.2f}\n\nUse 'Withdraw' button to withdraw your balance to upi"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Withdraw History 📊", callback_data="history"))
    bot.reply_to(m, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "history")
def history(c):
    txs = list(withdraw_col.find({"user_id": c.message.chat.id}).sort("date", -1).limit(5))
    msg = "📜 *Withdraw History*\n"
    for t in txs: msg += f"₹{t['amount']} | {t['status']}\n"
    bot.send_message(c.message.chat.id, msg if txs else "No history.", parse_mode="Markdown")

# --- BONUS ---
@bot.message_handler(func=lambda m: m.text == "🎁 Bonus")
def bonus_menu(m):
    if not is_verified(m): return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📅 Daily Check-in", callback_data="daily_bonus"))
    markup.add(types.InlineKeyboardButton("🎟 Redeem Code", callback_data="redeem_code"))
    bot.reply_to(m, "🎁 *Bonus Section*", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "daily_bonus")
def claim_daily(c):
    u = get_user(c.message.chat.id)
    now = time.time()
    amt = get_setting("daily_bonus")
    if now - u.get('last_bonus', 0) > 86400:
        users_col.update_one({"user_id": c.message.chat.id}, {"$inc": {"balance": amt}, "$set": {"last_bonus": now}})
        bot.answer_callback_query(c.id, f"✅ Claimed ₹{amt}!", show_alert=True)
    else:
        bot.answer_callback_query(c.id, "⏳ Come back tomorrow!", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data == "redeem_code")
def redeem_ask(c):
    msg = bot.send_message(c.message.chat.id, "🎟 *Send Promo Code:*", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_code)

def process_code(m):
    code = m.text.strip()
    gift = gift_codes_col.find_one({"code": code})
    if gift and gift['users_used'] < gift['limit']:
        if m.chat.id not in gift['used_by']:
            users_col.update_one({"user_id": m.chat.id}, {"$inc": {"balance": gift['amount']}})
            gift_codes_col.update_one({"code": code}, {"$inc": {"users_used": 1}, "$push": {"used_by": m.chat.id}})
            bot.reply_to(m, f"✅ Added ₹{gift['amount']}")
        else: bot.reply_to(m, "❌ Already used!")
    else: bot.reply_to(m, "❌ Invalid/Expired Code")

# --- PAYOUT METHOD ---
@bot.message_handler(func=lambda m: m.text == "🏦 Payout Method")
def payout(m):
    if not is_verified(m): return
    u = get_user(m.chat.id)
    msg = f"*Choose Desired Payment Method From Below 👇*\n\nYour Current UPI - {u.get('payout_details', 'not set')}"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🏦 Set UPI ID", callback_data="set_upi"))
    bot.reply_to(m, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "set_upi")
def setupi(c):
    msg = bot.send_message(c.message.chat.id, "👇 *Send your UPI ID:*", parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_upi)

def save_upi(m):
    users_col.update_one({"user_id": m.chat.id}, {"$set": {"payout_method": "UPI", "payout_details": m.text}})
    bot.reply_to(m, "✅ UPI Set Successfully!")

# --- WITHDRAW ---
@bot.message_handler(func=lambda m: m.text == "💸 Withdraw")
def withdraw(m):
    if not is_verified(m): return
    u = get_user(m.chat.id)
    min_wd = get_setting("min_withdraw")
    
    if u['balance'] < min_wd:
        bot.reply_to(m, f"🤑 *You need minimum ₹{min_wd} in balance to withdraw*", parse_mode="Markdown")
        return
    if u.get('payout_method') == "Not Set":
        bot.reply_to(m, "❌ Set Payout Method First!")
        return
    
    users_col.update_one({"user_id": m.chat.id}, {"$set": {"balance": 0}})
    withdraw_col.insert_one({"user_id": m.chat.id, "amount": u['balance'], "details": u['payout_details'], "status": "Pending", "date": datetime.datetime.now()})
    
    mark = types.InlineKeyboardMarkup()
    mark.add(types.InlineKeyboardButton("✅ Pay", callback_data=f"py_{m.chat.id}_{u['balance']}"), types.InlineKeyboardButton("❌ Reject", callback_data=f"pn_{m.chat.id}_{u['balance']}"))
    try: bot.send_message(ADMIN_ID, f"🔔 Withdraw: ₹{u['balance']}\nUPI: `{u['payout_details']}`", reply_markup=mark, parse_mode="Markdown")
    except: pass
    bot.reply_to(m, "✅ Request Submitted.")

# --- EARN MORE (FIXED) ---
@bot.message_handler(func=lambda m: m.text == "📍 Earn More")
def earn(m):
    if not is_verified(m): return
    msg = get_setting("earn_more_msg")
    
    # Try sending with Markdown, if fail then send Normal
    try:
        bot.reply_to(m, msg, parse_mode="Markdown", disable_web_page_preview=True)
    except:
        bot.reply_to(m, msg, parse_mode=None, disable_web_page_preview=True)

# ==========================================
# 4. ADMIN PANEL (ALL FEATURES BACK)
# ==========================================

@bot.message_handler(func=lambda m: m.text == "⚙️ Admin Panel")
def admin_panel(m):
    bot.clear_step_handler_by_chat_id(m.chat.id)
    if m.chat.id != ADMIN_ID: return
    
    msg = f"""
👮‍♂️ *Full Control Panel*

Refer: ₹{get_setting('refer_bonus')} | Daily: ₹{get_setting('daily_bonus')}
Min Withdraw: ₹{get_setting('min_withdraw')}

👇 *Edit Everything Here:*
"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✏️ Refer Bonus", callback_data="adm_set_ref"),
        types.InlineKeyboardButton("✏️ Daily Bonus", callback_data="adm_set_daily"),
        types.InlineKeyboardButton("✏️ Min Withdraw", callback_data="adm_set_min"),
        types.InlineKeyboardButton("✏️ Earn Msg", callback_data="adm_set_earn"),
        types.InlineKeyboardButton("✏️ Tutorial Link", callback_data="adm_set_link"),
        types.InlineKeyboardButton("🎟 Add Code", callback_data="adm_code"),
        types.InlineKeyboardButton("➕ Add Channel", callback_data="adm_ch"),
        types.InlineKeyboardButton("🗑 Del Channel", callback_data="adm_rem"),
        types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_bc")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_"))
def admin_ops(c):
    if c.message.chat.id != ADMIN_ID: return
    op = c.data
    
    if op == "adm_set_ref":
        msg = bot.send_message(ADMIN_ID, "👇 Send New Refer Bonus (e.g. 5.0):")
        bot.register_next_step_handler(msg, lambda m: [update_setting("refer_bonus", float(m.text)), bot.reply_to(m, "✅ Updated")])

    elif op == "adm_set_daily":
        msg = bot.send_message(ADMIN_ID, "👇 Send New Daily Bonus (e.g. 1.0):")
        bot.register_next_step_handler(msg, lambda m: [update_setting("daily_bonus", float(m.text)), bot.reply_to(m, "✅ Updated")])
        
    elif op == "adm_set_min":
        msg = bot.send_message(ADMIN_ID, "👇 Send New Min Withdraw (e.g. 15):")
        bot.register_next_step_handler(msg, lambda m: [update_setting("min_withdraw", float(m.text)), bot.reply_to(m, "✅ Updated")])

    elif op == "adm_set_link":
        msg = bot.send_message(ADMIN_ID, "👇 Send New Link:")
        bot.register_next_step_handler(msg, lambda m: [update_setting("tutorial_link", m.text), bot.reply_to(m, "✅ Updated")])

    elif op == "adm_set_earn":
        msg = bot.send_message(ADMIN_ID, "👇 Send New 'Earn More' Msg (Markdown Allowed):")
        bot.register_next_step_handler(msg, lambda m: [update_setting("earn_more_msg", m.text), bot.reply_to(m, "✅ Updated")])
        
    elif op == "adm_ch":
        msg = bot.send_message(ADMIN_ID, "Send Channel:\n`@username` OR `-100ID Link Name`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, add_channel_db)
        
    elif op == "adm_rem":
        msg = bot.send_message(ADMIN_ID, "Send ID/@username to remove:")
        bot.register_next_step_handler(msg, lambda m: [channels_col.delete_one({"chat_id": m.text}), bot.reply_to(m, "✅ Removed")])

    elif op == "adm_bc":
        msg = bot.send_message(ADMIN_ID, "Send Message to Broadcast:")
        bot.register_next_step_handler(msg, lambda m: [bot.copy_message(u['user_id'], m.chat.id, m.message_id) for u in users_col.find({})])

    elif op == "adm_code":
        msg = bot.send_message(ADMIN_ID, "Send: `CODE AMOUNT LIMIT`")
        bot.register_next_step_handler(msg, add_code_db)

def add_channel_db(m):
    text = m.text
    try:
        if text.startswith("@"):
            channels_col.insert_one({"chat_id": text, "link": f"https://t.me/{text.replace('@','')}", "name": text})
        elif text.startswith("-100"):
            p = text.split()
            channels_col.insert_one({"chat_id": p[0], "link": p[1], "name": " ".join(p[2:])})
        bot.reply_to(m, "✅ Channel Added")
    except: bot.reply_to(m, "❌ Format Error")

def add_code_db(m):
    try:
        p = m.text.split()
        gift_codes_col.insert_one({"code": p[0], "amount": float(p[1]), "limit": int(p[2]), "users_used": 0, "used_by": []})
        bot.reply_to(m, "✅ Code Added")
    except: bot.reply_to(m, "❌ Format Error")

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
        try: bot.send_message(uid, "❌ Payment Rejected (Refunded)")
        except: pass

keep_alive()
if API_TOKEN:
    bot.infinity_polling()
