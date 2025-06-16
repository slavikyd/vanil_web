from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import WEBAPP_URL

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(f"Your Telegram ID is: {message.from_user.id}")

@router.message(Command("app"))
async def cmd_app(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Open Web App",
        web_app=types.WebAppInfo(url=WEBAPP_URL)
    )
    await message.answer("Click below to open the web app:", reply_markup=builder.as_markup())
