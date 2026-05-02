import asyncio
import sqlite3
import os
from datetime import datetime
from typing import Optional, Tuple

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================= КОНФИГУРАЦИЯ =================
BOT_TOKEN = "8655931539:AAE9DjvBYScMBrutC17TP0UaLBc_jj_bo2U"  # Замените на ваш токен от @BotFather
ADMIN_IDS = [7673683792]  # ID администраторов (укажите свои)
STAR_PRICE = 500  # Стоимость удаления в звёздах Telegram

# ================= СОСТОЯНИЯ FSM =================
class ReportStates(StatesGroup):
    waiting_for_username = State()  # Ожидание username для подачи заявки
    waiting_for_proof_photos = State()  # Ожидание доказательств (фото)
    waiting_for_proof_videos = State()  # Ожидание доказательств (видео)

class AdminAddStates(StatesGroup):
    waiting_for_username = State()  # Ожидание username для добавления
    waiting_for_label = State()  # Ожидание метки

class AdminRemoveStates(StatesGroup):
    waiting_for_username = State()  # Ожидание username для удаления

# ================= ИНИЦИАЛИЗАЦИЯ =================
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ================= РАБОТА С БАЗОЙ ДАННЫХ =================
def init_db():
    """Инициализация базы данных"""
    conn = sqlite3.connect('scambase.db')
    cur = conn.cursor()
    
    # Таблица пользователей в ScamBase
    cur.execute('''
        CREATE TABLE IF NOT EXISTS scambase (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            label TEXT DEFAULT 'Scammer',
            added_by INTEGER,
            added_date TEXT,
            proof_photos TEXT DEFAULT '',
            proof_videos TEXT DEFAULT ''
        )
    ''')
    
    # Таблица заявок от пользователей
    cur.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            reported_by INTEGER,
            proof_photos TEXT,
            proof_videos TEXT,
            status TEXT DEFAULT 'pending',
            report_date TEXT
        )
    ''')
    
    conn.commit()
    conn.close()


def is_in_scambase(username: str) -> bool:
    """Проверка, есть ли человек в ScamBase"""
    conn = sqlite3.connect('scambase.db')
    cur = conn.cursor()
    cur.execute('SELECT label FROM scambase WHERE username = ?', (username,))
    result = cur.fetchone()
    conn.close()
    return result[0] if result else None


def add_to_scambase(username: str, label: str, admin_id: int, proof_photos: str = '', proof_videos: str = '') -> bool:
    """Добавление человека в базу (только админ)"""
    try:
        conn = sqlite3.connect('scambase.db')
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO scambase (username, label, added_by, added_date, proof_photos, proof_videos)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (username, label, admin_id, datetime.now().isoformat(), proof_photos, proof_videos))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False


def remove_from_scambase(username: str) -> bool:
    """Удаление человека из базы"""
    conn = sqlite3.connect('scambase.db')
    cur = conn.cursor()
    cur.execute('DELETE FROM scambase WHERE username = ?', (username,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def update_label(username: str, new_label: str) -> bool:
    """Обновление метки пользователя"""
    if new_label not in ['Scammer', 'Face', 'Worker']:
        return False
    conn = sqlite3.connect('scambase.db')
    cur = conn.cursor()
    cur.execute('UPDATE scambase SET label = ? WHERE username = ?', (new_label, username))
    updated = cur.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def add_report(username: str, user_id: int, photos: list, videos: list) -> bool:
    """Добавление заявки на человека"""
    conn = sqlite3.connect('scambase.db')
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO reports (username, reported_by, proof_photos, proof_videos, status, report_date)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (username, user_id, ','.join(photos), ','.join(videos), 'pending', datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return True


def get_pending_reports() -> list:
    """Получение всех ожидающих заявок"""
    conn = sqlite3.connect('scambase.db')
    cur = conn.cursor()
    cur.execute('SELECT id, username, reported_by, proof_photos, proof_videos, report_date FROM reports WHERE status = "pending"')
    results = cur.fetchall()
    conn.close()
    return results


def approve_report(report_id: int, username: str, label: str, admin_id: int):
    """Одобрение заявки и добавление в базу"""
    conn = sqlite3.connect('scambase.db')
    cur = conn.cursor()
    
    # Обновляем статус заявки
    cur.execute('UPDATE reports SET status = "approved" WHERE id = ?', (report_id,))
    
    # Добавляем в основную базу
    cur.execute('''
        INSERT OR IGNORE INTO scambase (username, label, added_by, added_date)
        VALUES (?, ?, ?, ?)
    ''', (username, label, admin_id, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()


def reject_report(report_id: int):
    """Отклонение заявки"""
    conn = sqlite3.connect('scambase.db')
    cur = conn.cursor()
    cur.execute('UPDATE reports SET status = "rejected" WHERE id = ?', (report_id,))
    conn.commit()
    conn.close()


# ================= КЛАВИАТУРЫ =================
def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 Поиск в ScamBase", callback_data="search")
    builder.button(text="⭐ Удалить себя (500 ⭐)", callback_data="delete_self")
    builder.button(text="📝 Подать заявку на скаммера", callback_data="report")
    builder.button(text="📊 Статистика", callback_data="stats")
    
    if True:  # Проверка на админа будет в хендлере
        builder.button(text="👑 Админ-панель", callback_data="admin_panel")
    
    builder.adjust(1)
    return builder.as_markup()


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Панель администратора"""
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить в базу", callback_data="admin_add")
    builder.button(text="❌ Удалить из базы", callback_data="admin_remove")
    builder.button(text="🏷️ Выдать метку", callback_data="admin_label")
    builder.button(text="📋 Заявки от пользователей", callback_data="admin_reports")
    builder.button(text="🔙 Назад", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()


def label_keyboard(username: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора метки"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔴 Scammer", callback_data=f"label_{username}_Scammer")
    builder.button(text="🟡 Face", callback_data=f"label_{username}_Face")
    builder.button(text="🟢 Worker", callback_data=f"label_{username}_Worker")
    builder.button(text="🔙 Отмена", callback_data="admin_panel")
    builder.adjust(1)
    return builder.as_markup()


# ================= ОБЩИЕ ХЕНДЛЕРЫ =================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    await message.answer(
        "👋 Добро пожаловать в ScamBase Bot!\n\n"
        "🔍 Я помогу проверить, есть ли человек в базе скамеров.\n"
        "📝 Также ты можешь подать заявку на добавление скамера с доказательствами.\n\n"
        "Используй кнопки ниже для навигации:",
        reply_markup=main_menu_keyboard()
    )


@dp.callback_query(F.data == "search")
async def search_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос username для поиска"""
    await callback.message.answer("🔍 Введите username человека для проверки (без @):")
    await callback.answer()
    await state.set_state("waiting_for_search")


@dp.message(StateFilter("waiting_for_search"))
async def perform_search(message: Message, state: FSMContext):
    """Выполнение поиска"""
    username = message.text.strip().replace('@', '')
    label = is_in_scambase(username)
    
    if label:
        await message.answer(
            f"⚠️ <b>РЕЗУЛЬТАТ ПОИСКА</b> ⚠️\n\n"
            f"👤 Username: @{username}\n"
            f"🏷️ Метка: {label}\n"
            f"📌 Статус: <b>В БАЗЕ СКАМЕРОВ</b>\n\n"
            f"Будьте осторожны в общении с этим человеком!",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"✅ <b>РЕЗУЛЬТАТ ПОИСКА</b> ✅\n\n"
            f"👤 Username: @{username}\n"
            f"📌 Статус: <b>НЕ НАЙДЕН В БАЗЕ</b>\n\n"
            f"Человек не числится в ScamBase.",
            parse_mode="HTML"
        )
    
    await state.clear()


@dp.callback_query(F.data == "stats")
async def show_stats(callback: CallbackQuery):
    """Показать статистику"""
    conn = sqlite3.connect('scambase.db')
    cur = conn.cursor()
    
    cur.execute('SELECT COUNT(*) FROM scambase')
    total_scammers = cur.fetchone()[0]
    
    cur.execute('SELECT label, COUNT(*) FROM scambase GROUP BY label')
    labels_stats = cur.fetchall()
    
    cur.execute('SELECT COUNT(*) FROM reports WHERE status = "pending"')
    pending_reports = cur.fetchone()[0]
    
    conn.close()
    
    stats_text = f"📊 <b>Статистика ScamBase</b> 📊\n\n"
    stats_text += f"👥 Всего в базе: <b>{total_scammers}</b>\n"
    stats_text += f"📋 Ожидающих заявок: <b>{pending_reports}</b>\n\n"
    stats_text += "<b>По меткам:</b>\n"
    
    for label, count in labels_stats:
        emoji = "🔴" if label == "Scammer" else "🟡" if label == "Face" else "🟢"
        stats_text += f"{emoji} {label}: {count}\n"
    
    await callback.message.answer(stats_text, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "delete_self")
async def delete_self_prompt(callback: CallbackQuery):
    """Запрос на удаление себя из базы за звёзды"""
    user_label = is_in_scambase(f"user_{callback.from_user.id}")
    
    if not user_label:
        await callback.message.answer("✅ Вы не найдены в базе ScamBase. Удаление не требуется.")
        await callback.answer()
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⭐ Удалить за {STAR_PRICE} звёзд", callback_data="confirm_star_delete")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_menu")]
    ])
    
    await callback.message.answer(
        f"⚠️ <b>Вы находитесь в ScamBase!</b> ⚠️\n\n"
        f"Ваша метка: {user_label}\n\n"
        f"Вы можете удалить себя из базы за <b>{STAR_PRICE} ⭐</b>\n\n"
        f"Нажмите на кнопку ниже, чтобы оплатить звёздами Telegram.",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(F.data == "confirm_star_delete")
async def process_star_delete(callback: CallbackQuery):
    """Обработка удаления за звёзды"""
    user_id = callback.from_user.id
    username = f"user_{user_id}"
    
    try:
        # Создаём инвойс для оплаты звёздами
        await bot.send_invoice(
            chat_id=user_id,
            title="Удаление из ScamBase",
            description=f"Удаление вашего профиля из базы ScamBase",
            payload=f"delete_{user_id}",
            currency="XTR",  # Telegram Stars
            prices=[types.LabeledPrice(label="Удаление", amount=STAR_PRICE)],
            need_name=False,
            need_phone_number=False,
            need_email=False
        )
        await callback.answer("💫 Отправлен счёт на оплату звёздами!")
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)}\nПопробуйте позже.")
        await callback.answer()


@dp.pre_checkout_query()
async def pre_checkout_query(pre_checkout: types.PreCheckoutQuery):
    """Проверка перед оплатой"""
    await pre_checkout.answer(ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    """Успешная оплата - удаляем пользователя"""
    user_id = message.from_user.id
    username = f"user_{user_id}"
    
    if remove_from_scambase(username):
        await message.answer(
            "✅ <b>Оплата получена! Вы удалены из ScamBase.</b> ✅\n\n"
            "Ваше имя больше не числится в базе скамеров.\n"
            "Спасибо за оплату звёздами! 🌟",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard()
        )
    else:
        await message.answer(
            "❌ Ошибка: вас не было в базе данных.\n"
            "Возможно, вы уже были удалены ранее.",
            reply_markup=main_menu_keyboard()
        )


# ================= ЗАЯВКИ НА СКАММЕРА =================
@dp.callback_query(F.data == "report")
async def report_start(callback: CallbackQuery, state: FSMContext):
    """Начало подачи заявки"""
    await callback.message.answer(
        "📝 <b>Подача заявки на скамера</b>\n\n"
        "Введите username человека, которого вы хотите добавить в базу (без @):",
        parse_mode="HTML"
    )
    await callback.answer()
    await state.set_state(ReportStates.waiting_for_username)


@dp.message(ReportStates.waiting_for_username)
async def report_get_username(message: Message, state: FSMContext):
    """Получение username для заявки"""
    username = message.text.strip().replace('@', '')
    
    # Проверяем, нет ли уже в базе
    if is_in_scambase(username):
        await message.answer(
            "⚠️ Этот человек уже находится в ScamBase!\n\n"
            "Вы можете проверить его через поиск.",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return
    
    await state.update_data(report_username=username)
    await message.answer(
        "📸 Теперь отправьте <b>фото-доказательства</b> (можно несколько фото в одном сообщении)\n\n"
        "Отправьте 'готово', если фото нет:",
        parse_mode="HTML"
    )
    await state.set_state(ReportStates.waiting_for_proof_photos)


@dp.message(ReportStates.waiting_for_proof_photos)
async def report_get_photos(message: Message, state: FSMContext):
    """Получение фото доказательств"""
    photos = []
    
    if message.photo:
        photos = [message.photo[-1].file_id]
    elif message.text and message.text.lower() == 'готово':
        pass
    elif message.text:
        await message.answer("Пожалуйста, отправьте фото или напишите 'готово'")
        return
    
    await state.update_data(report_photos=photos)
    
    await message.answer(
        "🎥 Теперь отправьте <b>видео-доказательства</b> (можно несколько видео)\n\n"
        "Отправьте 'готово', если видео нет:",
        parse_mode="HTML"
    )
    await state.set_state(ReportStates.waiting_for_proof_videos)


@dp.message(ReportStates.waiting_for_proof_videos)
async def report_get_videos(message: Message, state: FSMContext):
    """Получение видео доказательств"""
    videos = []
    
    if message.video:
        videos = [message.video.file_id]
    elif message.text and message.text.lower() == 'готово':
        pass
    elif message.text:
        await message.answer("Пожалуйста, отправьте видео или напишите 'готово'")
        return
    
    data = await state.get_data()
    username = data.get('report_username')
    photos = data.get('report_photos', [])
    
    # Сохраняем заявку
    add_report(username, message.from_user.id, photos, videos)
    
    # Уведомляем админов
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📋 <b>НОВАЯ ЗАЯВКА В SCAMBASE!</b>\n\n"
                f"👤 Пользователь: @{username}\n"
                f"📝 Подал: {message.from_user.full_name} (ID: {message.from_user.id})\n"
                f"📸 Фото: {len(photos)} шт.\n"
                f"🎥 Видео: {len(videos)} шт.\n\n"
                f"Используйте админ-панель для рассмотрения заявки.",
                parse_mode="HTML"
            )
        except:
            pass
    
    await message.answer(
        "✅ <b>Заявка успешно отправлена!</b> ✅\n\n"
        f"👤 Человек: @{username}\n"
        f"📸 Доказательств: {len(photos)} фото, {len(videos)} видео\n\n"
        "Администраторы рассмотрят вашу заявку в ближайшее время.\n"
        "Спасибо за помощь в борьбе со скамерами! 🙏",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )
    
    await state.clear()


# ================= АДМИН-ПАНЕЛЬ =================
def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь админом"""
    return user_id in ADMIN_IDS


@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    """Панель администратора"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён! Вы не администратор.", show_alert=True)
        return
    
    await callback.message.answer(
        "👑 <b>Панель администратора ScamBase</b> 👑\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_add")
async def admin_add_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос username для добавления"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён!", show_alert=True)
        return
    
    await callback.message.answer("➕ Введите username для добавления в базу (без @):")
    await callback.answer()
    await state.set_state(AdminAddStates.waiting_for_username)


@dp.message(AdminAddStates.waiting_for_username)
async def admin_add_get_username(message: Message, state: FSMContext):
    """Получение username и запрос метки"""
    username = message.text.strip().replace('@', '')
    
    if is_in_scambase(username):
        await message.answer("⚠️ Этот пользователь уже есть в базе!")
        await state.clear()
        return
    
    await state.update_data(add_username=username)
    await message.answer(
        "🏷️ Выберите метку для пользователя:",
        reply_markup=label_keyboard(username)
    )
    await state.clear()  # Очищаем, так как дальше callback


@dp.callback_query(F.data.startswith("label_"))
async def admin_set_label(callback: CallbackQuery):
    """Установка метки при добавлении"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён!", show_alert=True)
        return
    
    _, username, label = callback.data.split("_")
    
    if add_to_scambase(username, label, callback.from_user.id):
        await callback.message.answer(
            f"✅ Пользователь @{username} добавлен в ScamBase с меткой {label}!"
        )
    else:
        await callback.message.answer(f"❌ Ошибка: пользователь @{username} уже существует или ошибка БД.")
    
    await callback.answer()
    await callback.message.answer("👑 Админ-панель:", reply_markup=admin_panel_keyboard())


@dp.callback_query(F.data == "admin_remove")
async def admin_remove_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос username для удаления"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён!", show_alert=True)
        return
    
    await callback.message.answer("❌ Введите username для удаления из базы (без @):")
    await callback.answer()
    await state.set_state(AdminRemoveStates.waiting_for_username)


@dp.message(AdminRemoveStates.waiting_for_username)
async def admin_remove_user(message: Message, state: FSMContext):
    """Удаление пользователя админом"""
    username = message.text.strip().replace('@', '')
    
    if remove_from_scambase(username):
        await message.answer(f"✅ Пользователь @{username} удалён из ScamBase!")
    else:
        await message.answer(f"❌ Пользователь @{username} не найден в базе.")
    
    await state.clear()
    await message.answer("👑 Админ-панель:", reply_markup=admin_panel_keyboard())


@dp.callback_query(F.data == "admin_label")
async def admin_label_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос username для выдачи метки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён!", show_alert=True)
        return
    
    await callback.message.answer("🏷️ Введите username для изменения метки (без @):")
    await callback.answer()
    await state.set_state("waiting_label_username")


@dp.message(StateFilter("waiting_label_username"))
async def admin_label_get_username(message: Message, state: FSMContext):
    """Получение username для смены метки"""
    username = message.text.strip().replace('@', '')
    
    if not is_in_scambase(username):
        await message.answer("❌ Пользователь не найден в базе!")
        await state.clear()
        return
    
    await state.update_data(label_username=username)
    await message.answer(
        f"🏷️ Выберите новую метку для @{username}:",
        reply_markup=label_keyboard(username)
    )
    await state.clear()


@dp.callback_query(F.data.startswith("change_label_"))
async def admin_change_label(callback: CallbackQuery):
    """Изменение метки у существующего пользователя"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён!", show_alert=True)
        return
    
    _, username, new_label = callback.data.split("_")
    
    if update_label(username, new_label):
        await callback.message.answer(f"✅ Метка для @{username} изменена на {new_label}!")
    else:
        await callback.message.answer(f"❌ Ошибка: пользователь @{username} не найден.")
    
    await callback.answer()
    await callback.message.answer("👑 Админ-панель:", reply_markup=admin_panel_keyboard())


@dp.callback_query(F.data == "admin_reports")
async def admin_show_reports(callback: CallbackQuery):
    """Показать все заявки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён!", show_alert=True)
        return
    
    reports = get_pending_reports()
    
    if not reports:
        await callback.message.answer("📭 Нет ожидающих заявок.")
        await callback.answer()
        return
    
    for report in reports:
        report_id, username, reported_by, photos, videos, date = report
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить (Scammer)", callback_data=f"approve_{report_id}_{username}_Scammer"),
                InlineKeyboardButton(text="✅ Одобрить (Face)", callback_data=f"approve_{report_id}_{username}_Face"),
                InlineKeyboardButton(text="✅ Одобрить (Worker)", callback_data=f"approve_{report_id}_{username}_Worker")
            ],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{report_id}")]
        ])
        
        text = f"📋 <b>Заявка #{report_id}</b>\n"
        text += f"👤 Username: @{username}\n"
        text += f"👮 Подал: ID {reported_by}\n"
        text += f"📅 Дата: {date[:19]}\n"
        text += f"📸 Фото: {len(photos.split(',')) if photos else 0}\n"
        text += f"🎥 Видео: {len(videos.split(',')) if videos else 0}\n"
        
        await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    
    await callback.answer()


@dp.callback_query(F.data.startswith("approve_"))
async def admin_approve_report(callback: CallbackQuery):
    """Одобрение заявки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён!", show_alert=True)
        return
    
    _, report_id, username, label = callback.data.split("_")
    report_id = int(report_id)
    
    approve_report(report_id, username, label, callback.from_user.id)
    
    await callback.message.answer(f"✅ Заявка #{report_id} одобрена! @{username} добавлен в базу с меткой {label}.")
    await callback.answer()


@dp.callback_query(F.data.startswith("reject_"))
async def admin_reject_report(callback: CallbackQuery):
    """Отклонение заявки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён!", show_alert=True)
        return
    
    report_id = int(callback.data.split("_")[1])
    reject_report(report_id)
    
    await callback.message.answer(f"❌ Заявка #{report_id} отклонена.")
    await callback.answer()


@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    """Возврат в главное меню"""
    await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    await callback.answer()


# ================= ЗАПУСК БОТА =================
async def main():
    """Запуск бота"""
    init_db()
    print("✅ Бот ScamBase запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
