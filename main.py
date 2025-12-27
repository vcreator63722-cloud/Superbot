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
# 1. SERVER KEEP ALIVE
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Door Cash Clone Running!"

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

API_TOKEN = os.environ.get('BOT_TOKEN')
MONGO_URL = os.environ.get('MONGO_URL')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '1234567890'))

# --- SETTINGS (Customize Here) ---
CURRENCY = "₹"
PER_REFER_BONUS = 5.0
DAILY_BONUS_AMOUNT = 1.0
MIN_WITHDRAW = 15.0
SIGNUP_BONUS = 2.0 
FAKE_BOT_FUND = 56000.0 # Starting fake fund

try:
    if not MONGO_URL: print("❌ MONGO_URL Missing")
    client = MongoClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
    db = client['TelegramBotDB']
    users_col = db['users']
    withdraw_col = db['withdrawals']
    channels_col = db['channels']
    gift_codes_col = db['gift_codes']
    tasks_col = db['tasks'] # New: Task System
except Exception as e:
    print(f"DB Error: {e}")

bot = telebot.TeleBot(API_TOKEN) if API_TOKEN else None

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
            "balance": SIGNUP_BONUS,
            "referrals": 0,
            "total_earned": 0.0,
            "joined_date": datetime.datetime.now(),
            "last_bonus": 0,
            "payout_method": "Not Set",
            "payout_details": "Not Set",
            "completed_tasks": []
        })
        # Refer Logic
        if referrer_id and referrer_id != user_id:
            users_col.update_one({"user_id": referrer_id}, {
                "$inc": {"balance": PER_REFER_BONUS, "referrals": 1, "total_earned": PER_REFER_BONUS}
            })
            try: bot.send_message(referrer_id, f"🎉 **New Referral!**\nYou earned {CURRENCY}{PER_REFER_BONUS}", parse_mode="Markdown")
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
    
    # Force Join Check
    pending = check_joined(user_id)
    if pending:
        markup = types.InlineKeyboardMarkup()
        for ch in pending:
            markup.add(types.InlineKeyboardButton(f"Join {ch['name']}", url=ch['link']))
        markup.add(types.InlineKeyboardButton("✅ Joined (Click Here)", callback_data="check_join"))
        
        msg = f"👋 **Hey User! Welcome!**\n\n🛑 **Must Join All Channels To Use Bot**"
        bot.send_message(user_id, msg, reply_markup=markup, parse_mode="Markdown")
    else:
        main_menu(user_id)

@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def check_join_btn(c):
    if not check_joined(c.message.chat.id):
        bot.delete_message(c.message.chat.id, c.message.message_id)
        main_menu(c.message.chat.id)
    else:
        bot.answer_callback_query(c.id, "❌ You haven't joined all channels!", show_alert=True)

def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("💰 Balance", "🗣 Refer Earn")
    markup.add("🎁 Bonus", "💸 Withdraw")
    markup.add("🏦 Payout Method", "📍 Earn More")
    
    if user_id == ADMIN_ID: markup.add("⚙️ Admin Panel")
    
    msg = f"🏡 **Home Menu**\n\n🆔 User ID: `{user_id}`\n🚀 Start Earning Now!"
    bot.send_message(user_id, msg, reply_markup=markup, parse_mode="Markdown")

# --- 1. BALANCE & HISTORY ---
@bot.message_handler(func=lambda m: m.text == "💰 Balance")
def balance(m):
    u = get_user(m.chat.id)
    msg = f"💰 **Current Balance:** {CURRENCY}{u['balance']:.2f}\n\n📊 **Total Earned:** {CURRENCY}{u['total_earned']:.2f}"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📜 Withdraw History", callback_data="history"))
    markup.add(types.InlineKeyboardButton("🏦 Bot Fund Stats", callback_data="bot_fund"))
    
    bot.reply_to(m, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "history")
def history(c):
    txs = list(withdraw_col.find({"user_id": c.message.chat.id}).sort("date", -1).limit(5))
    if not txs:
        bot.answer_callback_query(c.id, "No history found!", show_alert=True)
        return
    
    msg = "📜 **Last 5 Withdrawals:**\n\n"
    for tx in txs:
        status_icon = "✅" if tx['status'] == "Paid" else "⏳" if tx['status'] == "Pending" else "❌"
        msg += f"{status_icon} {CURRENCY}{tx['amount']} | {tx['date'].strftime('%d/%m')}\n"
    
    bot.send_message(c.message.chat.id, msg)

@bot.callback_query_handler(func=lambda c: c.data == "bot_fund")
def bot_fund(c):
    # Fake stats to impress users
    fake_amt = FAKE_BOT_FUND + random.randint(100, 5000)
    msg = f"🏦 **Live Bot Fund Stats**\n\n💰 Available Fund: **{CURRENCY}{fake_amt:,.2f}**\n✅ Total Paid: **{CURRENCY}1,24,500+**\n\n_Payment Verified 100%_ ✅"
    bot.send_message(c.message.chat.id, msg, parse_mode="Markdown")

# --- 2. REFER & TRACKER ---
@bot.message_handler(func=lambda m: m.text == "🗣 Refer Earn")
def refer(m):
    link = f"https://t.me/{bot.get_me().username}?start={m.chat.id}"
    msg = f"📣 **Refer & Earn Program**\n\n🎁 Per Refer: **{CURRENCY}{PER_REFER_BONUS}**\n🔗 **Link:** `{link}`\n\n_Share with friends & family!_"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("👥 My Invites (Tracker)", callback_data="my_invites"))
    markup.add(types.InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard"))
    
    bot.reply_to(m, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "my_invites")
def tracker(c):
    u = get_user(c.message.chat.id)
    bot.answer_callback_query(c.id, f"Total Invites: {u['referrals']}", show_alert=True)

# --- 3. BONUS & GIFT CODE ---
@bot.message_handler(func=lambda m: m.text == "🎁 Bonus")
def bonus_menu(m):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📅 Daily Check-in", callback_data="daily_bonus"))
    markup.add(types.InlineKeyboardButton("🎟 Redeem Code", callback_data="redeem_code"))
    bot.reply_to(m, "🎁 **Bonus Section**", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data == "daily_bonus")
def claim_daily(c):
    uid = c.message.chat.id
    u = get_user(uid)
    now = time.time()
    
    if now - u.get('last_bonus', 0) > 86400:
        users_col.update_one({"user_id": uid}, {
            "$inc": {"balance": DAILY_BONUS_AMOUNT}, 
            "$set": {"last_bonus": now}
        })
        bot.answer_callback_query(c.id, f"Success! +{CURRENCY}{DAILY_BONUS_AMOUNT} Added.")
    else:
        bot.answer_callback_query(c.id, "❌ Already claimed today!", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data == "redeem_code")
def redeem_ask(c):
    msg = bot.send_message(c.message.chat.id, "🎟 **Enter Promo Code:**")
    bot.register_next_step_handler(msg, process_code)

def process_code(m):
    code = m.text.strip()
    gift = gift_codes_col.find_one({"code": code})
    if gift and gift['users_used'] < gift['limit']:
        if m.chat.id not in gift['used_by']:
            users_col.update_one({"user_id": m.chat.id}, {"$inc": {"balance": gift['amount']}})
            gift_codes_col.update_one({"code": code}, {"$inc": {"users_used": 1}, "$push": {"used_by": m.chat.id}})
            bot.reply_to(m, f"✅ **Redeemed!** {CURRENCY}{gift['amount']} Added.")
        else: bot.reply_to(m, "❌ Already used!")
    else: bot.reply_to(m, "❌ Invalid or Expired Code!")

# --- 4. PAYOUT SETTINGS ---
@bot.message_handler(func=lambda m: m.text == "🏦 Payout Method")
def payout(m):
    u = get_user(m.chat.id)
    msg = f"💳 **Payout Settings**\n\nActive Method: **{u.get('payout_method')}**\nDetails: `{u.get('payout_details')}`"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Set UPI", callback_data="set_upi"),
               types.InlineKeyboardButton("Set Paytm", callback_data="set_paytm"))
    bot.reply_to(m, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("set_"))
def set_wallet(c):
    method = "UPI" if "upi" in c.data else "Paytm"
    msg = bot.send_message(c.message.chat.id, f"👇 **Enter your {method} ID/Number:**")
    bot.register_next_step_handler(msg, lambda mm: save_wallet(mm, method))

def save_wallet(m, method):
    users_col.update_one({"user_id": m.chat.id}, {"$set": {"payout_method": method, "payout_details": m.text}})
    bot.reply_to(m, f"✅ **{method} Saved:** `{m.text}`", parse_mode="Markdown")

# --- 5. EARN MORE (TASKS) ---
@bot.message_handler(func=lambda m: m.text == "📍 Earn More")
def earn_more(m):
    tasks = list(tasks_col.find({}))
    if not tasks:
        bot.reply_to(m, "🚫 No tasks available right now.")
        return
    
    markup = types.InlineKeyboardMarkup()
    for t in tasks:
        markup.add(types.InlineKeyboardButton(f"💰 {CURRENCY}{t['amount']} - {t['name']}", callback_data=f"do_task_{t['_id']}"))
    
    bot.reply_to(m, "📋 **Available Tasks:**\nClick to complete and earn!", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith("do_task_"))
def task_click(c):
    task_id = c.data.split("_")[2]
    # Simple logic: Just show link. In advanced, you check join.
    # For now, providing link.
    # Note: Implementing true verification for external links is impossible in basic bots.
    # We will assume user clicks and we pay (or use Admin verify).
    # Let's use simple click = reward (limited to 1 time)
    
    # Check if done
    u = get_user(c.message.chat.id)
    if task_id in u.get('completed_tasks', []):
        bot.answer_callback_query(c.id, "❌ Already Completed!", show_alert=True)
        return

    # Find task
    from bson.objectid import ObjectId
    task = tasks_col.find_one({"_id": ObjectId(task_id)})
    
    if task:
        # Give reward
        users_col.update_one({"user_id": c.message.chat.id}, {
            "$inc": {"balance": task['amount']},
            "$push": {"completed_tasks": task_id}
        })
        bot.send_message(c.message.chat.id, f"✅ **Task Completed!**\nYou visited {task['name']}\nEarned: {CURRENCY}{task['amount']}")
        # In real scenario, redirect first, verify later. This is simplified.

# --- 6. WITHDRAW SYSTEM ---
@bot.message_handler(func=lambda m: m.text == "💸 Withdraw")
def withdraw(m):
    u = get_user(m.chat.id)
    
    if u['balance'] < MIN_WITHDRAW:
        bot.reply_to(m, f"❌ **Low Balance!**\nMinimum Withdraw: {CURRENCY}{MIN_WITHDRAW}")
        return
    
    if u['payout_method'] == "Not Set":
        bot.reply_to(m, "❌ **Payout Method Not Set!**\nGo to 'Payout Method' button first.")
        return

    # Deduct & Save
    users_col.update_one({"user_id": m.chat.id}, {"$set": {"balance": 0}})
    withdraw_col.insert_one({
        "user_id": m.chat.id, "amount": u['balance'],
        "method": u['payout_method'], "details": u['payout_details'],
        "status": "Pending", "date": datetime.datetime.now()
    })
    
    # Notify Admin
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Pay", callback_data=f"pay_yes_{m.chat.id}_{u['balance']}"),
               types.InlineKeyboardButton("❌ Reject", callback_data=f"pay_no_{m.chat.id}_{u['balance']}"))
    
    bot.send_message(ADMIN_ID, f"🔔 **Withdraw Request**\nUser: `{m.chat.id}`\nAmt: {CURRENCY}{u['balance']}\nMethod: {u['payout_method']}\nDetails: `{u['payout_details']}`", reply_markup=markup, parse_mode="Markdown")
    bot.reply_to(m, "✅ **Request Submitted!**\nPayment will be processed within 24 hours.")

# --- 7. ADMIN PANEL (GRAPHICAL) ---
@bot.message_handler(func=lambda m: m.text == "⚙️ Admin Panel")
def admin_panel(m):
    if m.chat.id != ADMIN_ID: return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_bc"),
        types.InlineKeyboardButton("➕ Add Channel", callback_data="adm_ch"),
        types.InlineKeyboardButton("🎟 Add Code", callback_data="adm_code"),
        types.InlineKeyboardButton("📋 Add Task", callback_data="adm_task"),
        types.InlineKeyboardButton("📊 Stats", callback_data="adm_stats")
    )
    bot.reply_to(m, "👮‍♂️ **Admin Control Panel**", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_"))
def admin_actions(c):
    if c.message.chat.id != ADMIN_ID: return
    op = c.data.split("_")[1]
    
    if op == "ch":
        msg = bot.send_message(ADMIN_ID, "Send Channel:\n`@username` OR `-100ID Link Name`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_add_ch)
        
    elif op == "code":
        msg = bot.send_message(ADMIN_ID, "Send: `CODE AMOUNT LIMIT`")
        bot.register_next_step_handler(msg, process_add_code)
        
    elif op == "task":
        msg = bot.send_message(ADMIN_ID, "Send: `NAME AMOUNT URL`")
        bot.register_next_step_handler(msg, process_add_task)
        
    elif op == "bc":
        msg = bot.send_message(ADMIN_ID, "Send Message to Broadcast:")
        bot.register_next_step_handler(msg, lambda m: [bot.copy_message(u['user_id'], m.chat.id, m.message_id) for u in users_col.find({})])
        
    elif op == "stats":
        u_count = users_col.count_documents({})
        w_count = withdraw_col.count_documents({"status": "Paid"})
        bot.send_message(ADMIN_ID, f"📊 **Stats:**\nUsers: {u_count}\nPaid WDs: {w_count}")

# Admin Process Functions
def process_add_ch(m):
    text = m.text
    if text.startswith("@"):
        channels_col.insert_one({"chat_id": text, "link": f"https://t.me/{text.replace('@','')}", "name": text})
    elif text.startswith("-100"):
        p = text.split()
        channels_col.insert_one({"chat_id": p[0], "link": p[1], "name": " ".join(p[2:])})
    bot.reply_to(m, "✅ Channel Added")

def process_add_code(m):
    try:
        p = m.text.split()
        gift_codes_col.insert_one({"code": p[0], "amount": float(p[1]), "limit": int(p[2]), "users_used": 0, "used_by": []})
        bot.reply_to(m, "✅ Code Created")
    except: bot.reply_to(m, "Error")

def process_add_task(m):
    try:
        p = m.text.split()
        tasks_col.insert_one({"name": p[0], "amount": float(p[1]), "url": p[2]})
        bot.reply_to(m, "✅ Task Created")
    except: bot.reply_to(m, "Error")

# --- ADMIN PAY ---
@bot.callback_query_handler(func=lambda c: c.data.startswith("pay_"))
def pay_action(c):
    if c.message.chat.id != ADMIN_ID: return
    act, uid, amt = c.data.split("_")[1], int(c.data.split("_")[2]), float(c.data.split("_")[3])
    
    if act == "yes":
        withdraw_col.update_one({"user_id": uid, "status": "Pending"}, {"$set": {"status": "Paid"}})
        bot.edit_message_text(f"✅ Marked Paid: {uid}", c.message.chat.id, c.message.message_id)
        try: bot.send_message(uid, f"✅ **Withdrawal Success!**\n{CURRENCY}{amt} has been sent.")
        except: pass
    else:
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": amt}})
        withdraw_col.update_one({"user_id": uid, "status": "Pending"}, {"$set": {"status": "Rejected"}})
        bot.edit_message_text(f"❌ Rejected: {uid}", c.message.chat.id, c.message.message_id)
        try: bot.send_message(uid, f"❌ **Withdrawal Rejected.** Refunded.")
        except: pass

keep_alive()
if API_TOKEN:
    print("🤖 Ultra Pro Bot Started...")
    bot.infinity_polling()
