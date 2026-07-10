import asyncio
import statistics
import re
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def auto_discount_hunter(category_url):
    async with Stealth().use_async(async_playwright()) as p:
        # headless=False, чтобы ты видел, если выскочит капча
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("Робот зашел на страницу категории. Ожидание загрузки товаров...")

        try:
            await page.goto(category_url, wait_until="domcontentloaded")

            # Ждем верхнеуровневый контейнер (плитку или сами карточки), ставим таймаут поменьше
            await page.locator('.item-card, [data-product-id], .recom-card').first.wait_for(timeout=5000)

        except Exception:
            print("\n❌ Ошибка: Карточки не найдены на странице за 5 секунд.")
            await page.screenshot(path="kaspi_error_screen.png")
            print("Скриншот сохранен в 'kaspi_error_screen.png'.")
            await browser.close()
            return

        # Забираем все карточки, которые начинаются на item- или содержат id продукта
        raw_products = await page.locator('.item-card, [data-product-id]').all()

        parsed_items = []
        all_prices = []

        print(f"Найдено сырых блоков для анализа: {len(raw_products)}. Начинаю разбор...")

        for item in raw_products:
            try:
                # 1. Ссылка и Название (берем первую ссылку внутри карточки)
                link_elem = item.locator('a').first
                link = await link_elem.get_attribute('href')

                # Забираем ВЕСЬ текст внутри карточки ОДНИМ запросом (это исключает зависание на цене)
                full_text = await item.inner_text()
                lines = [line.strip() for line in full_text.split('\n') if line.strip()]

                if not lines:
                    continue

                # Название обычно идет первой или второй строчкой
                title = lines[0]

                # 2. Поиск цены через регулярное выражение (ищем строку, где есть цифры и значок ₸)
                price = None
                for line in lines:
                    if '₸' in line or 'тг' in line:
                        # Удаляем всё, кроме цифр
                        digits = "".join(filter(str.isdigit, line))
                        if digits:
                            price = int(digits)
                            break

                # Если регулярка выше не сработала, ищем просто самую большую цифру в карточке
                if not price:
                    all_digits = [int("".join(filter(str.isdigit, l))) for l in lines if "".join(filter(str.isdigit, l))]
                    if all_digits:
                        # Обычно цена — это самое большое число в карточке (бонусы и отзывы меньше)
                        price = max(all_digits)

                if not title or not price or price < 100:  # Отсекаем слишком мелкие суммы (мелочь/чехлы)
                    continue

                product_data = {
                    'title': title,
                    'price': price,
                    'link': link if link else ''
                }

                parsed_items.append(product_data)
                all_prices.append(price)

            except Exception:
                continue

        if not all_prices:
            print("❌ Текст карточек получен, но алгоритм не смог выделить из него цены. Каспи жестко изменил формат.")
            await browser.close()
            return

        # Шаг 2: Расчет рынка
        median_price = statistics.median(all_prices)
        print(f"\nАнализ завершен. Всего успешно распознано товаров: {len(all_prices)}")
        print(f"Средняя (медианная) цена по этой странице: {median_price:,.0f} ₸\n")
        print("="*60)
        print("🔥 НАЙДЕНЫ ВЫГОДНЫЕ ТОВАРЫ (Дешевле рынка минимум на 10%):")
        print("="*60)

        # Шаг 3: Фильтрация
        count_found = 0
        for prod in parsed_items:
            discount_from_market = ((median_price - prod['price']) / median_price) * 100

            if prod['price'] < median_price and discount_from_market >= 10:
                count_found += 1
                print(f"\nРыночная цена (Медиана): {median_price:,.0f} ₸")
                print(f"Цена этого товара: {prod['price']:,.0f} ₸")
                print(f"Выгода: {discount_from_market:.1f}%")
                print(f"Товар: {prod['title']}")
                print(f"Ссылка: https://kaspi.kz{prod['link'] if prod['link'].startswith('/') else '/' + prod['link']}")
                print("-" * 40)

        if count_found == 0:
            print("\nАномально дешевых предложений на этой странице прямо сейчас не найдено.")

        await browser.close()

# Запуск
category_link = "https://kaspi.kz/shop/c/smartphones/"
asyncio.run(auto_discount_hunter(category_link))
