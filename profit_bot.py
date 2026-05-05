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
BOT_TOKEN = "8220363263:AAErJ6PfZh037WJsxFG5YaovLswFmkbqD7Q"
ADMIN_IDS = [8315613104]

# ================= БАЗА ДАННЫХ =================
conn = sqlite3.connect("profit_bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS workers (
    telegram_id INTEGER PRIMARY KEY,
    full_name TEXT,
    balance_usd REAL DEFAULT 0,
    price_per_screenshot REAL DEFAULT 0.5,
    total_screenshots INTEGER DEFAULT 0,
    daily_screenshots INTEGER DEFAULT 0,
    last_bonus_date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS screenshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id INTEGER,
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


# ================= FSM =================
class AddWorkerState(StatesGroup):
    waiting_for_id = State()
    waiting_for_price = State()


class SetPriceState(StatesGroup):
    waiting_for_worker_id = State()
    waiting_for_new_price = State()


class AddBalanceState(StatesGroup):
    waiting_for_worker_id = State()
    waiting_for_amount = State()


class RemoveBalanceState(StatesGroup):
    waiting_for_worker_id = State()
    waiting_for_amount = State()


class EditNameState(StatesGroup):
    waiting_for_worker_id = State()
    waiting_for_new_name = State()


# ================= ФУНКЦИИ =================
def is_admin(user_id):
    return user_id in ADMIN_IDS


def get_worker(telegram_id):
    cursor.execute("SELECT * FROM workers WHERE telegram_id = ?", (telegram_id,))
    return cursor.fetchone()


def add_worker(telegram_id, full_name, price):
    today = date.today().isoformat()
    cursor.execute(
        "INSERT OR REPLACE INTO workers (telegram_id, full_name, price_per_screenshot, balance_usd, total_screenshots, daily_screenshots, last_bonus_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (telegram_id, full_name, price, 0, 0, 0, today))
    conn.commit()


def update_worker_price(telegram_id, new_price):
    cursor.execute("UPDATE workers SET price_per_screenshot = ? WHERE telegram_id = ?", (new_price, telegram_id))
    conn.commit()


def update_worker_name(telegram_id, new_name):
    cursor.execute("UPDATE workers SET full_name = ? WHERE telegram_id = ?", (new_name, telegram_id))
    conn.commit()


def add_balance(telegram_id, amount):
    cursor.execute("UPDATE workers SET balance_usd = balance_usd + ? WHERE telegram_id = ?", (amount, telegram_id))
    conn.commit()


def remove_balance(telegram_id, amount):
    """Списывает баланс (уменьшает)"""
    cursor.execute("UPDATE workers SET balance_usd = balance_usd - ? WHERE telegram_id = ?", (amount, telegram_id))
    conn.commit()


def increment_screenshots(telegram_id):
    cursor.execute(
        "UPDATE workers SET total_screenshots = total_screenshots + 1, daily_screenshots = daily_screenshots + 1 WHERE telegram_id = ?",
        (telegram_id,))
    conn.commit()


def reset_daily_stats():
    today = date.today().isoformat()
    cursor.execute("UPDATE workers SET daily_screenshots = 0, last_bonus_date = ?", (today,))
    conn.commit()


def check_and_give_bonuses(telegram_id):
    worker = get_worker(telegram_id)
    if not worker:
        return ""
    daily_count = worker[5]
    last_bonus = worker[6] or ""
    messages = []

    if daily_count >= 10 and "bonus_10" not in last_bonus:
        add_balance(telegram_id, 8)
        cursor.execute("UPDATE workers SET last_bonus_date = last_bonus_date || ',bonus_10' WHERE telegram_id = ?",
                       (telegram_id,))
        conn.commit()
        messages.append("🎉 Бонус за 10 скриншотов за сегодня: +8 $")
    if daily_count >= 6 and "bonus_6" not in last_bonus:
        add_balance(telegram_id, 6)
        cursor.execute("UPDATE workers SET last_bonus_date = last_bonus_date || ',bonus_6' WHERE telegram_id = ?",
                       (telegram_id,))
        conn.commit()
        messages.append("🎉 Бонус за 6 скриншотов за сегодня: +6 $")
    if daily_count >= 4 and "bonus_4" not in last_bonus:
        add_balance(telegram_id, 5)
        cursor.execute("UPDATE workers SET last_bonus_date = last_bonus_date || ',bonus_4' WHERE telegram_id = ?",
                       (telegram_id,))
        conn.commit()
        messages.append("🎉 Бонус за 4 скриншота за сегодня: +5 $")
    return "\n".join(messages)


def save_screenshot(worker_id, file_id):
    cursor.execute("INSERT INTO screenshots (worker_id, file_id, status) VALUES (?, ?, 'pending')",
                   (worker_id, file_id))
    conn.commit()
    return cursor.lastrowid


def approve_screenshot(screenshot_id):
    cursor.execute("UPDATE screenshots SET status = 'approved' WHERE id = ?", (screenshot_id,))
    conn.commit()


def reject_screenshot(screenshot_id):
    cursor.execute("UPDATE screenshots SET status = 'rejected' WHERE id = ?", (screenshot_id,))
    conn.commit()


def get_all_workers():
    cursor.execute(
        "SELECT telegram_id, full_name, balance_usd, price_per_screenshot, total_screenshots, daily_screenshots FROM workers")
    return cursor.fetchall()


def get_pending_screenshots_count(worker_id=None):
    if worker_id:
        cursor.execute("SELECT COUNT(*) FROM screenshots WHERE worker_id = ? AND status = 'pending'", (worker_id,))
    else:
        cursor.execute("SELECT COUNT(*) FROM screenshots WHERE status = 'pending'")
    return cursor.fetchone()[0]


# ================= КЛАВИАТУРЫ =================
def get_main_keyboard(is_admin_user):
    buttons = [[KeyboardButton(text="👤 Мой профиль")], [KeyboardButton(text="📸 Отправить скриншот")]]
    if is_admin_user:
        buttons.append([KeyboardButton(text="⚙️ Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_admin_panel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить работника", callback_data="add_worker")],
        [InlineKeyboardButton(text="✏️ Изменить имя работника", callback_data="edit_name")],
        [InlineKeyboardButton(text="💰 Настроить сумму за скриншот", callback_data="set_price")],
        [InlineKeyboardButton(text="🏦 Пополнить баланс", callback_data="add_balance")],
        [InlineKeyboardButton(text="📉 Списать с баланса", callback_data="remove_balance")],
        [InlineKeyboardButton(text="📋 Список работников", callback_data="list_workers")],
        [InlineKeyboardButton(text="🔄 Сбросить бонусы", callback_data="reset_bonuses")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ])


# ================= ОБРАБОТЧИКИ =================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    keyboard = get_main_keyboard(is_admin(message.from_user.id))
    await message.answer("🤖 Добро пожаловать в бот учёта прибыли!\n\n📌 Выберите действие в меню.",
                         reply_markup=keyboard)


@dp.message(F.text == "👤 Мой профиль")
async def show_profile(message: types.Message):
    worker = get_worker(message.from_user.id)
    if not worker:
        await message.answer("❌ Вы не зарегистрированы как работник. Обратитесь к администратору.")
        return
    await message.answer(
        f"📊 *Ваш профиль*\n\n"
        f"👤 Имя: `{worker[1]}`\n"
        f"💰 Баланс: `{worker[2]:.2f} $`\n"
        f"💵 Цена за скриншот: `{worker[3]:.2f} $`\n"
        f"📸 Всего скриншотов: `{worker[4]}`\n"
        f"📅 Сегодня: `{worker[5]}` скриншотов",
        parse_mode="Markdown"
    )


@dp.message(F.text == "📸 Отправить скриншот")
async def ask_screenshot(message: types.Message):
    if not get_worker(message.from_user.id):
        await message.answer("❌ Вы не зарегистрированы как работник.")
        return
    await message.answer("📷 Отправьте фото скриншота:")


@dp.message(F.photo)
async def handle_screenshot(message: types.Message):
    worker = get_worker(message.from_user.id)
    if not worker:
        await message.answer("❌ Вы не зарегистрированы")
        return
    file_id = message.photo[-1].file_id
    save_screenshot(message.from_user.id, file_id)
    for admin_id in ADMIN_IDS:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"approve_{message.from_user.id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{message.from_user.id}")]
        ])
        await bot.send_photo(
            admin_id,
            photo=file_id,
            caption=f"📸 Новый скриншот\n👤 Работник: {worker[1]}\n🆔 ID: {message.from_user.id}",
            reply_markup=keyboard
        )
    await message.answer("✅ Скриншот отправлен на подтверждение!")


@dp.message(F.text == "⚙️ Админ-панель")
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён!")
        return
    await message.answer("⚙️ *Админ-панель*\nВыберите действие:", parse_mode="Markdown",
                         reply_markup=get_admin_panel_keyboard())


# ================= CALLBACK =================
@dp.callback_query(lambda c: c.data == "add_worker")
async def add_worker_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("➕ Введите `telegram_id` работника:", parse_mode="Markdown")
    await state.set_state(AddWorkerState.waiting_for_id)


@dp.callback_query(lambda c: c.data == "edit_name")
async def edit_name_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    workers = get_all_workers()
    if not workers:
        await callback.message.answer("❌ Нет работников!")
        return
    text = "📋 *Список работников:*\n\n"
    for w in workers:
        text += f"🆔 ID: `{w[0]}` | Имя: {w[1]}\n"
    await callback.message.answer(text + "\n✏️ Введите `telegram_id` работника, чьё имя хотите изменить:",
                                  parse_mode="Markdown")
    await state.set_state(EditNameState.waiting_for_worker_id)


@dp.callback_query(lambda c: c.data == "set_price")
async def set_price_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("💰 Введите `telegram_id` работника:", parse_mode="Markdown")
    await state.set_state(SetPriceState.waiting_for_worker_id)


@dp.callback_query(lambda c: c.data == "list_workers")
async def list_workers(callback: types.CallbackQuery):
    await callback.answer()
    workers = get_all_workers()
    if not workers:
        await callback.message.answer("❌ Нет работников!")
        return
    text = "📋 *Список работников:*\n\n"
    for w in workers:
        text += (
            f"🆔 ID: `{w[0]}`\n"
            f"👤 Имя: {w[1]}\n"
            f"💰 Баланс: {w[2]:.2f} $\n"
            f"💵 Цена: {w[3]:.2f} $\n"
            f"📸 Всего: {w[4]} | Сегодня: {w[5]}\n"
            f"{'─' * 25}\n"
        )
    await callback.message.answer(text, parse_mode="Markdown")


@dp.callback_query(lambda c: c.data == "add_balance")
async def add_balance_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("🏦 Введите `telegram_id` работника для пополнения:", parse_mode="Markdown")
    await state.set_state(AddBalanceState.waiting_for_worker_id)


@dp.callback_query(lambda c: c.data == "remove_balance")
async def remove_balance_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("📉 Введите `telegram_id` работника для списания:", parse_mode="Markdown")
    await state.set_state(RemoveBalanceState.waiting_for_worker_id)


@dp.callback_query(lambda c: c.data == "reset_bonuses")
async def reset_bonuses_manual(callback: types.CallbackQuery):
    await callback.answer()
    reset_daily_stats()
    await callback.message.answer("✅ Дневные бонусы и счётчики сброшены у всех работников!")


@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("🔙 Главное меню", reply_markup=get_main_keyboard(True))
    await callback.message.delete()


@dp.callback_query(lambda c: c.data.startswith("approve_"))
async def approve_screenshot_callback(callback: types.CallbackQuery):
    worker_id = int(callback.data.split("_")[1])
    cursor.execute(
        "SELECT id FROM screenshots WHERE worker_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
        (worker_id,))
    result = cursor.fetchone()
    if not result:
        await callback.answer("❌ Нет ожидающих скриншотов!")
        return
    approve_screenshot(result[0])
    worker = get_worker(worker_id)
    price = worker[3]
    add_balance(worker_id, price)
    increment_screenshots(worker_id)
    bonus_msg = check_and_give_bonuses(worker_id)

    await bot.send_message(
        worker_id,
        f"✅ Ваш скриншот подтверждён!\n💰 Начислено: +{price}$\n{bonus_msg}"
    )
    await callback.answer("✅ Скриншот подтверждён!")
    await callback.message.edit_caption(caption=f"✅ ПОДТВЕРЖДЁН\n{callback.message.caption}", reply_markup=None)


@dp.callback_query(lambda c: c.data.startswith("reject_"))
async def reject_screenshot_callback(callback: types.CallbackQuery):
    worker_id = int(callback.data.split("_")[1])
    cursor.execute(
        "SELECT id FROM screenshots WHERE worker_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
        (worker_id,))
    result = cursor.fetchone()
    if result:
        reject_screenshot(result[0])
        await bot.send_message(worker_id, "❌ Ваш скриншот отклонён администратором.")
    await callback.answer("❌ Скриншот отклонён!")
    await callback.message.edit_caption(caption=f"❌ ОТКЛОНЁН\n{callback.message.caption}", reply_markup=None)


# ================= FSM ОБРАБОТЧИКИ =================
@dp.message(AddWorkerState.waiting_for_id)
async def add_worker_get_id(message: types.Message, state: FSMContext):
    try:
        worker_id = int(message.text.strip())
        await state.update_data(worker_id=worker_id)
        await message.answer("💰 Введите цену за 1 скриншот (в $, например: 0.5):")
        await state.set_state(AddWorkerState.waiting_for_price)
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО (telegram_id)!")


@dp.message(AddWorkerState.waiting_for_price)
async def add_worker_get_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.replace(",", "."))
        data = await state.get_data()
        worker_id = data["worker_id"]
        if get_worker(worker_id):
            await message.answer(f"❌ Работник с ID {worker_id} уже существует!")
            await state.clear()
            return
        full_name = message.from_user.full_name
        add_worker(worker_id, full_name, price)
        await message.answer(f"✅ Работник добавлен!\n🆔 ID: {worker_id}\n👤 Имя: {full_name}\n💰 Цена: {price:.2f}$")
        await state.clear()
        await bot.send_message(worker_id, f"🎉 Вас добавили как работника!\n💰 Ваша цена за скриншот: {price:.2f}$")
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО (цену в $)!")


@dp.message(EditNameState.waiting_for_worker_id)
async def edit_name_get_worker(message: types.Message, state: FSMContext):
    try:
        worker_id = int(message.text.strip())
        worker = get_worker(worker_id)
        if not worker:
            await message.answer(f"❌ Работник с ID {worker_id} не найден!")
            await state.clear()
            return
        await state.update_data(worker_id=worker_id)
        await message.answer(f"✏️ Текущее имя: {worker[1]}\nВведите новое имя для работника:")
        await state.set_state(EditNameState.waiting_for_new_name)
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО (telegram_id)!")


@dp.message(EditNameState.waiting_for_new_name)
async def edit_name_get_new_name(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    data = await state.get_data()
    worker_id = data["worker_id"]
    update_worker_name(worker_id, new_name)
    await message.answer(f"✅ Имя работника изменено на: {new_name}")
    await state.clear()
    await bot.send_message(worker_id, f"✏️ Админ изменил ваше имя на: {new_name}")


@dp.message(SetPriceState.waiting_for_worker_id)
async def set_price_get_worker(message: types.Message, state: FSMContext):
    try:
        worker_id = int(message.text.strip())
        worker = get_worker(worker_id)
        if not worker:
            await message.answer(f"❌ Работник с ID {worker_id} не найден!")
            await state.clear()
            return
        await state.update_data(worker_id=worker_id)
        await message.answer(f"💰 Текущая цена для {worker[1]}: {worker[3]:.2f}$\nВведите новую цену:")
        await state.set_state(SetPriceState.waiting_for_new_price)
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО!")


@dp.message(SetPriceState.waiting_for_new_price)
async def set_price_get_new_price(message: types.Message, state: FSMContext):
    try:
        new_price = float(message.text.replace(",", "."))
        data = await state.get_data()
        worker_id = data["worker_id"]
        update_worker_price(worker_id, new_price)
        worker = get_worker(worker_id)
        await message.answer(f"✅ Цена для {worker[1]} обновлена: {new_price:.2f}$")
        await state.clear()
        await bot.send_message(worker_id, f"💰 Админ обновил цену за скриншот: теперь {new_price:.2f}$")
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО!")


@dp.message(AddBalanceState.waiting_for_worker_id)
async def add_balance_get_worker(message: types.Message, state: FSMContext):
    try:
        worker_id = int(message.text.strip())
        worker = get_worker(worker_id)
        if not worker:
            await message.answer(f"❌ Работник с ID {worker_id} не найден!")
            await state.clear()
            return
        await state.update_data(worker_id=worker_id)
        await message.answer(f"💰 Текущий баланс {worker[1]}: {worker[2]:.2f}$\nВведите сумму пополнения (+$):")
        await state.set_state(AddBalanceState.waiting_for_amount)
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО!")


@dp.message(AddBalanceState.waiting_for_amount)
async def add_balance_get_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        data = await state.get_data()
        worker_id = data["worker_id"]
        add_balance(worker_id, amount)
        worker = get_worker(worker_id)
        await message.answer(f"✅ Баланс пополнен на {amount:.2f}$\n💰 Новый баланс: {worker[2]:.2f}$")
        await state.clear()
        await bot.send_message(worker_id, f"💰 Админ пополнил баланс на +{amount:.2f}$\n📊 Ваш баланс: {worker[2]:.2f}$")
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО!")


@dp.message(RemoveBalanceState.waiting_for_worker_id)
async def remove_balance_get_worker(message: types.Message, state: FSMContext):
    try:
        worker_id = int(message.text.strip())
        worker = get_worker(worker_id)
        if not worker:
            await message.answer(f"❌ Работник с ID {worker_id} не найден!")
            await state.clear()
            return
        await state.update_data(worker_id=worker_id)
        await message.answer(f"💰 Текущий баланс {worker[1]}: {worker[2]:.2f}$\nВведите сумму для СПИСАНИЯ (-$):")
        await state.set_state(RemoveBalanceState.waiting_for_amount)
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО!")


@dp.message(RemoveBalanceState.waiting_for_amount)
async def remove_balance_get_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        data = await state.get_data()
        worker_id = data["worker_id"]
        remove_balance(worker_id, amount)
        worker = get_worker(worker_id)
        await message.answer(f"✅ Списано {amount:.2f}$\n💰 Новый баланс: {worker[2]:.2f}$")
        await state.clear()
        await bot.send_message(worker_id, f"📉 Админ списал с баланса -{amount:.2f}$\n📊 Ваш баланс: {worker[2]:.2f}$")
    except ValueError:
        await message.answer("❌ Введите ЧИСЛО!")


# ================= ФОНОВАЯ ЗАДАЧА =================
async def daily_reset_task():
    while True:
        now = datetime.now()
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        await asyncio.sleep((next_midnight - now).total_seconds())
        reset_daily_stats()
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id,
                                       "🔄 *Ежедневный сброс бонусов выполнен!*\n\nРаботники могут снова получать бонусы за 4, 6 и 10 скриншотов за сегодня.",
                                       parse_mode="Markdown")
            except:
                pass


# ================= ЗАПУСК =================
async def main():
    asyncio.create_task(daily_reset_task())
    await dp.start_polling(bot)


if __name__ == "__main__":
    print("🤖 Бот запущен!")
    print(f"👑 Админы: {ADMIN_IDS}")
    print("⏰ Ежедневный сброс бонусов в 00:00")
    print("📌 Новые функции: Изменение имени | Списание баланса")
    asyncio.run(main())
