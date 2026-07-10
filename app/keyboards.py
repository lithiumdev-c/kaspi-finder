from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types.inline_keyboard_button import InlineKeyboardButton
from aiogram.types.inline_keyboard_markup import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

main = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='Поиск скидок')],
        [KeyboardButton(text='Реферальная программа')],
        [KeyboardButton(text='Поддержать проект!')],
    ], resize_keyboard=True
)

def get_categories(categories_map: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for index, (url, name) in enumerate(categories_map.items()):
        builder.button(
            text=name,
            callback_data=f'cat_{index}'
        )

    builder.adjust(2)
    return builder.as_markup()
