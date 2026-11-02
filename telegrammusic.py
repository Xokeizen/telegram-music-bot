import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, FSInputFile
from yt_dlp import YoutubeDL

from config import TOKEN


if not TOKEN:
    raise RuntimeError("Задайте токен бота в переменной окружения BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)


def search_tracks(query: str):
    """Return up to five YouTube search results without downloading them."""
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}
    with YoutubeDL(opts) as ydl:
        if query.startswith(("https://", "http://")):
            info = ydl.extract_info(query, download=False)
            entries = info.get("entries") or [info]
        else:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            entries = info.get("entries") or []
    return [entry for entry in entries if entry and entry.get("id")][:5]


def download_track(video_id: str):
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(DOWNLOAD_DIR / "%(id)s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    url = f"https://www.youtube.com/watch?v={video_id}"
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = DOWNLOAD_DIR / f"{info['id']}.mp3"
        if not path.is_file():
            raise FileNotFoundError("Не удалось подготовить аудиофайл")
        return path, info.get("title", "Аудио")


@dp.message(F.text == "/start")
async def start(message: Message):
    await message.answer(
        "Напиши название песни — я покажу несколько вариантов. "
        "Нажми на нужный, и я отправлю аудио."
    )


@dp.message(F.text)
async def find_music(message: Message):
    query = (message.text or "").strip()
    if not query:
        return
    status = await message.answer("Ищу варианты…")
    try:
        loop = asyncio.get_running_loop()
        tracks = await loop.run_in_executor(None, search_tracks, query)
        if not tracks:
            await status.edit_text("Ничего не нашёл. Попробуй другое название.")
            return

        buttons = []
        for track in tracks:
            title = track.get("title") or "Без названия"
            duration = track.get("duration")
            label = f"{title} ({duration // 60}:{duration % 60:02d})" if isinstance(duration, (int, float)) else title
            buttons.append([InlineKeyboardButton(text=label[:64], callback_data=f"track:{track['id']}")])
        await status.edit_text("Выбери нужный вариант:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception:
        logging.exception("Ошибка поиска музыки")
        await status.edit_text("Не получилось выполнить поиск. Попробуй ещё раз.")


@dp.callback_query(F.data.startswith("track:"))
async def send_track(callback: CallbackQuery):
    await callback.answer()
    video_id = callback.data.split(":", 1)[1]
    status = await callback.message.answer("Готовлю аудиофайл…")
    file_path = None
    try:
        loop = asyncio.get_running_loop()
        file_path, title = await loop.run_in_executor(None, download_track, video_id)
        await callback.message.answer_audio(audio=FSInputFile(file_path), title=title[:64])
        await status.delete()
    except Exception:
        logging.exception("Ошибка загрузки аудио")
        await status.edit_text("Не получилось отправить аудио. Возможно, источник временно недоступен.")
    finally:
        if file_path and file_path.exists():
            file_path.unlink()


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
