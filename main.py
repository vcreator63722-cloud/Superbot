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
    return "Ultra Pro Bot Running!"

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

# --- IMAGES (Inhe aap change kar sakte hain) ---
IMG_WELCOME = "https://i.ibb.co/hR5W0z3/welcome.jpg" # Koi bhi image link dalein
IMG_BALANCE = "https://i.ibb.co/vzD3Xj0/wallet.jpg"  # Wallet icon link

# --- SETTINGS ---
CURRENCY = "₹"
PER_REFER_BONUS = 5.0
DAILY_BONUS_AMOUNT = 1.0
MIN_WITHDRAW = 15.0
SIGNUP_BONUS = 2.0 
FAKE_BOT_FUND = 58000.0

try:
    if not MONGO_URL: print("❌ MONGO_URL Missing")
    client = MongoClient(MONGO_URL, tls=True, tlsAllowInvalidCertificates=True)
    db = client['TelegramBotDB']
    users_col = db['users']
    withdraw_col = db['withdrawals']
    channels_col = db['channels']
    gift_codes_col = db['gift_codes']
    tasks_col = db['tasks']
except Exception as e:
    print(f"DB Error: {e}")

bot = telebot.TeleBot(API_TOKEN) if API_TOKEN else None

# --- HELPER FUNCTIONS ---

def get_user(user_id):
    # Safe User Fetching (Crash Fix)
    u = users_col.find_one({"user_id": user_id})
    if not u: return None
    
    # Auto-Repair: Agar purane user me naye fields nahi hain to add karo
    updates = {}
    if 'total_earned' not in u: updates['total_earned'] = 0.0
    if 'payout_method' not in u: updates['payout_method'] = "Not Set"
    if 'payout_details' not in u: updates['payout_details'] = "Not Set"
    if 'completed_tasks' not in u: updates['completed_tasks'] = []
    
    if updates:
        users_col.update_one({"user_id": user_id}, {"$set": updates})
        return users_col.find_one({"user_id": user_id}) # Refresh
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
    
    pending = check_joined(user_id)
    if pending:
        markup = types.InlineKeyboardMarkup()
        for ch in pending:
            markup.add(types.InlineKeyboardButton(f"Join {ch['name']}", url=ch['link']))
        markup.add(types.InlineKeyboardButton("✅ Joined (Check)", callback_data="check_join"))
        
        msg = f"👋 **Welcome User!**\n\n🛑 **Access Denied:** You must join our channels to use the bot."
        # Image ke sath bhejna
        try:
            bot.send_photo(user_id, IMG_WELCOME, caption=msg, reply_markup=markup, parse_mode="Markdown")
        except:
            bot.send_message(user_id, msg, reply_markup=markup, parse_mode="Markdown")
    else:
        main_menu(user_id)

@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def check_join_btn(c):
    if not check_joined(c.message.chat.id):
        bot.delete_message(c.message.chat.id, c.message.message_id)
        main_menu(c.message.chat.id)
    else:
        bot.answer_callback_query(c.id, "❌ Join all channels first!", show_alert=True)

def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    # Exactly matching button text for handlers
    markup.add("💰 Balance", "🗣 Refer Earn")
    markup.add("🎁 Bonus", "💸 Withdraw")
    markup.add("🏦 Payout Method", "📍 Earn More")
    
    if user_id == ADMIN_ID: markup.add("⚙️ Admin Panel")
    
    msg = f"🏡 **Dashboard**\n\n🆔 ID: `{user_id}`\n🚀 **Start Earning Today!**\n\n👇 Choose an option below:"
    bot.send_message(user_id, msg, reply_markup=markup, parse_mode="Markdown")

# --- 1. BALANCE (FIXED & PROFESSIONAL) ---
@bot.message_handler(func=lambda m: m.text == "💰 Balance")
def balance(m):
    try:
        u = get_user(m.chat.id) # Safe fetch
        if not u:
            bot.reply_to(m, "❌ Error loading profile. Type /start")
            return

        msg = f"""
💰 **Your Wallet Dashboard**

👤 **User:** {m.chat.first_name}
🆔 **ID:** `{m.chat.id}`

💵 **Current Balance:** `{CURRENCY}{u.get('balance', 0):.2f}`
📊 **Total Earned:** `{CURRENCY}{u.get('total_earned', 0):.2f}`

_Refer friends to earn more!_
"""
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📜 History", callback_data="history"),
                   types.InlineKeyboardButton("🏦 Bot Fund", callback_data="bot_fund"))
        
        # Try sending photo, if fails (bad url), send text
        try:
            bot.send_photo(m.chat.id, IMG_BALANCE, caption=msg, reply_markup=markup, parse_mode="Markdown")
        except:
            bot.reply_to(m, msg, reply_markup=markup, parse_mode="Markdown")
            
    except Exception as e:
        bot.reply_to(m, "❌ System Error. Try /start again.")

@bot.callback_query_handler(func=lambda c: c.data == "history")
def history(c):
    txs = list(withdraw_col.find({"user_id": c.message.chat.id}).sort("date", -1).limit(5))
    msg = "📜 **Recent Transactions:**\n\n"
    if not txs: msg += "No history found."
    
    for tx in txs:
        icon = "✅" if tx['status'] == "Paid" else "❌" if tx['status'] == "Rejected" else "⏳"
        msg += f"{icon} **{CURRENCY}{tx['amount']}** | {tx['status']}\n"
    
    bot.send_message(c.message.chat.id, msg, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "bot_fund")
def bot_fund(c):
    amt = FAKE_BOT_FUND + random.randint(100, 9999)
    msg = f"🏦 **Bot Treasury Fund**\n\n💰 Live Balance: **{CURRENCY}{amt:,.2f}**\n✅ Status: **PAYING INSTANTLY** 🔥"
    bot.answer_callback_query(c.id, "Checking Server...")
    bot.send_message(c.message.chat.id, msg, parse_mode="Markdown")

# --- 2. REFER ---
@bot.message_handler(func=lambda m: m.text == "🗣 Refer Earn")
def refer(m):
    link = f"https://t.me/{bot.get_me().username}?start={m.chat.id}"
    msg = f"""
📣 **Refer & Earn Program**

🎁 **Per Refer:** {CURRENCY}{PER_REFER_BONUS}
👥 **Your Invites:** {get_user(m.chat.id).get('referrals', 0)}

🔗 **Your Link:**
`{link}`

_Share this link to earn unlimited cash!_
"""
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard"))
    bot.send_message(m.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "leaderboard")
def lb(c):
    tops = users_col.find().sort("referrals", -1).limit(10)
    msg = "🏆 **Top 10 Leaders** 🏆\n\n"
    for i, u in enumerate(tops):
        msg += f"#{i+1} 🆔 `{str(u['user_id'])[:4]}..` - {u['referrals']} Refs\n"
    bot.send_message(c.message.chat.id, msg, parse_mode="Markdown")

# --- 3. BONUS ---
@bot.message_handler(func=lambda m: m.text == "🎁 Bonus")
def bonus_menu(m):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📅 Claim Daily Bonus", callback_data="daily_bonus"))
    markup.add(types.InlineKeyboardButton("🎟 Redeem Promo Code", callback_data="redeem_code"))
    bot.reply_to(m, "🎁 **Bonus Zone**\nChoose an option:", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data == "daily_bonus")
def claim_daily(c):
    uid = c.message.chat.id
    u = get_user(uid)
    now = time.time()
    if now - u.get('last_bonus', 0) > 86400:
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": DAILY_BONUS_AMOUNT}, "$set": {"last_bonus": now}})
        bot.answer_callback_query(c.id, f"✅ Claimed {CURRENCY}{DAILY_BONUS_AMOUNT}!", show_alert=True)
    else:
        bot.answer_callback_query(c.id, "⏳ Come back tomorrow!", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data == "redeem_code")
def redeem_ask(c):
    msg = bot.send_message(c.message.chat.id, "🎟 **Send your Promo Code:**")
    bot.register_next_step_handler(msg, process_code)

def process_code(m):
    code = m.text.strip()
    gift = gift_codes_col.find_one({"code": code})
    if gift and gift['users_used'] < gift['limit']:
        if m.chat.id not in gift['used_by']:
            users_col.update_one({"user_id": m.chat.id}, {"$inc": {"balance": gift['amount']}})
            gift_codes_col.update_one({"code": code}, {"$inc": {"users_used": 1}, "$push": {"used_by": m.chat.id}})
            bot.reply_to(m, f"✅ **Success!** Added {CURRENCY}{gift['amount']}")
        else: bot.reply_to(m, "❌ Already used!")
    else: bot.reply_to(m, "❌ Invalid/Expired Code")

# --- 4. PAYOUT METHOD ---
@bot.message_handler(func=lambda m: m.text == "🏦 Payout Method")
def payout(m):
    u = get_user(m.chat.id)
    msg = f"💳 **Wallet Settings**\n\nActive: **{u.get('payout_method', 'None')}**\nDetails: `{u.get('payout_details', 'None')}`"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Set UPI", callback_data="set_upi"),
               types.InlineKeyboardButton("Set Paytm", callback_data="set_paytm"))
    bot.reply_to(m, msg, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("set_"))
def set_w(c):
    method = "UPI" if "upi" in c.data else "Paytm"
    msg = bot.send_message(c.message.chat.id, f"👇 **Enter {method} ID:**")
    bot.register_next_step_handler(msg, lambda mm: save_w(mm, method))

def save_w(m, method):
    users_col.update_one({"user_id": m.chat.id}, {"$set": {"payout_method": method, "payout_details": m.text}})
    bot.reply_to(m, f"✅ **Saved:** {m.text}")

# --- 5. WITHDRAW ---
@bot.message_handler(func=lambda m: m.text == "💸 Withdraw")
def withdraw(m):
    u = get_user(m.chat.id)
    bal = u.get('balance', 0)
    
    if bal < MIN_WITHDRAW:
        bot.reply_to(m, f"❌ **Insufficient Funds**\nMin Withdraw: {CURRENCY}{MIN_WITHDRAW}")
        return
    if u.get('payout_method') == "Not Set":
        bot.reply_to(m, "❌ **Wallet Not Set!**\nGo to 'Payout Method' first.")
        return

    users_col.update_one({"user_id": m.chat.id}, {"$set": {"balance": 0}})
    withdraw_col.insert_one({
        "user_id": m.chat.id, "amount": bal, "method": u['payout_method'],
        "details": u['payout_details'], "status": "Pending", "date": datetime.datetime.now()
    })
    
    # Notify Admin
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Pay", callback_data=f"pay_yes_{m.chat.id}_{bal}"),
               types.InlineKeyboardButton("❌ Reject", callback_data=f"pay_no_{m.chat.id}_{bal}"))
    bot.send_message(ADMIN_ID, f"🔔 **Withdraw Request**\nUser: `{m.chat.id}`\nAmt: {CURRENCY}{bal}\nTo: `{u['payout_details']}`", reply_markup=markup, parse_mode="Markdown")
    
    bot.reply_to(m, "✅ **Request Submitted!**\nAdmin will process it soon.")

# --- 6. ADMIN & EXTRAS ---
@bot.message_handler(func=lambda m: m.text == "⚙️ Admin Panel")
def admin(m):
    if m.chat.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_bc"),
        types.InlineKeyboardButton("➕ Add Channel", callback_data="adm_ch"),
        types.InlineKeyboardButton("🎟 Add Code", callback_data="adm_code"),
        types.InlineKeyboardButton("📊 Stats", callback_data="adm_stats")
    )
    bot.reply_to(m, "👮‍♂️ **Admin Panel**", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_"))
def adm_act(c):
    op = c.data.split("_")[1]
    if op == "ch":
        msg = bot.send_message(ADMIN_ID, "Send: `@username` OR `-100ID Link Name`")
        bot.register_next_step_handler(msg, add_ch_logic)
    elif op == "code":
        msg = bot.send_message(ADMIN_ID, "Send: `CODE AMOUNT LIMIT`")
        bot.register_next_step_handler(msg, add_code_logic)
    elif op == "stats":
        u = users_col.count_documents({})
        w = withdraw_col.count_documents({"status": "Paid"})
        bot.send_message(ADMIN_ID, f"📊 Users: {u}\n✅ Paid WDs: {w}")
    elif op == "bc":
        msg = bot.send_message(ADMIN_ID, "Send Broadcast Msg:")
        bot.register_next_step_handler(msg, lambda m: [bot.copy_message(u['user_id'], m.chat.id, m.message_id) for u in users_col.find({})])

def add_ch_logic(m):
    txt = m.text
    if txt.startswith("@"):
        channels_col.insert_one({"chat_id": txt, "link": f"https://t.me/{txt.replace('@','')}", "name": txt})
    else:
        try:
            p = txt.split()
            channels_col.insert_one({"chat_id": p[0], "link": p[1], "name": " ".join(p[2:])})
        except: return
    bot.reply_to(m, "✅ Added")

def add_code_logic(m):
    try:
        p = m.text.split()
        gift_codes_col.insert_one({"code": p[0], "amount": float(p[1]), "limit": int(p[2]), "users_used": 0, "used_by": []})
        bot.reply_to(m, "✅ Added")
    except: pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("pay_"))
def pay_proc(c):
    if c.message.chat.id != ADMIN_ID: return
    act, uid, amt = c.data.split("_")[1], int(c.data.split("_")[2]), float(c.data.split("_")[3])
    if act == "yes":
        withdraw_col.update_one({"user_id": uid, "status": "Pending"}, {"$set": {"status": "Paid"}})
        bot.edit_message_text(f"✅ Paid {uid}", c.message.chat.id, c.message.message_id)
        try: bot.send_message(uid, f"✅ **Payment Received!**\n{CURRENCY}{amt} sent successfully.")
        except: pass
    else:
        users_col.update_one({"user_id": uid}, {"$inc": {"balance": amt}})
        withdraw_col.update_one({"user_id": uid, "status": "Pending"}, {"$set": {"status": "Rejected"}})
        bot.edit_message_text(f"❌ Rejected {uid}", c.message.chat.id, c.message.message_id)
        try: bot.send_message(uid, f"❌ **Withdrawal Failed.** Refunded.")
        except: pass

@bot.message_handler(func=lambda m: m.text == "📍 Earn More")
def earn(m):
    # Dummy Links (Change these)
    msg = """
🔥 **Exclusive Loots (Instant Payment)**

1️⃣ **Task 1: Install & Register** (₹10)
🔗 [Click Here](https://google.com)

2️⃣ **Task 2: Join Channel** (₹5)
🔗 [Click Here](https://google.com)

_Complete tasks to earn extra income!_
"""
    bot.reply_to(m, msg, parse_mode="Markdown")

keep_alive()
if API_TOKEN:
    print("Bot Started...")
    bot.infinity_polling()
