import asyncio
import random
import json
import os
from datetime import datetime, date, timedelta
from collections import defaultdict

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.utils.markdown import hbold, hcode
from aiogram.types.input_file import FSInputFile

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "8574767944:AAFbyzaPW7T7e5ieFkKdPcVOAYGe124ovKE"  # Замени на свой токен!
ADMIN_IDS = [7673683792]  # Сюда вставь свой Telegram ID (целое число)

# Файл для хранения данных пользователей
DATA_FILE = "user_data.json"

# ========== ЗАГРУЗКА/СОХРАНЕНИЕ ДАННЫХ ==========
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Структура данных:
# {
#   "user_id": {
#       "balance": 1000,
#       "last_daily": "2025-01-01",
#       "wins": 0,
#       "losses": 0
#   }
# }

# Кэш в памяти для быстрого доступа
user_cache = load_data()

def get_user(user_id):
    uid = str(user_id)
    if uid not in user_cache:
        user_cache[uid] = {
            "balance": 1000,
            "last_daily": None,
            "wins": 0,
            "losses": 0
        }
    return user_cache[uid]

def save_user(user_id):
    save_data(user_cache)

# ========== АНИМИРОВАННЫЕ КУБИКИ (TG анимация через dice) ==========
async def roll_dice(message: Message, bet: int, choice: str = None):
    """Бросает кубик в Telegram с анимацией и возвращает результат"""
    dice_msg = await message.answer_dice(emoji="🎲")
    value = dice_msg.dice.value
    return value

# Дуэль кубиков: два броска
async def dice_duel(message: Message, bet: int, player1_id: int, player2_id: int):
    """Анимированная дуэль кубиков. Возвращает (winner_id, value1, value2)"""
    # Первый игрок бросает
    msg1 = await message.answer_dice(emoji="🎲")
    val1 = msg1.dice.value
    await asyncio.sleep(1)  # небольшая пауза для драматичности
    
    # Второй игрок бросает
    msg2 = await message.answer_dice(emoji="🎲")
    val2 = msg2.dice.value
    
    if val1 > val2:
        return player1_id, val1, val2
    elif val2 > val1:
        return player2_id, val1, val2
    else:
        return None, val1, val2  # Ничья

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    get_user(user_id)
    save_user(user_id)
    
    await message.answer(
        f"🎰 Привет, {message.from_user.first_name}!\n\n"
        f"Добро пожаловать в Casino Bot!\n"
        f"Твой баланс: {get_user(user_id)['balance']} монет\n\n"
        f"🎲 Команды для беседы:\n"
        f"/dice_battle [сумма] - создать дуэль на кубиках\n"
        f"/evenodd [сумма] [чёт/нечёт] - игра чёт/нечёт\n"
        f"/football [сумма] - игра в футбол (анимация)\n"
        f"/daily - ежедневный бонус +500\n"
        f"/balance - показать баланс\n\n"
        f"👑 Админ-команды:\n"
        f"/chat_info - инфо о беседе\n"
        f"/give [user_id] [сумма] - выдать валюту\n"
        f"/ping - пинг бота\n"
        f"/stats - статистика бота\n"
        f"/user_stats [user_id] - статистика игрока"
    )

# Ежедневный бонус
@dp.message(Command("daily"))
async def daily_bonus(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    today = date.today().isoformat()
    if user["last_daily"] == today:
        await message.answer("❌ Ты уже получал бонус сегодня! Приходи завтра.")
        return
    
    user["balance"] += 500
    user["last_daily"] = today
    save_user(user_id)
    
    await message.answer(f"✅ Ежедневный бонус +500 монет!\n💰 Твой баланс: {user['balance']}")

# Баланс
@dp.message(Command("balance"))
async def show_balance(message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    await message.answer(f"💰 Твой баланс: {user['balance']} монет")

# ========== ИГРА 1: КУБИК-ДУЭЛЬ (создание ставки) ==========
# Хранилище активных дуэлей: {creator_id: {"bet": amount, "challenger": None}}
active_duels = {}

@dp.message(Command("dice_battle"))
async def cmd_dice_battle(message: Message, command: CommandObject):
    if not message.chat.type in ["group", "supergroup"]:
        await message.answer("❌ Эта игра доступна ТОЛЬКО в беседах!")
        return
    
    args = command.args
    if not args or not args.isdigit():
        await message.answer("❌ Использование: /dice_battle [сумма ставки]")
        return
    
    bet = int(args)
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if bet <= 0:
        await message.answer("❌ Ставка должна быть положительной!")
        return
    if user["balance"] < bet:
        await message.answer(f"❌ Не хватает монет! Нужно {bet}, у тебя {user['balance']}")
        return
    
    # Создаём дуэль
    active_duels[user_id] = {"bet": bet, "creator_id": user_id, "challenger": None}
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ Принять бой!", callback_data=f"accept_duel_{user_id}")]
    ])
    
    await message.answer(
        f"🎲 {message.from_user.first_name} создал дуэль на кубиках!\n"
        f"💰 Ставка: {bet} монет\n"
        f"⚔️ Кто примет вызов? Нажми на кнопку!",
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("accept_duel_"))
async def accept_duel(callback: CallbackQuery):
    creator_id = int(callback.data.split("_")[2])
    challenger_id = callback.from_user.id
    
    if challenger_id == creator_id:
        await callback.answer("❌ Нельзя играть с самим собой!", show_alert=True)
        return
    
    duel = active_duels.get(creator_id)
    if not duel:
        await callback.answer("❌ Дуэль уже завершена или отменена!", show_alert=True)
        return
    
    if duel["challenger"] is not None:
        await callback.answer("❌ На эту дуэль уже кто-то согласился!", show_alert=True)
        return
    
    creator = get_user(creator_id)
    challenger = get_user(challenger_id)
    bet = duel["bet"]
    
    if challenger["balance"] < bet:
        await callback.answer(f"❌ Не хватает {bet} монет для участия!", show_alert=True)
        return
    
    # Блокируем ставки
    creator["balance"] -= bet
    challenger["balance"] -= bet
    save_user(creator_id)
    save_user(challenger_id)
    duel["challenger"] = challenger_id
    
    await callback.message.edit_text(
        f"⚔️ Бой начинается!\n"
        f"{callback.from_user.first_name} принял вызов {callback.message.from_user.first_name}\n"
        f"💰 Ставка: {bet} монет\n\n"
        f"🎲 Бросаем кубики..."
    )
    
    # Проводим дуэль
    winner_id, val1, val2 = await dice_duel(callback.message, bet, creator_id, challenger_id)
    
    if winner_id is None:
        await callback.message.answer(
            f"🤝 НИЧЬЯ! Оба выбросили {val1}\n"
            f"Ставки возвращаются игрокам."
        )
        creator["balance"] += bet
        challenger["balance"] += bet
        save_user(creator_id)
        save_user(challenger_id)
    else:
        winner = get_user(winner_id)
        winner["balance"] += bet * 2
        winner["wins"] += 1
        loser_id = creator_id if winner_id == challenger_id else challenger_id
        loser = get_user(loser_id)
        loser["losses"] += 1
        save_user(winner_id)
        save_user(loser_id)
        
        winner_name = (await bot.get_chat(winner_id)).first_name if winner_id != callback.from_user.id else callback.from_user.first_name
        
        await callback.message.answer(
            f"🏆 ПОБЕДИТЕЛЬ: {winner_name}!\n"
            f"🎲 {val1} vs {val2}\n"
            f"💰 Выигрыш: {bet*2} монет!"
        )
    
    # Удаляем дуэль
    del active_duels[creator_id]

# ========== ИГРА 2: ЧЁТ / НЕЧЁТ ==========
@dp.message(Command("evenodd"))
async def cmd_evenodd(message: Message, command: CommandObject):
    if not message.chat.type in ["group", "supergroup"]:
        await message.answer("❌ Эта игра доступна ТОЛЬКО в беседах!")
        return
    
    args = command.args
    if not args:
        await message.answer("❌ Использование: /evenodd [сумма] [чёт/нечёт]\nПример: /evenodd 100 чёт")
        return
    
    parts = args.split()
    if len(parts) != 2 or not parts[0].isdigit() or parts[1] not in ["чёт", "нечет", "чет", "нечет"]:
        await message.answer("❌ Неверный формат! Пример: /evenodd 100 чёт")
        return
    
    bet = int(parts[0])
    choice_normalized = "чёт" if parts[1].startswith("ч") else "нечёт"
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if user["balance"] < bet:
        await message.answer(f"❌ Не хватает монет! Нужно {bet}, у тебя {user['balance']}")
        return
    
    user["balance"] -= bet
    save_user(user_id)
    
    # Анимированный кубик
    dice_msg = await message.answer_dice(emoji="🎲")
    value = dice_msg.dice.value
    is_even = (value % 2 == 0)
    result = "чёт" if is_even else "нечёт"
    
    if choice_normalized == result:
        win_amount = bet * 2
        user["balance"] += win_amount
        user["wins"] += 1
        save_user(user_id)
        await message.answer(
            f"🎲 Выпало: {value} - {result.upper()}!\n"
            f"✅ Ты угадал! +{win_amount} монет\n"
            f"💰 Новый баланс: {user['balance']}"
        )
    else:
        user["losses"] += 1
        save_user(user_id)
        await message.answer(
            f"🎲 Выпало: {value} - {result.upper()}!\n"
            f"❌ Ты не угадал. Потеряно {bet} монет\n"
            f"💰 Новый баланс: {user['balance']}"
        )

# ========== ИГРА 3: ФУТБОЛ (анимированный) ==========
@dp.message(Command("football"))
async def cmd_football(message: Message, command: CommandObject):
    if not message.chat.type in ["group", "supergroup"]:
        await message.answer("❌ Эта игра доступна ТОЛЬКО в беседах!")
        return
    
    args = command.args
    if not args or not args.isdigit():
        await message.answer("❌ Использование: /football [сумма ставки]")
        return
    
    bet = int(args)
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if user["balance"] < bet:
        await message.answer(f"❌ Не хватает монет! Нужно {bet}, у тебя {user['balance']}")
        return
    
    user["balance"] -= bet
    save_user(user_id)
    
    # Анимированный футбольный мяч (⚽)
    await message.answer("⚽ Матч начинается...")
    await asyncio.sleep(0.5)
    
    # В Telegram есть специальный эмодзи для футбола - это dice с эмодзи ⚽
    # Но dice с ⚽ даёт случайный результат 1-5 (голы)
    football_msg = await message.answer_dice(emoji="⚽")
    goals = football_msg.dice.value  # от 1 до 5
    
    if goals >= 4:
        # Победа (ставка умножается на коэффициент ~2.5)
        win_amount = int(bet * 2.5)
        user["balance"] += win_amount
        user["wins"] += 1
        save_user(user_id)
        await message.answer(
            f"🏆 ГОЛ! Твоя команда забила {goals} гола!\n"
            f"✅ Ты выиграл {win_amount} монет!\n"
            f"💰 Новый баланс: {user['balance']}"
        )
    else:
        user["losses"] += 1
        save_user(user_id)
        await message.answer(
            f"😭 Твоя команда проиграла со счётом {goals}-{random.randint(goals+1, 5)}\n"
            f"❌ Потеряно {bet} монет\n"
            f"💰 Новый баланс: {user['balance']}"
        )

# ========== АДМИН-КОМАНДЫ ==========
def is_admin(user_id):
    return user_id in ADMIN_IDS

# Информация о беседе
@dp.message(Command("chat_info"))
async def chat_info(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для администратора бота!")
        return
    
    chat = message.chat
    info = (
        f"📊 Информация о беседе:\n"
        f"🆔 ID: {chat.id}\n"
        f"📛 Название: {chat.title}\n"
        f"👥 Тип: {chat.type}\n"
        f"👤 Участников: {await bot.get_chat_member_count(chat.id)}"
    )
    await message.answer(info)

# Выдать валюту (можно в ЛС и беседе)
@dp.message(Command("give"))
async def give_money(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для администратора бота!")
        return
    
    args = command.args
    if not args:
        await message.answer("❌ Использование: /give [user_id] [сумма]")
        return
    
    parts = args.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("❌ Неверный формат! Пример: /give 123456789 1000")
        return
    
    target_id = int(parts[0])
    amount = int(parts[1])
    
    user = get_user(target_id)
    user["balance"] += amount
    save_user(target_id)
    
    await message.answer(f"✅ Выдано {amount} монет пользователю ID {target_id}")

# Пинг бота
@dp.message(Command("ping"))
async def ping_bot(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для администратора бота!")
        return
    await message.answer("🏓 Понг! Бот работает.")

# Статистика бота
@dp.message(Command("stats"))
async def bot_stats(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для администратора бота!")
        return
    
    total_users = len(user_cache)
    total_balance = sum(u["balance"] for u in user_cache.values())
    total_wins = sum(u["wins"] for u in user_cache.values())
    
    await message.answer(
        f"📈 Статистика бота:\n"
        f"👥 Пользователей: {total_users}\n"
        f"💰 Общий баланс: {total_balance}\n"
        f"🏆 Всего побед: {total_wins}"
    )

# Статистика пользователя
@dp.message(Command("user_stats"))
async def user_stats(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только для администратора бота!")
        return
    
    args = command.args
    if not args or not args.isdigit():
        await message.answer("❌ Использование: /user_stats [user_id]")
        return
    
    user_id = int(args)
    user = get_user(user_id)
    
    try:
        tg_user = await bot.get_chat(user_id)
        name = tg_user.first_name
    except:
        name = f"ID{user_id}"
    
    await message.answer(
        f"📊 Статистика игрока {name}:\n"
        f"💰 Баланс: {user['balance']}\n"
        f"🏆 Побед: {user['wins']}\n"
        f"💀 Поражений: {user['losses']}"
    )

# ========== ЗАПУСК БОТА ==========
async def main():
    print("🤖 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
