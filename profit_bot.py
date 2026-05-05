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
BOT_TOKEN = "8602357349:AAEID1YFdPCzMg0wbvg6tNXtQBpjpCyYXhU"  # ЗАМЕНИ НА СВОЙ ТОКЕН
ADMIN_IDS = [8315613104]  # ЗАМЕНИ НА СВОЙ TELEGRAM ID

# ================= БАЗА ДАННЫХ =================
conn = sqlite3.connect("profit_bot.db", check_same_thread=False)
cursor = conn.cursor()

# Таблица работников
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
    last_bonus_date TEXT
)
""")

# Таблица скриншотов
cursor.execute("""
CREATE TABLE IF NOT EXISTS screenshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id INTEGER,
    platform TEXT,
    file_id TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# ================= ИНИЦИАЛИЗАЦИЯ =================
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ================= FSM СОСТОЯНИЯ =================
class AddWorkerState(StatesGroup):
    waiting_for_id = State()
    waiting_for_ozon_price = State()
    waiting_for_ypay_price = State()
    waiting_for_logi_price = State()


class SetPriceState(StatesGroup):
    waiting_for_id = State()
    waiting_for_platform = State()
    waiting_for_price = State()


class AddBalanceState(StatesGroup):
    waiting_for_id = State()
    waiting_for_amount = State()


class RemoveBalanceState(StatesGroup):
    waiting_for_id = State()
    waiting_for_amount = State()


class EditNameState(StatesGroup):
    waiting_for_id = State()
    waiting_for_name = State()


class ScreenshotState(StatesGroup):
    waiting_for_platform = State()
    waiting_for_photo = State()


# ================= ФУНКЦИИ БАЗЫ ДАННЫХ =================
def is_admin(user_id):
    return user_id in ADMIN_IDS


def get_worker(telegram_id):
    cursor.execute("SELECT * FROM workers WHERE telegram_id = ?", (telegram_id,))
    return cursor.fetchone()


def add_worker(telegram_id, name, price_ozon, price_ypay, price_logi):
    today = date.today().isoformat()
    cursor.execute("""
        INSERT INTO workers 
        (telegram_id, full_name, price_ozon, price_ypay, price_logi, last_bonus_date)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (telegram_id, name, price_ozon, price_ypay, price_logi, today))
    conn.commit()


def update_worker_name(telegram_id, new_name):
    cursor.execute("UPDATE workers SET full_name = ? WHERE telegram_id = ?", (new_name, telegram_id))
    conn.commit()


def update_price(telegram_id, platform, price):
    if platform == "ozon":
        cursor.execute("UPDATE workers SET price_ozon = ? WHERE telegram_id = ?", (price, telegram_id))
    elif platform == "ypay":
        cursor.execute("UPDATE workers SET price_ypay = ? WHERE telegram_id = ?", (price, telegram_id))
    else:
        cursor.execute("UPDATE workers SET price_logi = ? WHERE telegram_id = ?", (price, telegram_id))
    conn.commit()


def add_balance(telegram_id, amount):
    cursor.execute("UPDATE workers SET balance_usd = balance_usd + ? WHERE telegram_id = ?", (amount, telegram_id))
    conn.commit()


def remove_balance(telegram_id, amount):
    cursor.execute("UPDATE workers SET balance_usd = balance_usd - ? WHERE telegram_id = ?", (amount, telegram_id))
    conn.commit()


def increment_screenshot(telegram_id, platform):
    if platform == "ozon":
        cursor.execute(
            "UPDATE workers SET total_ozon = total_ozon + 1, daily_ozon = daily_ozon + 1 WHERE telegram_id = ?",
            (telegram_id,))
    elif platform == "ypay":
        cursor.execute(
            "UPDATE workers SET total_ypay = total_ypay + 1, daily_ypay = daily_ypay + 1 WHERE telegram_id = ?",
            (telegram_id,))
    else:
        cursor.execute(
            "UPDATE workers SET total_logi = total_logi + 1, daily_logi = daily_logi + 1 WHERE telegram_id = ?",
            (telegram_id,))
    conn.commit()


def get_daily_total(telegram_id):
    worker = get_worker(telegram_id)
    if not worker:
        return 0
    return worker[9] + worker[10] + worker[11]


def check_bonuses(telegram_id):
    worker = get_worker(telegram_id)
    if not worker:
        return ""

    today = date.today().isoformat()
    daily_total = worker[9] + worker[10] + worker[11]
    messages = []

    # Проверяем, нужно ли обнулить бонусы (новый день)
    if worker[15] != today:
        cursor.execute(
            "UPDATE workers SET bonus_4 = 0, bonus_6 = 0, bonus_10 = 0, last_bonus_date = ? WHERE telegram_id = ?",
            (today, telegram_id))
        conn.commit()
        worker = get_worker(telegram_id)

    bonus_4 = worker[12]
    bonus_6 = worker[13]
    bonus_10 = worker[14]

    if daily_total >= 10 and bonus_10 == 0:
        add_balance(telegram_id, 8)
        cursor.execute("UPDATE workers SET bonus_10 = 1 WHERE telegram_id = ?", (telegram_id,))
        conn.commit()
        messages.append("🎉 Бонус за 10 скриншотов: +8$")

    if daily_total >= 6 and bonus_6 == 0:
        add_balance(telegram_id, 6)
        cursor.execute("UPDATE workers SET bonus_6 = 1 WHERE telegram_id = ?", (telegram_id,))
        conn.commit()
        messages.append("🎉 Бонус за 6 скриншотов: +6$")

    if daily_total >= 4 and bonus_4 == 0:
        add_balance(telegram_id, 5)
        cursor.execute("UPDATE workers SET bonus_4 = 1 WHERE telegram_id = ?", (telegram_id,))
        conn.commit()
        messages.append("🎉 Бонус за 4 скриншота: +5$")

    return "\n".join(messages)


def save_screenshot(worker_id, platform, file_id):
    cursor.execute("INSERT INTO screenshots (worker_id, platform, file_id, status) VALUES (?, ?, ?, 'pending')",
                   (worker_id, platform, file_id))
    conn.commit()
    return cursor.lastrowid


def approve_screenshot(screenshot_id):
    cursor.execute("UPDATE screenshots SET status = 'approved' WHERE id = ?", (screenshot_id,))
    conn.commit()


def reject_screenshot(screenshot_id):
    cursor.execute("UPDATE screenshots SET status = 'rejected' WHERE id = ?", (screenshot_id,))
    conn.commit()


def get_pending_screenshot(worker_id, platform):
    cursor.execute(
        "SELECT id FROM screenshots WHERE worker_id = ? AND platform = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
        (worker_id, platform))
    return cursor.fetchone()


def get_all_workers():
    cursor.execute(
        "SELECT telegram_id, full_name, balance_usd, price_ozon, price_ypay, price_logi, total_ozon, total_ypay, total_logi, daily_ozon, daily_ypay, daily_logi FROM workers")
    return cursor.fetchall()


# ================= КЛАВИАТУРЫ =================
def get_main_keyboard(is_admin_user):
    buttons = [
        [KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="📸 Отправить скриншот")]
    ]
    if is_admin_user:
        buttons.append([KeyboardButton(text="⚙️ Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_platform_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛍️ Ozon"), KeyboardButton(text="💳 YPay")],
            [KeyboardButton(text="📦 ЛОГИ"), KeyboardButton(text="◀️ Назад")]
        ],
        resize_keyboard=True
    )


def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить работника", callback_data="add_worker")],
        [InlineKeyboardButton(text="✏️ Изменить имя", callback_data="edit_name")],
        [InlineKeyboardButton(text="💰 Изменить цену", callback_data="set_price")],
        [InlineKeyboardButton(text="🏦 Пополнить баланс", callback_data="add_balance")],
        [InlineKeyboardButton(text="📉 Списать баланс", callback_data="remove_balance")],
        [InlineKeyboardButton(text="📋 Список работников", callback_data="list_workers")],
        [InlineKeyboardButton(text="🔄 Сбросить бонусы", callback_data="reset_bonuses")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_main")]
    ])


# ================= ОБРАБОТЧИКИ =================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    keyboard = get_main_keyboard(is_admin(message.from_user.id))
    await message.answer(
        "🤖 *Бот учёта прибыли*\n\n"
        "🛍️ Ozon | 💳 YPay | 📦 ЛОГИ\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


@dp.message(F.text == "👤 Мой профиль")
async def show_profile(message: types.Message):
    worker = get_worker(message.from_user.id)
    if not worker:
        await message.answer("❌ Вы не зарегистрированы! Обратитесь к администратору.")
        return

    daily_total = worker[9] + worker[10] + worker[11]

    text = (
        f"📊 *Профиль*\n\n"
        f"👤 Имя: {worker[1]}\n"
        f"💰 Баланс: {worker[2]:.2f} $\n\n"
        f"🛍️ *Ozon*\n"
        f"├ Цена: {worker[3]:.2f}$\n"
        f"├ Всего: {worker[6]}\n"
        f"└ Сегодня: {worker[9]}\n\n"
        f"💳 *YPay*\n"
        f"├ Цена: {worker[4]:.2f}$\n"
        f"├ Всего: {worker[7]}\n"
        f"└ Сегодня: {worker[10]}\n\n"
        f"📦 *ЛОГИ*\n"
        f"├ Цена: {worker[5]:.2f}$\n"
        f"├ Всего: {worker[8]}\n"
        f"└ Сегодня: {worker[11]}\n\n"
        f"📅 *Сегодня:* {daily_total} скриншотов"
    )
    await message.answer(text, parse_mode="Markdown")


@dp.message(F.text == "📸 Отправить скриншот")
async def ask_platform(message: types.Message, state: FSMContext):
    worker = get_worker(message.from_user.id)
    if not worker:
        await message.answer("❌ Вы не зарегистрированы!")
        return

    await message.answer("📷 Выберите платформу:", reply_markup=get_platform_keyboard())
    await state.set_state(ScreenshotState.waiting_for_platform)


@dp.message(ScreenshotState.waiting_for_platform)
async def handle_platform(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        keyboard = get_main_keyboard(is_admin(message.from_user.id))
        await message.answer("🔙 Главное меню", reply_markup=keyboard)
        await state.clear()
        return

    platform_map = {
        "🛍️ Ozon": "ozon",
        "💳 YPay": "ypay",
        "📦 ЛОГИ": "logi"
    }

    if message.text not in platform_map:
        await message.answer("❌ Выберите платформу из кнопок!")
        return

    platform = platform_map[message.text]
    await state.update_data(platform=platform)
    await message.answer(f"Выбрано: {message.text}\n\nОтправьте фото скриншота:",
                         reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(ScreenshotState.waiting_for_photo)


@dp.message(ScreenshotState.waiting_for_photo, F.photo)
async def handle_screenshot(message: types.Message, state: FSMContext):
    data = await state.get_data()
    platform = data.get("platform")

    if not platform:
        await message.answer("❌ Ошибка! Начните заново: /start")
        await state.clear()
        return

    worker = get_worker(message.from_user.id)
    if not worker:
        await message.answer("❌ Вы не зарегистрированы!")
        await state.clear()
        return

    file_id = message.photo[-1].file_id
    save_screenshot(message.from_user.id, platform, file_id)

    platform_emoji = {"ozon": "🛍️ Ozon", "ypay": "💳 YPay", "logi": "📦 ЛОГИ"}
    price = worker[3] if platform == "ozon" else worker[4] if platform == "ypay" else worker[5]

    for admin_id in ADMIN_IDS:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"approve_{message.from_user.id}_{platform}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{message.from_user.id}_{platform}")]
        ])
        await bot.send_photo(
            admin_id,
            photo=file_id,
            caption=f"📸 *Новый скриншот*\n👤 {worker[1]}\n🆔 ID: {message.from_user.id}\n📱 {platform_emoji[platform]}\n💰 {price:.2f}$",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    await message.answer(f"✅ Скриншот ({platform_emoji[platform]}) отправлен на проверку!")
    await state.clear()

    keyboard = get_main_keyboard(is_admin(message.from_user.id))
    await message.answer("🔙 Главное меню", reply_markup=keyboard)


@dp.message(ScreenshotState.waiting_for_photo)
async def invalid_photo(message: types.Message,
                        state: FSMContext):
    await message.answer("❌ Пожалуйста, отправьте ФОТО!")


@dp.message(F.text == "⚙️ Админ-панель")
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён!")
        return
    await message.answer("⚙️ *Админ-панель*", parse_mode="Markdown", reply_markup=get_admin_keyboard())


# ================= CALLBACK АДМИНА =================
@dp.callback_query(lambda c: c.data == "add_worker")
async def add_worker_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("➕ Введите Telegram ID работника:")
    await state.set_state(AddWorkerState.waiting_for_id)


@dp.callback_query(lambda c: c.data == "edit_name")
async def edit_name_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("✏️ Введите Telegram ID работника:")
    await state.set_state(EditNameState.waiting_for_id)


@dp.callback_query(lambda c: c.data == "set_price")
async def set_price_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("💰 Введите Telegram ID работника:")
    await state.set_state(SetPriceState.waiting_for_id)


@dp.callback_query(lambda c: c.data == "add_balance")
async def add_balance_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("🏦 Введите Telegram ID работника:")
    await state.set_state(AddBalanceState.waiting_for_id)


@dp.callback_query(lambda c: c.data == "remove_balance")
async def remove_balance_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("📉 Введите Telegram ID работника:")
    await state.set_state(RemoveBalanceState.waiting_for_id)


@dp.callback_query(lambda c: c.data == "list_workers")
async def list_workers(callback: types.CallbackQuery):
    await callback.answer()
    workers = get_all_workers()
    if not workers:
        await callback.message.answer("❌ Нет работников!")
        return

    text = "📋 *Список работников*\n\n"
    for w in workers:
        daily = w[9] + w[10] + w[11]
        text += (
            f"🆔 ID: `{w[0]}`\n"
            f"👤 {w[1]}\n"
            f"💰 {w[2]:.2f}$\n"
            f"🛍️ {w[3]:.2f}$ | 💳 {w[4]:.2f}$ | 📦 {w[5]:.2f}$\n"
            f"📸 O:{w[6]} Y:{w[7]} Л:{w[8]}\n"
            f"📅 Сегодня: {daily}\n"
            f"{'─' * 25}\n"
        )
    await callback.message.answer(text, parse_mode="Markdown")


@dp.callback_query(lambda c: c.data == "reset_bonuses")
async def reset_bonuses(callback: types.CallbackQuery):
    await callback.answer()
    today = date.today().isoformat()
    cursor.execute("UPDATE workers SET bonus_4 = 0, bonus_6 = 0, bonus_10 = 0, last_bonus_date = ?", (today,))
    conn.commit()
    await callback.message.answer("✅ Бонусы сброшены!")


@dp.callback_query(lambda c: c.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    await callback.message.answer("🔙 Главное меню", reply_markup=get_main_keyboard(is_admin(user_id)))
    await callback.message.delete()


# ================= ПОДТВЕРЖДЕНИЕ СКРИНШОТОВ =================
@dp.callback_query(lambda c: c.data.startswith("approve_"))
async def approve_screenshot_callback(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    worker_id = int(parts[1])
    platform = parts[2]

    screenshot = get_pending_screenshot(worker_id, platform)
    if not screenshot:
        await callback.answer("❌ Нет скриншота!")
        return

    approve_screenshot(screenshot[0])

    worker = get_worker(worker_id)
    price = worker[3] if platform == "ozon" else worker[4] if platform == "ypay" else worker[5]

    add_balance(worker_id, price)
    increment_screenshot(worker_id, platform)
    bonus_msg = check_bonuses(worker_id)

    platform_emoji = {"ozon": "🛍️ Ozon", "ypay": "💳 YPay", "logi": "📦 ЛОГИ"}

    await bot.send_message(
        worker_id,
        f"✅ Скриншот ({platform_emoji[platform]}) подтверждён!\n💰 +{price:.2f}$\n{bonus_msg}"
    )

    await callback.answer("✅ Подтверждён!")
    await callback.message.edit_caption(caption=f"✅ ПОДТВЕРЖДЁН\n{callback.message.caption}", reply_markup=None)


@dp.callback_query(lambda c: c.data.startswith("reject_"))
async def reject_screenshot_callback(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    worker_id = int(parts[1])
    platform = parts[2]

    screenshot = get_pending_screenshot(worker_id, platform)
    if screenshot:
        reject_screenshot(screenshot[0])

        platform_emoji = {"ozon": "🛍️ Ozon", "ypay": "💳 YPay", "logi": "📦 ЛОГИ"}
        await bot.send_message(worker_id, f"❌ Скриншот ({platform_emoji[platform]}) отклонён!")

    await callback.answer("❌ Отклонён!")
    await callback.message.edit_caption(caption=f"❌ ОТКЛОНЁН\n{callback.message.caption}", reply_markup=None)


# ================= FSM ОБРАБОТЧИКИ =================
@dp.message(AddWorkerState.waiting_for_id)
async def add_worker_get_id(message: types.Message, state: FSMContext):
    try:
        worker_id = int(message.text.strip())
        if get_worker(worker_id):
            await message.answer("❌ Работник уже существует!")
            await state.clear()
            return
        await state.update_data(worker_id=worker_id)
        await message.answer("💰 Введите цену для Ozon (в $):")
        await state.set_state(AddWorkerState.waiting_for_ozon_price)
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО!")


@dp.message(AddWorkerState.waiting_for_ozon_price)
async def add_worker_get_ozon(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", "."))
        await state.update_data(price_ozon=price)
        await message.answer("💰 Введите цену для YPay (в $):")
        await state.set_state(AddWorkerState.waiting_for_ypay_price)
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО!")


@dp.message(AddWorkerState.waiting_for_ypay_price)
async def add_worker_get_ypay(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", "."))
        await state.update_data(price_ypay=price)
        await message.answer("💰 Введите цену для ЛОГИ (в $):")
        await state.set_state(AddWorkerState.waiting_for_logi_price)
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО!")


@dp.message(AddWorkerState.waiting_for_logi_price)
async def add_worker_get_logi(message: types.Message, state: FSMContext):
    try:
        price_logi = float(message.text.replace(",", "."))
        data = await state.get_data()
        worker_id = data["worker_id"]
        price_ozon = data["price_ozon"]
        price_ypay = data["price_ypay"]

        name = f"User_{worker_id}"
        add_worker(worker_id, name, price_ozon, price_ypay, price_logi)

        await message.answer(
            f"✅ *Работник добавлен!*\n\n"
            f"🆔 ID: {worker_id}\n"
            f"🛍️ Ozon: {price_ozon:.2f}$\n"
            f"💳 YPay: {price_ypay:.2f}$\n"
            f"📦 ЛОГИ: {price_logi:.2f}$",
            parse_mode="Markdown"
        )
        await state.clear()

        try:
            await bot.send_message(
                worker_id,
                f"🎉 Вас добавили!\n\n🛍️ Ozon: {price_ozon:.2f}$\n💳 YPay: {price_ypay:.2f}$\n📦 ЛОГИ: {price_logi:.2f}$\n\n📸 Отправляйте скриншоты!"
            )
        except:
            pass
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО!")


@dp.message(EditNameState.waiting_for_id)
async def edit_name_get_id(message: types.Message, state: FSMContext):
    try:
        worker_id = int(message.text.strip())
        worker = get_worker(worker_id)
        if not worker:
            await message.answer("❌ Работник не найден!")
            await state.clear()
            return
        await state.update_data(worker_id=worker_id)
        await message.answer(f"Текущее имя: {worker[1]}\nВведите новое имя:")
        await state.set_state(EditNameState.waiting_for_name)
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО!")


@dp.message(EditNameState.waiting_for_name)
async def edit_name_set(message: types.Message, state: FSMContext):
    data = await state.get_data()
    worker_id = data["worker_id"]
    new_name = message.text.strip()
    update_worker_name(worker_id, new_name)
    await message.answer(f"✅ Имя изменено на: {new_name}")
    await state.clear()


@dp.message(SetPriceState.waiting_for_id)
async def set_price_get_id(message: types.Message, state: FSMContext):
    try:
        worker_id = int(message.text.strip())
        worker = get_worker(worker_id)
        if not worker:
            await message.answer("❌ Работник не найден!")
            await state.clear()
            return
        await state.update_data(worker_id=worker_id)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍️ Ozon", callback_data="price_ozon"),
             InlineKeyboardButton(text="💳 YPay", callback_data="price_ypay")],
            [InlineKeyboardButton(text="📦 ЛОГИ", callback_data="price_logi")]
        ])
        await message.answer(
            f"💰 Текущие цены {worker[1]}:\nOzon: {worker[3]:.2f}$\nYPay: {worker[4]:.2f}$\nЛОГИ: {worker[5]:.2f}$\n\nВыберите платформу:",
            reply_markup=keyboard)
        await state.set_state(SetPriceState.waiting_for_platform)
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО!")


@dp.callback_query(lambda c: c.data.startswith("price_"))
async def set_price_platform(callback: types.CallbackQuery, state: FSMContext):
    platform = callback.data.split("_")[1]
    await state.update_data(platform=platform)
    await callback.message.answer(f"💰 Введите новую цену для {platform.upper()}:")
    await state.set_state(SetPriceState.waiting_for_price)
    await callback.answer()


@dp.message(SetPriceState.waiting_for_price)
async def set_price_set(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", "."))
        data = await state.get_data()
        worker_id = data["worker_id"]
        platform = data["platform"]

        update_price(worker_id, platform, price)
        platform_names = {"ozon": "Ozon", "ypay": "YPay", "logi": "ЛОГИ"}
        await message.answer(f"✅ Цена для {platform_names[platform]} обновлена: {price:.2f}$")
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО!")


@dp.message(AddBalanceState.waiting_for_id)
async def add_balance_get_id(message: types.Message, state: FSMContext):
    try:
        worker_id = int(message.text.strip())
        worker = get_worker(worker_id)
        if not worker:
            await message.answer("❌ Работник не найден!")
            await state.clear()
            return
        await state.update_data(worker_id=worker_id)
        await message.answer(f"💰 Текущий баланс: {worker[2]:.2f}$\nВведите сумму (+$):")
        await state.set_state(AddBalanceState.waiting_for_amount)
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО!")


@dp.message(AddBalanceState.waiting_for_amount)
async def add_balance_set(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        data = await state.get_data()
        worker_id = data["worker_id"]
        add_balance(worker_id, amount)
        worker = get_worker(worker_id)
        await message.answer(f"✅ Пополнено на {amount:.2f}$\n💰 Новый баланс: {worker[2]:.2f}$")
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО!")


@dp.message(RemoveBalanceState.waiting_for_id)
async def remove_balance_get_id(message: types.Message, state: FSMContext):
    try:
        worker_id = int(message.text.strip())
        worker = get_worker(worker_id)
        if not worker:
            await message.answer("❌ Работник не найден!")
            await state.clear()
            return
        await state.update_data(worker_id=worker_id)
        await message.answer(f"💰 Текущий баланс: {worker[2]:.2f}$\nВведите сумму для списания (-$):")
        await state.set_state(RemoveBalanceState.waiting_for_amount)
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО!")


@dp.message(RemoveBalanceState.waiting_for_amount)
async def remove_balance_set(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        data = await state.get_data()
        worker_id = data["worker_id"]
        remove_balance(worker_id, amount)
        worker = get_worker(worker_id)
        await message.answer(f"✅ Списано {amount:.2f}$\n💰 Новый баланс: {worker[2]:.2f}$")
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО!")


# ================= ЕЖЕДНЕВНЫЙ СБРОС =================
async def daily_reset():
    while True:
        now = datetime.now()
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        wait_seconds = (tomorrow - now).total_seconds()
        await asyncio.sleep(wait_seconds)

        cursor.execute("UPDATE workers SET daily_ozon = 0, daily_ypay = 0, daily_logi = 0")
        conn.commit()

        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, "🔄 *Ежедневный сброс бонусов выполнен!*", parse_mode="Markdown")


# ================= ЗАПУСК =================
async def main():
    asyncio.create_task(daily_reset())
    print("🤖 Бот запущен!")
    print(f"👑 Админы: {ADMIN_IDS}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
