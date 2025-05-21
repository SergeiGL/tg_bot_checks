import asyncio
import aiohttp
from config import telegram_alerts_chats, telegram_alerts_token


async def send_telegram_message(
    message,
    chat_id=telegram_alerts_chats,
    bot_token=telegram_alerts_token,
    max_retries=10
):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chat_ids = chat_id if isinstance(chat_id, list) else [chat_id]

    async with aiohttp.ClientSession() as session:
        for chat in chat_ids:
            payload = {
                "chat_id": chat,
                "text": message,
                "parse_mode": "HTML"
            }

            for i in range(max_retries + 1):
                try:
                    async with session.post(url, json=payload) as response:
                        if response.status == 200:
                            return
                        response.raise_for_status()
                except Exception:
                    await asyncio.sleep(1.5 ** i)
            else:
                raise Exception("send_telegram_message: Max retries reached. Message sending failed.")
