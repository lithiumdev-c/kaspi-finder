from aiogram.filters import Command, CommandStart
from aiogram import F, Router
from aiogram.filters.command import CommandObject
from aiogram.types import Message, CallbackQuery
from sqlalchemy.sql.functions import user

import app.keyboards as kb
from app.database.models import User

from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import statistics
import asyncio
import random
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

#Constants

CATEGORIES_MAP = {
    'https://kaspi.kz/shop/c/desktop%20computers/': "Настольные компьютеры",
    'https://kaspi.kz/shop/c/notebooks%20and%20accessories/': "Ноутбуки и аксессуары",
    'https://kaspi.kz/shop/c/smartphones%20and%20gadgets/': "Смартфоны и гаджеты",
    'https://kaspi.kz/shop/c/smartphones/': "Смартфоны",
    'https://kaspi.kz/shop/c/portable%20speakers/': "Портативные колонки",
    'https://kaspi.kz/shop/c/peripherals/': "Периферийные устройства",
    'https://kaspi.kz/shop/c/fashion/': "Одежда",
    'https://kaspi.kz/shop/c/women fashion/': "Женская одежда",
    'https://kaspi.kz/shop/c/men fashion/': "Мужская одежда",
    'https://kaspi.kz/shop/c/microcomputers/': "Микрокомпьютеры",
}

CATEGORIES_TO_MONITOR = list(CATEGORIES_MAP.keys())
delete_words = ['ноутбук', 'смартфон', 'планшет', 'мышь', 'микрокомпьютер', 'одежда', 'футболка', 'наушники', 'колонка', 'штаны', 'шорты', 'рубашка', 'электронные книги', 'моноблок',  'микроконтроллер', 'портативная колонка', 'колонка']

#Kaspi shop parsing functions

#Extracts brand from product title
def extract_brand(title: str):
    clean_title = title.lower().strip()
    for word in delete_words:
        if clean_title.startswith(word):
            clean_title = clean_title[len(word):].strip()
    words = clean_title.split()
    return words[0].upper() if words else 'UNKNOWN'


#Parses a category page and extracts product data with Playwright_Stealth
async def kaspi_parser(category_url: str):
    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True, args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-setuid-sandbox"
                    ])
        context = await browser.new_context(
            viewport = {"width": 1920, "height": 1080},
            timezone_id="Asia/Almaty",
            locale="ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)

        try:
            await page.goto(category_url, wait_until='domcontentloaded')
            await asyncio.sleep(random.uniform(2.0, 4.0))
            await page.locator('.item-card, [data-product-id]').first.wait_for(timeout=7000)
        except Exception as e:
            await browser.close()
            return 'Не удалось прогрузить сайт и получить данные'

        raw_products = await page.locator('.item-card, [data-product-id]').all()
        brands_data = defaultdict(list)

        for item in raw_products:
            try:
                title_selector = item.locator('.item-card__name-link, a.ch-link')
                if await title_selector.count() == 0:
                    continue

                link_element = title_selector.first
                link = await link_element.get_attribute('href')
                raw_title = await link_element.inner_text()
                raw_title = raw_title.strip()

                if not raw_title or '\n' in raw_title or 'отзывов' in raw_title:
                    continue
                brand = extract_brand(raw_title)

                if brand == 'UNKNOWN' or len(brand) < 2:
                    continue

                price_txt = ""
                price_elements = item.locator('.item-card__prices-price, .item-card__price')
                if await price_elements.count() > 0:
                    price_txt = await price_elements.first.inner_text()
                else:
                    full_text = await item.inner_text()
                    for line in full_text.split('\n'):
                        if '₸' in line or 'тг' in line:
                            price_txt = line
                            break

                digits = "".join(filter(str.isdigit, price_txt))
                if not digits:
                    continue
                price = int(digits)

                if price < 100 or brand == 'UNKNOWN':
                    continue

                brands_data[brand].append({'title': raw_title, 'price': price, 'link': link or ''})
            except Exception:
                continue

        await browser.close()

        print(f" Собрано брендов: {len(brands_data)}. Сводка: {list(brands_data.keys())}")

        report_messages = []
        for brand, products in brands_data.items():
            brand_prices = [p['price'] for p in products]
            if len(brand_prices) < 2:
                continue

            brand_median = statistics.median(brand_prices)

            brand_details = []
            for prod in products:
                discount = ((brand_median - prod['price']) / brand_median) * 100
                if prod['price'] < brand_median and discount >= 5:
                    link_url = f"https://kaspi.kz{prod['link'] if prod['link'].startswith('/') else '/' + prod['link']}"
                    deal_text = (
                        f"🔥 *{prod['title']}*\n"
                        f"💰 Цена: *{prod['price']:,.0f} ₸* (Рынок: {brand_median:,.0f} ₸)\n"
                        f"📉 Выгода: *{discount:.1f}%*\n"
                        f"🔗 [Купить на Kaspi]({link_url})\n"
                    )
                    brand_details.append(deal_text)

            if brand_details:
                report_messages.append(f"📦 *БРЕНД: {brand}*")
                report_messages.extend(brand_details)
                report_messages.append('-' * 15)
        return "\n".join(report_messages) if report_messages else None

#Aiogram bot router setup and handlers
router = Router()
@router.message(CommandStart())
async def cmd_start(msg: Message, session: AsyncSession, command: CommandObject):
    if msg.from_user is None or msg.bot is None:
        return

    user_id = msg.from_user.id
    username = msg.from_user.username

    result = await session.execute(select(User).filter_by(id=user_id))
    current_user = result.scalar_one_or_none()
    if current_user:
        await msg.answer('🛒 Добро пожаловать в KaspiFinder - парсер магазина Kaspi\n'
                    '💲Находим самые свежие и новые скидки для продуктов!', reply_markup=kb.main)
        return

    referrer_id = None
    if command.args and command.args.isdigit():
        possible_referrer = int(command.args)
        if possible_referrer != user_id:
            ref_check = await session.execute(select(User).where(User.id == possible_referrer))
            if ref_check.scalar_one_or_none():
                referrer_id = possible_referrer

    new_user = User(
        id=user_id,
        username=username,
        refferrer_id=referrer_id,
    )
    session.add(new_user)
    await session.commit()
    if referrer_id:
        await msg.answer('🛒 Добро пожаловать в KaspiFinder - парсер магазина Kaspi\n'
                    '💲Находим самые свежие и новые скидки для продуктов!\n'
                    'Вы успешно прошли реферальную программу!', reply_markup=kb.main)

        try:
            await msg.bot.send_message(
                chat_id=referrer_id,
            text=f'По вашей ссылке зарегистрирован новый пользователь: @{username}',
            )
        except Exception as e:
            print(e)
            pass
    else:
        await msg.answer('🛒 Добро пожаловать в KaspiFinder - парсер магазина Kaspi\n'
                    '💲Находим самые свежие и новые скидки для продуктов!', reply_markup=kb.main)



@router.message(F.text == 'Поиск скидок')
async def search_discounts(msg: Message):
    inline_kb = kb.get_categories(CATEGORIES_MAP)
    await msg.answer(
        '👇 *Выберите категорию товара для поиска скидок:*',
        parse_mode = "Markdown",
        reply_markup=inline_kb,
    )

@router.callback_query(F.data.startswith('cat_'))
async def proccess_category(callback: CallbackQuery):
    if callback.data is None or callback.message is None:
        return
    await callback.answer()

    category_index = int(callback.data.split('_')[1])
    target_url = CATEGORIES_TO_MONITOR[category_index]

    category_name = CATEGORIES_MAP[target_url]

    status_msg = await callback.message.answer(
        f"Идет поиск выгодных товаров в категории *{category_name}* \n"
        "Это займет определенное время...",
        parse_mode="Markdown",
    )

    report = await kaspi_parser(target_url)

    if report == 'Не удалось прогрузить сайт и получить данные':
            await status_msg.edit_text(
                f"❌ *Ошибка:* {report}",
                parse_mode="Markdown",
            )
    elif report:
        MAX_LENGTH = 4000
        if len(report) <= MAX_LENGTH:
            await status_msg.edit_text(
            f"✅ *Результаты поиска:* \n"
            f"{report}",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        else:
            lines = report.split('\n')
            chunks = []
            current_chunk = f"✅ *Результаты поиска для категории {category_name} (Часть 1):*\n\n"

            for line in lines:
                if len(current_chunk) + len(line) + 1 > MAX_LENGTH:
                    chunks.append(current_chunk)
                    current_chunk = f"📦 *(Продолжение отчета):*\n\n" + line + '\n'
                else:
                    current_chunk += line + '\n'
            if current_chunk:
                chunks.append(current_chunk)
            await status_msg.edit_text(chunks[0], parse_mode="Markdown", disable_web_page_preview=True)
            for i, chunk in enumerate(chunks[1:], start=2):
                updated_chunk = chunk.replace("*(Продолжение отчета):*", f"📦 *(Продолжение отчета, часть {i}):*")
                await callback.message.answer(updated_chunk, parse_mode="Markdown", disable_web_page_preview=True)
                await asyncio.sleep(0.3)
    else:
        await status_msg.edit_text(
            "❌ *Не удалось найти товары с выгодой от 10%*",
            parse_mode="Markdown",
        )

@router.message(F.text == 'Реферальная программа')
async def referral_link(message: Message, session: AsyncSession):
    if not message.from_user or not message.bot:
        return

    user_id = message.from_user.id

    bot_info = await message.bot.get_me()
    bot_username = bot_info.username

    ref_link = f"https://t.me/{bot_username}?start={user_id}"

    query = select(func.count()).where(User.refferrer_id == user_id)
    db_result = await session.execute(query)
    referral_count = db_result.scalar() or 0

    text = (
        f"📝 *Реферальная программа KaspiFinder:*\n\n"
        f"🔗 *Ссылка для приглашения:* {ref_link}\n"
        f"📊 *Количество приглашенных:* {referral_count}\n"
    )

    await message.answer(text, parse_mode="Markdown")
