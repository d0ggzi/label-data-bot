import asyncio
import logging
import sys
from typing import Any, Dict

from aiogram import Bot, Dispatcher, F, Router, html
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
import psycopg2
import re
import config


def remove_emojis(data):
    emoj = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
        u"\U00002500-\U00002BEF"  # chinese char
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        u"\U0001f926-\U0001f937"
        u"\U00010000-\U0010ffff"
        u"\u2640-\u2642" 
        u"\u2600-\u2B55"
        u"\u200d"
        u"\u23cf"
        u"\u23e9"
        u"\u231a"
        u"\ufe0f"  # dingbats
        u"\u3030"
                      "]+", re.UNICODE)
    return re.sub(emoj, '', data)

conn = psycopg2.connect(f"""
    host=rc1b-2wfn2w8hz6rt5hfv.mdb.yandexcloud.net
    port=6432
    sslmode=verify-full
    dbname=db1
    user={config.dbuser}
    password={config.password}
    target_session_attrs=read-write
""")
q = conn.cursor()

form_router = Router()


class Form(StatesGroup):
    reply_message = State()
    choose_label = State()


@form_router.message(CommandStart())
async def command_start(message: Message, state: FSMContext) -> None:
    await state.set_state(Form.reply_message)
    await message.answer(
        "Привет, {0}! Отправь мне какой-нибудь пост и пометь его лейблом 0 (обычный пост) или 1 (реклама)".format(message.from_user.first_name),
        reply_markup=ReplyKeyboardRemove(),
    )


@form_router.message(Command("cancel"))
@form_router.message(F.text.casefold() == "cancel")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        return

    logging.info("Cancelling state %r", current_state)
    await state.clear()
    await message.answer(
        "Cancelled.",
        reply_markup=ReplyKeyboardRemove(),
    )


@form_router.message(Form.reply_message)
async def process_name(message: Message, state: FSMContext) -> None:
    text = message.text if message.text is not None else message.caption
    if text is not None: 
        if message.caption is not None and message.caption_entities is not None:
            for entity in message.caption_entities:
                if entity.url is not None:
                    text += " " + entity.url + " "
        text = remove_emojis(text).replace('\n', '')
        await state.set_data({"text": text})
        await message.answer("Теперь выбери лейбл: 0 - обычный пост, 1 - реклама", reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [
                        KeyboardButton(text="1"),
                        KeyboardButton(text="0"),
                    ]
                ],
                resize_keyboard=True,
            ),
            )
        await state.set_state(Form.choose_label)
    else:
        await message.answer("Не удалось получить текст сообщения, попробуйте другой пост", reply_markup=ReplyKeyboardRemove())

@form_router.message(Form.choose_label, F.text.in_({"0", "1"}))
async def process_choosing_label(message: Message, state: FSMContext) -> None:
    label = message.text
    post_text = await state.get_data()
    try:
        q.execute("""INSERT INTO posts (text, post_label) VALUES (%s, %s);""", (post_text['text'], label))
        conn.commit()
        await message.answer("Спасибо! Жду следующий пост", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.reply_message)
    except:
        await message.answer("Ошибка добавления в базу данных, отправьте скриншот @dggz1", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.reply_message)

@form_router.message(Form.choose_label)
async def process_unknown_write_bots(message: Message) -> None:
    await message.reply("Не понимаю тебя(")


async def on_shutdown(bot: Bot):
    conn.close()

async def main():
    bot = Bot(token=config.BOT_TOKEN, parse_mode=ParseMode.HTML)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.shutdown.register(on_shutdown)
    dp.include_router(form_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())