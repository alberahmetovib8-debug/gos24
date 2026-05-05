import asyncio
import sqlite3
from datetime import datetime, timedelta, date
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ================= КОНФИГ =================
BOT_TOKEN = "8602357349:AAEID1YFdPCzMg0wbvg6tNXtQBpjpCyYXhU"  # ЗАМЕНИ!!!
ADMIN_IDS = [8315613104]  # ЗАМЕНИ!!!

# ================= БАЗА ДАННЫХ =================
conn = sqlite3.connect("profit_bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS workers (
    telegram_id INTEGER PRIMARY KEY,
    full_name TEXT,
    balance_usd REAL DEFAULT 0,
    price_ozon REAL DEFAULT 0.5,
    price_ypay REAL DEFAULT 0.5,
    price_logi REAL DEFAULT 0.5,
    total_ozon INTEGER DEFAULT 0,
    total_ypay INTEGER DEFAULT 0,
    total_logi INTEGER DEFAULT 0,
    daily_ozon INTEGER DEFAULT 0,
    daily_ypay INTEGER DEFAULT 0,
    daily_logi INTEGER DEFAULT 0,
    bonus_4 INTEGER DEFAULT 0,
    bonus_6 INTEGER DEFAULT 0,
    bonus_10 INTEGER DEFAULT 0,
    bonus_date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS screenshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id INTEGER,
    platform TEXT,
    file_id TEXT,
    status TEXT DEFAULT 'pending'
)
""")
conn.commit()

# ================= ИНИЦИАЛИЗАЦИЯ =================
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ================= FSM =================
class AddWorker(StatesGroup):
    get_id = State()
    get_ozon = State()
    get_ypay = State()
    get_logi = State()

class SetPrice(StatesGroup):
    get_id = State()
    get_platform = State()
    get_price = State()

class AddBalance(StatesGroup):
    get_id = State()
    get_amount = State()

class RemoveBalance(StatesGroup):
    get_id = State()
    get_amount = State()

class EditName(StatesGroup):
    get_id = State()
    get_name = State()

class SendScreenshot(StatesGroup):
    get_platform = State()
    get_photo = State()

# ================= ФУНКЦИИ =================
def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_worker(uid):
    cursor.execute("SELECT * FROM workers WHERE telegram_id = ?", (uid,))
    return cursor.fetchone()

def get_all_workers():
    cursor.execute("SELECT telegram_id, full_name, balance_usd, price_ozon, price_ypay, price_logi, total_ozon, total_ypay, total_logi, daily_ozon, daily_ypay, daily_logi FROM workers")
    return cursor.fetchall()

def add_worker(uid, name, p_ozon, p_ypay, p_logi):
    today = date.today().isoformat()
    cursor.execute("INSERT INTO workers (telegram_id, full_name, price_ozon, price_ypay, price_logi, bonus_date) VALUES (?, ?, ?, ?, ?, ?)",
                   (uid, name, p_ozon, p_ypay, p_logi, today))
    conn.commit()

def update_name(uid, new_name):
    cursor.execute("UPDATE workers SET full_name = ? WHERE telegram_id = ?", (new_name, uid))
    conn.commit()

def update_price(uid, platform, price):
    if platform == "ozon":
        cursor.execute("UPDATE workers SET price_ozon = ? WHERE telegram_id = ?", (price, uid))
    elif platform == "ypay":
        cursor.execute("UPDATE workers SET price_ypay = ? WHERE telegram_id = ?", (price, uid))
    else:
        cursor.execute("UPDATE workers SET price_logi = ? WHERE telegram_id = ?", (price, uid))
    conn.commit()

def add_balance(uid, amount):
    cursor.execute("UPDATE workers SET balance_usd = balance_usd + ? WHERE telegram_id = ?", (amount, uid))
    conn.commit()

def remove_balance(uid, amount):
    cursor.execute("UPDATE workers SET balance_usd = balance_usd - ? WHERE telegram_id = ?", (amount, uid))
    conn.commit()

def inc_screenshot(uid, platform):
    if platform == "ozon":
        cursor.execute("UPDATE workers SET total_ozon = total_ozon + 1, daily_ozon = daily_ozon + 1 WHERE telegram_id = ?", (uid,))
    elif platform == "ypay":
        cursor.execute("UPDATE workers SET total_ypay = total_ypay + 1, daily_ypay = daily_ypay + 1 WHERE telegram_id = ?", (uid,))
    else:
        cursor.execute("UPDATE workers SET total_logi = total_logi + 1, daily_logi = daily_logi + 1 WHERE telegram_id = ?", (uid,))
    conn.commit()

def get_price(worker, platform):
    if platform == "ozon":
        return worker[3]
    elif platform == "ypay":
        return worker[4]
    else:
        return worker[5]

def check_bonus(uid):
    worker = get_worker(uid)
    if not worker:
        return ""
    
    today = date.today().isoformat()
    daily_total = worker[9] + worker[10] + worker[11]
    messages = []
    
    if worker[15] != today:
        cursor.execute("UPDATE workers SET bonus_4 = 0, bonus_6 = 0, bonus_10 = 0, bonus_date = ? WHERE telegram_id = ?", (today, uid))
        conn.commit()
        worker = get_worker(uid)
    
    if daily_total >= 10 and worker[14] == 0:
        add_balance(uid, 8)
        cursor.execute("UPDATE workers SET bonus_10 = 1 WHERE telegram_id = ?", (uid,))
        conn.commit()
        messages.append("🎉 Бонус за 10 скриншотов: +8$")
    
    if daily_total >= 6 and worker[13] == 0:
        add_balance(uid, 6)
        cursor.execute("UPDATE workers SET bonus_6 = 1 WHERE telegram_id = ?", (uid,))
        conn.commit()
        messages.append("🎉 Бонус за 6 скриншотов: +6$")
    
    if daily_total >= 4 and worker[12] == 0:
        add_balance(uid, 5)
        cursor.execute("UPDATE workers SET bonus_4 = 1 WHERE telegram_id = ?", (uid,))
        conn.commit()
        messages.append("🎉 Бонус за 4 скриншота: +5$")
    
    return "\n".join(messages)

def save_screenshot(uid, platform, file_id):
    cursor.execute("INSERT INTO screenshots (worker_id, platform, file_id) VALUES (?, ?, ?)", (uid, platform, file_id))
    conn.commit()
    return cursor.lastrowid

def get_pending(uid, platform):
    cursor.execute("SELECT id FROM screenshots WHERE worker_id = ? AND platform = ? AND status = 'pending' ORDER BY id DESC LIMIT 1", (uid, platform))
    return cursor.fetchone()

def approve_screenshot(sid):
    cursor.execute("UPDATE screenshots SET status = 'approved' WHERE id = ?", (sid,))
    conn.commit()

def reject_screenshot(sid):
    cursor.execute("UPDATE screenshots SET status = 'rejected' WHERE id = ?", (sid,))
    conn.commit()

# ================= КЛАВИАТУРЫ =================
def main_keyboard(is_admin_user):
    btns = [
        [KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="📸 Отправить скриншот")]
    ]
    if is_admin_user:
        btns.append([KeyboardButton(text="⚙️ Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

def platform_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛍️ Ozon"), KeyboardButton(text="💳 YPay")],
            [KeyboardButton(text="📦 ЛОГИ"), KeyboardButton(text="◀️ Назад")]
        ],
        resize_keyboard=True
    )

def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить работника", callback_data="admin_add")],
        [InlineKeyboardButton(text="✏️ Изменить имя", callback_data="admin_name")],
        [InlineKeyboardButton(text="💰 Изменить цену", callback_data="admin_price")],
        [InlineKeyboardButton(text="🏦 Пополнить баланс", callback_data="admin_add_bal")],
        [InlineKeyboardButton(text="📉 Списать баланс", callback_data="admin_rem_bal")],
        [InlineKeyboardButton(text="📋 Список работников", callback_data="admin_list")],
        [InlineKeyboardButton(text="🔄 Сбросить бонусы", callback_data="admin_reset")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ])

# ================= ОБРАБОТЧИКИ =================
@dp.message(Command("start"))
async def start(msg: types.Message):
    kb = main_keyboard(is_admin(msg.from_user.id))
    await msg.answer("🤖 *Бот учёта прибыли*\n\nOzon / YPay / ЛОГИ", parse_mode="Markdown", reply_markup=kb)

@dp.message(F.text == "👤 Мой профиль")
async def profile(msg: types.Message):
    worker = get_worker(msg.from_user.id)
    if not worker:
        await msg.answer("❌ Вы не зарегистрированы!")
        return
    
    daily = worker[9] + worker[10] + worker[11]
    text = f"""📊 *Профиль*

👤 {worker[1]}
💰 Баланс: {worker[2]:.2f}$

🛍️ *Ozon*
├ Цена: {worker[3]:.2f}$
├ Всего: {worker[6]}
└ Сегодня: {worker[9]}

💳 *YPay*
├ Цена: {worker[4]:.2f}$
├ Всего: {worker[7]}
└ Сегодня: {worker[10]}

📦 *ЛОГИ*
├ Цена: {worker[5]:.2f}$
├ Всего: {worker[8]}
└ Сегодня: {worker[11]}

📅 Сегодня: {daily} скриншотов"""
    await msg.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📸 Отправить скриншот")
async def send_screenshot(msg: types.Message, state: FSMContext):
    if not get_worker(msg.from_user.id):
        await msg.answer("❌ Вы не зарегистрированы!")
        return
    await msg.answer("📷 Выберите платформу:", reply_markup=platform_keyboard())
    await state.set_state(SendScreenshot.get_platform)

@dp.message(SendScreenshot.get_platform)
async def get_platform(msg: types.Message, state: FSMContext):
    if msg.text == "◀️ Назад":
        kb = main_keyboard(is_admin(msg.from_user.id))
        await msg.answer("🔙 Главное меню", reply_markup=kb)
        await state.clear()
        return
    
    plat_map = {"🛍️ Ozon": "ozon", "💳 YPay": "ypay", "📦 ЛОГИ": "logi"}
    if msg.text not in plat_map:
        await msg.answer("❌ Выберите из кнопок!")
        return
    
    await state.update_data(platform=plat_map[msg.text])
    await msg.answer(f"Выбрано: {msg.text}\n\nОтправьте фото:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(SendScreenshot.get_photo)

@dp.message(SendScreenshot.get_photo, F.photo)
async def get_photo(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    platform = data.get("platform")
    if not platform:
        await msg.answer("❌ Ошибка! Начните заново /start")
        await state.clear()
        return
    
    worker = get_worker(msg.from_user.id)
    file_id = msg.photo[-1].file_id
    save_screenshot(msg.from_user.id, platform, file_id)
    
    plat_emoji = {"ozon": "🛍️ Ozon", "ypay": "💳 YPay", "logi": "📦 ЛОГИ"}
    price = get_price(worker, platform)
    
    # Отправляем админу
    for admin_id in ADMIN_IDS:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"ok_{msg.from_user.id}_{platform}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"no_{msg.from_user.id}_{platform}")]
        ])
        await bot.send_photo(
            admin_id,
            photo=file_id,
            caption=f"📸 *Новый скриншот*\n👤 {worker[1]}\n🆔 ID: {msg.from_user.id}\n📱 {plat_emoji[platform]}\n💰 {price:.2f}$",
            parse_mode="Markdown",
            reply_markup=kb
        )
    
    await msg.answer(f"✅ Скриншот ({plat_emoji[platform]}) отправлен на проверку!")
    await state.clear()
    
    kb = main_keyboard(is_admin(msg.from_user.id))
    await msg.answer("🔙 Главное меню", reply_markup=kb)

@dp.message(SendScreenshot.get_photo)
async def no_photo(msg: types.Message):
    await msg.answer("❌ Отправьте ФОТО!")

@dp.message(F.text == "⚙️ Админ-панель")
async def admin_panel(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("⛔ Доступ запрещён!")
        return
    await msg.answer("⚙️ *Админ-панель*", parse_mode="Markdown", reply_markup=admin_keyboard())

# ================= CALLBACK АДМИНА =================
@dp.callback_query(lambda c: c.data == "admin_add")
async def admin_add(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("➕ Введите Telegram ID работника:")
    await state.set_state(AddWorker.get_id)

@dp.callback_query(lambda c: c.data == "admin_name")
async def admin_name(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("✏️ Введите Telegram ID:")
    await state.set_state(EditName.get_id)

@dp.callback_query(lambda c: c.data == "admin_price")
async def admin_price(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("💰 Введите Telegram ID:")
    await state.set_state(SetPrice.get_id)

@dp.callback_query(lambda c: c.data == "admin_add_bal")
async def admin_add_bal(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("🏦 Введите Telegram ID:")
    await state.set_state(AddBalance.get_id)

@dp.callback_query(lambda c: c.data == "admin_rem_bal")
async def admin_rem_bal(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("📉 Введите Telegram ID:")
    await state.set_state(RemoveBalance.get_id)

@dp.callback_query(lambda c: c.data == "admin_list")
async def admin_list(call: types.CallbackQuery):
    await call.answer()
    workers = get_all_workers()
    if not workers:
        await call.message.answer("❌ Нет работников!")
        return
    
    text = "📋 *Список работников*\n\n"
    for w in workers:
        daily = w[9] + w[10] + w[11]
        text += f"🆔 `{w[0]}`\n👤 {w[1]}\n💰 {w[2]:.2f}$\n🛍️ {w[3]:.2f}$ | 💳 {w[4]:.2f}$ | 📦 {w[5]:.2f}$\n📸 O:{w[6]} Y:{w[7]} Л:{w[8]}\n📅 Сегодня: {daily}\n{'─' * 25}\n"
    await call.message.answer(text, parse_mode="Markdown")

@dp.callback_query(lambda c: c.data == "admin_reset")
async def admin_reset(call: types.CallbackQuery):
    await call.answer()
    today = date.today().isoformat()
    cursor.execute("UPDATE workers SET bonus_4 = 0, bonus_6 = 0, bonus_10 = 0, bonus_date = ?", (today,))
    conn.commit()
    await call.message.answer("✅ Бонусы сброшены!")

@dp.callback_query(lambda c: c.data == "admin_back")
async def admin_back(call: types.CallbackQuery):
    await call.answer()
    kb = main_keyboard(True)
    await call.message.answer("🔙 Главное меню", reply_markup=kb)
    await call.message.delete()

# ================= ПОДТВЕРЖДЕНИЕ =================
@dp.callback_query(lambda c: c.data.startswith("ok_"))
async def approve(call: types.CallbackQuery):
    parts = call.data.split("_")
    uid = int(parts[1])
    platform = parts[2]
    
    pending = get_pending(uid, platform)
    if not pending:
        await call.answer("❌ Нет скриншота!")
        return
    
    approve_screenshot(pending[0])
    worker = get_worker(uid)
    price = get_price(worker, platform)
    
    add_balance(uid, price)
    inc_screenshot(uid, platform)
    bonus = check_bonus(uid)
    
    plat_emoji = {"ozon": "🛍️ Ozon", "ypay": "💳 YPay", "logi": "📦 ЛОГИ"}
    await bot.send_message(uid, f"✅ Скриншот ({plat_emoji[platform]}) подтверждён!\n💰 +{price:.2f}$\n{bonus}")
    
    await call.answer("✅ Подтверждён!")
    await call.message.edit_caption(caption=f"✅ ПОДТВЕРЖДЁН\n{call.message.caption}", reply_markup=None)

@dp.callback_query(lambda c: c.data.startswith("no_"))
async def reject(call: types.CallbackQuery):
    parts = call.data.split("_")
    uid = int(parts[1])
    platform = parts[2]
    
    pending = get_pending(uid, platform)
    if pending:
        reject_screenshot(pending[0])
        plat_emoji = {"ozon": "🛍️ Ozon", "ypay": "💳 YPay", "logi": "📦 ЛОГИ"}
        await bot.send_message(uid, f"❌ Скриншот ({plat_emoji[platform]}) отклонён!")
    
    await call.answer("❌ Отклонён!")
    await call.message.edit_caption(caption=f"❌ ОТКЛОНЁН\n{call.message.caption}", reply_markup=None)

# ================= FSM ДОБАВЛЕНИЕ РАБОТНИКА =================
@dp.message(AddWorker.get_id)
async def add_get_id(msg: types.Message, state: FSMContext):
    try:
        uid = int(msg.text.strip())
        if get_worker(uid):
            await msg.answer("❌ Уже существует!")
            await state.clear()
            return
        await state.update_data(uid=uid)
        await msg.answer("💰 Цена для Ozon (в $):")
        await state.set_state(AddWorker.get_ozon)
    except:
        await msg.answer("❌ Введите ЧИСЛО!")

@dp.message(AddWorker.get_ozon)
async def add_get_ozon(msg: types.Message, state: FSMContext):
    try:
        p = float(msg.text.replace(",", "."))
        await state.update_data(ozon=p)
        await msg.answer("💰 Цена для YPay (в $):")
        await state.set_state(AddWorker.get_ypay)
    except:
        await msg.answer("❌ Введите ЧИСЛО!")

@dp.message(AddWorker.get_ypay)
async def add_get_ypay(msg: types.Message, state: FSMContext):
    try:
        p = float(msg.text.replace(",", "."))
        await state.update_data(ypay=p)
        await msg.answer("💰 Цена для ЛОГИ (в $):")
        await state.set_state(AddWorker.get_logi)
    except:
        await msg.answer("❌ Введите ЧИСЛО!")

@dp.message(AddWorker.get_logi)
async def add_get_logi(msg: types.Message, state: FSMContext):
    try:
        p_logi = float(msg.text.replace(",", "."))
        data = await state.get_data()
        uid = data["uid"]
        p_ozon = data["ozon"]
        p_ypay = data["ypay"]
        
        add_worker(uid, f"User_{uid}", p_ozon, p_ypay, p_logi)
        await msg.answer(f"✅ Работник добавлен!\n🆔 {uid}\n🛍️ {p_ozon:.2f}$\n💳 {p_ypay:.2f}$\n📦 {p_logi:.2f}$")
        await state.clear()
        
        try:
            await bot.send_message(uid, f"🎉 Вас добавили!\n🛍️ {p_ozon:.2f}$\n💳 {p_ypay:.2f}$\n📦 {p_logi:.2f}$")
        except:
            pass
    except:
        await msg.answer("❌ Ошибка!")

# ================= FSM РЕДАКТИРОВАНИЕ ИМЕНИ =================
@dp.message(EditName.get_id)
async def edit_name_id(msg: types.Message, state: FSMContext):
    try:
        uid = int(msg.text.strip())
        if not get_worker(uid):
            await msg.answer("❌ Не найден!")
            await state.clear()
            return
        await state.update_data(uid=uid)
        await msg.answer("✏️ Введите новое имя:")
        await state.set_state(EditName.get_name)
    except:
        await msg.answer("❌ Введите ЧИСЛО!")

@dp.message(EditName.get_name)
async def edit_name_set(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    update_name(data["uid"], msg.text.strip())
    await msg.answer(f"✅ Имя изменено на: {msg.text}")
    await state.clear()

# ================= FSM НАСТРОЙКА ЦЕНЫ =================
@dp.message(SetPrice.get_id)
async def price_get_id(msg: types.Message, state: FSMContext):
    try:
        uid = int(msg.text.strip())
        if not get_worker(uid):
            await msg.answer("❌ Не найден!")
            await state.clear()
            return
        await state.update_data(uid=uid)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍️ Ozon", callback_data="pr_ozon"),
             InlineKeyboardButton(text="💳 YPay", callback_data="pr_ypay")],
            [InlineKeyboardButton(text="📦 ЛОГИ", callback_data="pr_logi")]
        ])
        await msg.answer("Выберите платформу:", reply_markup=kb)
        await state.set_state(SetPrice.get_platform)
    except:
        await msg.answer("❌ Введите ЧИСЛО!")

@dp.callback_query(lambda c: c.data.startswith("pr_"))
async def price_platform(call: types.CallbackQuery, state: FSMContext):
    plat = call.data.split("_")[1]
    await state.update_data(platform=plat)
    await call.message.answer(f"💰 Введите новую цену для {plat.upper()}:")
    await state.set_state(SetPrice.get_price)
    await call.answer()

@dp.message(SetPrice.get_price)
async def price_set(msg: types.Message, state: FSMContext):
    try:
        price = float(msg.text.replace(",", "."))
        data = await state.get_data()
        update_price(data["uid"], data["platform"], price)
        await msg.answer(f"✅ Цена обновлена: {price:.2f}$")
        await state.clear()
    except:
        await msg.answer("❌ Введите ЧИСЛО!")

# ================= FSM ПОПОЛНЕНИЕ =================
@dp.message(AddBalance.get_id)
async def add_bal_id(msg: types.Message, state: FSMContext):
    try:
        uid = int(msg.text.strip())
        if not get_worker(uid):
            await msg.answer("❌ Не найден!")
            await state.clear()
            return
        await state.update_data(uid=uid)
        await msg.answer("💰 Введите сумму (+$):")
        await state.set_state(AddBalance.get_amount)
    except:
        await msg.answer("❌ Введите ЧИСЛО!")

@dp.message(AddBalance.get_amount)
async def add_bal_set(msg: types.Message, state: FSMContext):
    try:
        amount = float(msg.text.replace(",", "."))
        data = await state.get_data()
        add_balance(data["uid"], amount)
        worker = get_worker(data["uid"])
        await msg.answer(f"✅ Пополнено на {amount:.2f}$\n💰 Новый баланс: {worker[2]:.2f}$")
        await state.clear()
    except:
        await msg.answer("❌ Введите ЧИСЛО!")

# ================= FSM СПИСАНИЕ =================
@dp.message(RemoveBalance.get_id)
async def rem_bal_id(msg: types.Message, state: FSMContext):
    try:
        uid = int(msg.text.strip())
        if not get_worker(uid):
            await msg.answer("❌ Не найден!")
            await state.clear()
            return
        await state.update_data(uid=uid)
        await msg.answer("📉 Введите сумму для списания (-$):")
        await state.set_state(RemoveBalance.get_amount)
    except:
        await msg.answer("❌ Введите ЧИСЛО!")

@dp.message(RemoveBalance.get_amount)
async def rem_bal_set(msg: types.Message, state: FSMContext):
    try:
        amount = float(msg.text.replace(",", "."))
        data = await state.get_data()
        remove_balance(data["uid"], amount)
        worker = get_worker(data["uid"])
        await msg.answer(f"✅ Списано {amount:.2f}$\n💰 Новый баланс: {worker[2]:.2f}$")
        await state.clear()
    except:
        await msg.answer("❌ Введите ЧИСЛО!")

# ================= ЕЖЕДНЕВНЫЙ СБРОС =================
async def daily_reset_job():
    while True:
        now = datetime.now()
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        await asyncio.sleep((midnight - now).total_seconds())
        cursor.execute("UPDATE workers SET daily_ozon = 0, daily_ypay = 0, daily_logi = 0")
        conn.commit()
        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, "🔄 *Ежедневный сброс выполнен!*", parse_mode="Markdown")

# ================= ЗАПУСК =================
async def main():
    asyncio.create_task(daily_reset_job())
    print("🤖 Бот запущен!")
    print(f"👑 Админы: {ADMIN_IDS}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
