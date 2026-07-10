from mimetypes import init

from aiogram import Bot, Dispatcher

import asyncio
import os
from dotenv import load_dotenv
import logging

from app.handlers import router
from app.database.models import init_db, async_session
from app.database.middleware import DataBaseMiddleWare

load_dotenv()

bot = Bot(token=os.environ["TG_TOKEN"])
dp = Dispatcher()

async def main():
    logging.basicConfig(level=logging.INFO)
    dp.include_router(router)

    dp.message.middleware(DataBaseMiddleWare(async_session))
    dp.callback_query.middleware(DataBaseMiddleWare(async_session))

    @dp.startup()
    async def on_startup():
        await init_db()
        print('Database initialized')

    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped")
