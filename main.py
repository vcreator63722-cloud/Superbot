import telebot
from telebot import types
from pymongo import MongoClient
import time
import datetime
import dns.resolver
from flask import Flask
from threading import Thread
import os
import random

# ==========================================
# 1. SERVER (24/7 Alive)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Premium Bot is Live!"

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
    settings_col = db['settings']
    gift_codes_col = db['gift_codes'] # Wapis aa gaya
except Exception as e:
    print(f"DB Error: {e}")

bot = telebot.TeleBot(API_TOKEN) if API_TOKEN else None

# --- DEFAULT SETTINGS ---
DEFAULT_CONFIG = {
    "refer_bonus": 5.0,
    "min_withdraw": 15.0,
    "daily_bonus": 1.0,
    "tutorial_link": "https://t.me/YourChannel",
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
    u = users_col.find_one({"user_id": user_id})
    if not u: return None
    # Auto-Repair for old users
    if 'total_earned' not in u: users_col.update_one({"user_id": user_id}, {"$set": {"total_earned": 0.0}})
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
            "total_earned": 0.0,
            "joined_date": datetime.datetime.now(),
            "last_bonus": 0,
            "payout_method": "Not Set",
            "payout_details": "Not Set"
        })
        # Refer Logic
        bonus = get_setting("refer_bonus")
        if referrer_id and referrer_id != user_id:
            users_col.update_one({"user_id": referrer_id}, {
                "$inc": {"balance": bonus, "referrals": 1, "total_earned": bonus}
            })
            try: bot.send_message(referrer_id, f"🎉 **New Referral!**\nUser joined via your link.\n➕ Added: ₹{bonus}", parse_mode="Markdown")
            except: pass

# ==========================================
# 3. BOT FLOW (PREMIUM UI)
# ==========================================

@bot.message_handler(commands=['start'])
def start(m):
    user_id = m.chat.id
    ref_id = None
    try: ref_id = int(m.text.split()[1])
    except: pass
    
    add_new_user(user_id, ref_id)
    tut_link = get_setting("tutorial_link")
    
    pending = check_joined(user_id)
    if pending:
        msg = f"""
👋 **Hello {m.chat.first_name}!**

Welcome to the **Premium Rewards Bot**. 
To start earning, you must complete the steps below.

🛑 **REQUIRED: Join Channels**
_Click the buttons below to join:_
"""
        markup = types.InlineKeyboardMarkup(row_width=2)
        for ch in pending:
            markup.add(types.InlineKeyboardButton(f"🔔 Join {ch['name']}", url=ch['link']))
        markup.add(types.InlineKeyboardButton("✅ I Have Joined", callback_data="check_join"))
        
        bot.send_message(user_id, msg, reply_markup=markup, parse_mode="Markdown")
    else:
        main_menu(user_id)

@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def check_join_btn(c):
    if not check_joined(c.message.chat.id):
        bot.delete_message(c.message.chat.id, c.message.message_id)
        bot.answer_callback_query(c.id, "✅ Verification Success!", show_alert=False)
        main_menu(c.message.chat.id)
    else:
        bot.answer_callback_query(c.id, "❌ You must join ALL channels first!", show_alert=True)

def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 Balance", "🗣 Refer Earn")
    markup.add("🎁 Bonus", "💸 Withdraw")
    markup.add("🏦 Payout Method", "📍 Earn More")
    
    if user_id == ADMIN_ID: markup.add("⚙️ Admin Panel")
    
    tut_link = get_setting("tutorial_link")
    msg = f"""
🏡 **Main Dashboard**
━━━━━━━━━━━━━━━━━━━
👋 Welcome back!
🆔 **User ID:** `{user_id}`

💡 **How to Earn?**
(( [Click Here for Tutorial]({tut_link}) ))

👇 _Select an option from the menu:_
"""
    bot.send_message(user_id, msg, reply_markup=markup, parse_mode="Markdown", disable_web_page_preview=True)

# --- REFER EARN (PREMIUM LOOK) ---
@bot.message_handler(func=lambda m: m.text == "🗣 Refer Earn")
def refer(m):
    bonus = get_setting("refer_bonus")
    link = f"https://t.me/{bot.get_me().username}?start={m.chat.id}"
    
    msg = f"""
🚀 **REFERRAL PROGRAM**
━━━━━━━━━━━━━━━━━━━
invite your friends and earn unlimited cash!

💰 **Per Refer:** `₹{bonus}`
🏆 **Limit:** Unlimited

🔗 **Your Unique Link:**
`{link}`

_Tap the link to copy and share!_
"""
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("👥 My Team Stats", callback_data="my_invites"),
               types.InlineKeyboardButton("🏆 Top Leaderboard", callback_data="leaderboard"))
    
    bot.reply_to(m, msg, reply_markup=markup, disable_web_page_preview=True, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "my_invites")
def invites(c):
    u = get_user(c.message.chat.id)
    bot.answer_callback_query(c.id, f"👥 Total Referrals: {u['referrals']}", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data == "leaderboard")
def lb(c):
    tops = users_col.find().sort("referrals", -1).limit(10)
    msg = "🏆 **TOP 10 LEADERS** 🏆\n━━━━━━━━━━━━━━━━\n"
    for i, u in enumerate(tops): msg += f"**#{i+1}** 🆔 `{str(u['user_id'])[:4]}..` : **{u['referrals']}** Refs\n"
    bot.send_message(c.message.chat.id, msg, parse_mode="Markdown")

# --- BALANCE (PREMIUM LOOK) ---
@bot.message_handler(func=lambda m: m.text == "💰 Balance")
def balance(m):
    u = get_user(m.chat.id)
    msg = f"""
💰 **WALLET DASHBOARD**
━━━━━━━━━━━━━━━━━━━
👤 **User:** {m.chat.first_name}
🆔 **ID:** `{m.chat.id}`

💵 **Current Balance:** `₹{u['balance']:.2f}`
📈 **Lifetime Earnings:** `₹{u.get('total_earned', 0):.2f}`

_Withdraw your earnings instantly to UPI._
"""
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📜 Transaction History", callback_data="history"))
    markup.add(types.InlineKeyboardButton("🌍 Global Stats", callback_data="global_stats"))
    bot.reply_to(m, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "history")
def history(c):
    txs = list(withdraw_col.find({"user_id": c.message.chat.id}).sort("date", -1).limit(5))
    msg = "📜 **Recent Transactions**\n━━━━━━━━━━━━━━━━\n"
    for t in txs: 
        status = "✅" if t['status']=="Paid" else "⏳" if t['status']=="Pending" else "❌"
        msg += f"{status} **₹{t['amount']}** | {t['status']}\n"
    bot.send_message(c.message.chat.id, msg if txs else "🚫 No transaction history found.", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "global_stats")
def g_stats(c):
    total_u = users_col.count_documents({})
    total_w = withdraw_col.count_documents({"status": "Paid"})
    fake_fund = 50000 + (total_u * 10)
    msg = f"🌍 **LIVE BOT STATS**\n\n👥 Total Users: `{total_u}`\n💸 Successful Payouts: `{total_w}`\n🏦 Bot Treasury: `₹{fake_fund:,.2f}`"
    bot.send_message(c.message.chat.id, msg, parse_mode="Markdown")

# --- BONUS SECTION (Daily + Redeem Code) ---
@bot.message_handler(func=lambda m: m.text == "🎁 Bonus")
def bonus_menu(m):
    msg = "🎁 **Bonus Area**\nSelect an option to claim free rewards!"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📅 Daily Check-in", callback_data="daily_bonus"))
    markup.add(types.InlineKeyboardButton("🎟 Redeem Gift Code", callback_data="redeem_code"))
    bot.reply_to(m, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "daily_bonus")
def claim_daily(c):
    u = get_user(c.message.chat.id)
    now = time.time()
    amt = get_setting("daily_bonus")
    if now - u.get('last_bonus', 0) > 86400:
        users_col.update_one({"user_id": c.message.chat.id}, {"$inc": {"balance": amt, "total_earned": amt}, "$set": {"last_bonus": now}})
        bot.answer_callback_query(c.id, f"✅ Success! ₹{amt} added.", show_alert=True)
    else:
        bot.answer_callback_query(c.id, "⏳ Come back tomorrow!", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data == "redeem_code")
def redeem_ask(c):
    msg = bot.send_message(c.message.chat.id, "🎟 **Enter your Promo Code:**\n_(Type the code below)_")
    bot.register_next_step_handler(msg, process_code)

def process_code(m):
    code = m.text.strip()
    gift = gift_codes_col.find_one({"code": code})
    if gift and gift['users_used'] < gift['limit']:
        if m.chat.id not in gift['used_by']:
            users_col.update_one({"user_id": m.chat.id}, {"$inc": {"balance": gift['amount'], "total_earned": gift['amount']}})
            gift_codes_col.update_one({"code": code}, {"$inc": {"users_used": 1}, "$push": {"used_by": m.chat.id}})
            bot.reply_to(m, f"🎉 **Code Redeemed!**\nAdded ₹{gift['amount']} to your wallet.")
        else: bot.reply_to(m, "❌ You have already used this code!")
    else: bot.reply_to(m, "❌ Invalid or Expired Code.")

# --- PAYOUT METHOD ---
@bot.message_handler(func=lambda m: m.text == "🏦 Payout Method")
def payout(m):
    u = get_user(m.chat.id)
    msg = f"""
💳 **Payment Settings**
━━━━━━━━━━━━━━━━━━━
Status: **{u.get('payout_method', 'Not Set')}**
Details: `{u.get('payout_details', 'Not Set')}`

_Click below to update your payment info._
"""
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🏦 Set UPI ID", callback_data="set_upi"),
               types.InlineKeyboardButton("📧 Set Email/Paytm", callback_data="set_paytm"))
    bot.reply_to(m, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("set_"))
def set_pay_method(c):
    m_type = "UPI" if "upi" in c.data else "Paytm/Email"
    msg = bot.send_message(c.message.chat.id, f"👇 **Enter your {m_type}:**")
    bot.register_next_step_handler(msg, lambda m: save_pay_details(m, m_type))

def save_pay_details(m, m_type):
    users_col.update_one({"user_id": m.chat.id}, {"$set": {"payout_method": m_type, "payout_details": m.text}})
    bot.reply_to(m, f"✅ **Saved Successfully!**\nMethod: {m_type}\nDetails: {m.text}")

# --- WITHDRAW ---
@bot.message_handler(func=lambda m: m.text == "💸 Withdraw")
def withdraw(m):
    u = get_user(m.chat.id)
    min_wd = get_setting("min_withdraw")
    
    if u['balance'] < min_wd:
        bot.reply_to(m, f"⚠️ **Insufficient Balance**\nMinimum Withdraw: `₹{min_wd}`\nYour Balance: `₹{u['balance']:.2f}`", parse_mode="Markdown")
        return
    if u.get('payout_method') == "Not Set":
        bot.reply_to(m, "❌ **Payment Details Missing!**\nPlease go to 'Payout Method' and set your ID.")
        return
    
    amount = u['balance']
    users_col.update_one({"user_id": m.chat.id}, {"$set": {"balance": 0}})
    withdraw_col.insert_one({"user_id": m.chat.id, "amount": amount, "details": u['payout_details'], "status": "Pending", "date": datetime.datetime.now()})
    
    # Notify Admin
    mark = types.InlineKeyboardMarkup()
    mark.add(types.InlineKeyboardButton("✅ Pay", callback_data=f"py_{m.chat.id}_{amount}"), types.InlineKeyboardButton("❌ Reject", callback_data=f"pn_{m.chat.id}_{amount}"))
    bot.send_message(ADMIN_ID, f"🔔 **New Withdrawal**\nUser: `{m.chat.id}`\nAmt: ₹{amount}\nDetails: `{u['payout_details']}`", reply_markup=mark, parse_mode="Markdown")
    
    bot.reply_to(m, f"✅ **Request Submitted!**\nAmount: ₹{amount}\nStatus: Pending\n\n_We will process it shortly._", parse_mode="Markdown")

# --- EARN MORE ---
@bot.message_handler(func=lambda m: m.text == "📍 Earn More")
def earn(m):
    tut_link = get_setting("tutorial_link")
    msg = f"""
🤩 **High Paying Tasks**

1️⃣ **Install App & Register**
💰 Reward: ₹10
🔗 (( [Click Here]({tut_link}) ))

2️⃣ **Subscribe YouTube**
💰 Reward: ₹5
🔗 (( [Click Here]({tut_link}) ))

_Complete tasks to fill your wallet fast!_
"""
    bot.reply_to(m, msg, parse_mode="Markdown", disable_web_page_preview=True)

# ==========================================
# 4. ADMIN PANEL (FULL CONTROL)
# ==========================================

@bot.message_handler(func=lambda m: m.text == "⚙️ Admin Panel")
def admin(m):
    if m.chat.id != ADMIN_ID: return
    
    msg = f"""
👮‍♂️ **ADMIN CONTROL PANEL**
━━━━━━━━━━━━━━━━━━━
💰 Refer Bonus: ₹{get_setting('refer_bonus')}
💸 Min Withdraw: ₹{get_setting('min_withdraw')}
🎁 Daily Bonus: ₹{get_setting('daily_bonus')}

👇 **Tap to Edit:**
"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✏️ Refer Bonus", callback_data="set_ref"),
        types.InlineKeyboardButton("✏️ Min Withdraw", callback_data="set_min"),
        types.InlineKeyboardButton("✏️ Daily Bonus", callback_data="set_daily"),
        types.InlineKeyboardButton("✏️ Tutorial Link", callback_data="set_link"),
        types.InlineKeyboardButton("🎟 Add Gift Code", callback_data="adm_code"),
        types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_bc"),
        types.InlineKeyboardButton("➕ Add Channel", callback_data="adm_ch"),
        types.InlineKeyboardButton("🗑 Remove Channel", callback_data="adm_rem")
    )
    bot.send_message(m.chat.id, msg, reply_markup=markup, disable_web_page_preview=True, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_") or c.data.startswith("set_"))
def admin_ops(c):
    if c.message.chat.id != ADMIN_ID: return
    op = c.data
    
    prompts = {
        "set_ref": ("Refer Bonus", "refer_bonus", float),
        "set_min": ("Min Withdraw", "min_withdraw", float),
        "set_daily": ("Daily Bonus", "daily_bonus", float),
        "set_link": ("Link", "tutorial_link", str)
    }

    if op in prompts:
        name, key, dtype = prompts[op]
        msg = bot.send_message(ADMIN_ID, f"👇 Send new **{name}** value:")
        bot.register_next_step_handler(msg, lambda m: update_conf(m, key, dtype))
        
    elif op == "adm_ch":
        msg = bot.send_message(ADMIN_ID, "Send Channel:\n`@username` OR `-100ID Link Name`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, add_channel_db)
    
    elif op == "adm_rem":
        msg = bot.send_message(ADMIN_ID, "Send Channel ID or Username to remove:")
        bot.register_next_step_handler(msg, lambda m: [channels_col.delete_one({"chat_id": m.text}), bot.reply_to(m, "✅ Removed")])

    elif op == "adm_code":
        msg = bot.send_message(ADMIN_ID, "Send format: `CODE AMOUNT LIMIT`\nExample: `DIWALI 10 100`")
        bot.register_next_step_handler(msg, add_code_db)

    elif op == "adm_bc":
        msg = bot.send_message(ADMIN_ID, "Send Message to Broadcast:")
        bot.register_next_step_handler(msg, lambda m: [bot.copy_message(u['user_id'], m.chat.id, m.message_id) for u in users_col.find({})])

def update_conf(m, key, dtype):
    try:
        val = dtype(m.text)
        update_setting(key, val)
        bot.reply_to(m, "✅ Settings Updated!")
    except: bot.reply_to(m, "❌ Invalid Value")

def add_channel_db(m):
    text = m.text
    try:
        if text.startswith("@"):
            channels_col.insert_one({"chat_id": text, "link": f"https://t.me/{text.replace('@','')}", "name": text})
        elif text.startswith("-100"):
            p = text.split()
            channels_col.insert_one({"chat_id": p[0], "link": p[1], "name": " ".join(p[2:])})
        bot.reply_to(m, "✅ Channel Added Successfully")
    except: bot.reply_to(m, "❌ Error in format")

def add_code_db(m):
    try:
        p = m.text.split()
        gift_codes_col.insert_one({"code": p[0], "amount": float(p[1]), "limit": int(p[2]), "users_used": 0, "used_by": []})
        bot.reply_to(m, f"✅ Code Created: `{p[0]}` for ₹{p[1]}")
    except: bot.reply_to(m, "❌ Error format")

# Admin Pay Logic
@bot.callback_query_handler(func=lambda c: c.data.startswith("py_") or c.data.startswith("pn_"))
def pay_logic(c):
    if c.message.chat.id != ADMIN_ID: return
    act, uid, amt = c.data[:2], int(c.data.split("_")[1]), float(c.data.split("_")[2])
    if act == "py":
        withdraw_col.update_one({"user_id": uid, "status": "Pending"}, {"$set": {"status": "Paid"}})
        bot.edit_message_text(f"✅ Paid {uid}", c.message.chat.id, c.message.message_id)
        try: bot.send_message(uid, f"✅ **Withdrawal Successful!**\n₹{amt} has been sent to your account.")
        except: pass
    else:
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": amt}})
        withdraw_col.update_one({"user_id": uid, "status": "Pending"}, {"$set": {"status": "Rejected"}})
        bot.edit_message_text(f"❌ Rejected {uid}", c.message.chat.id, c.message.message_id)
        try: bot.send_message(uid, "❌ **Withdrawal Rejected.**\nBalance has been refunded.")
        except: pass

keep_alive()
if API_TOKEN:
    bot.infinity_polling()
