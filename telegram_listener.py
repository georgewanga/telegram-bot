import asyncio
import os
from telethon import TelegramClient, events
from iqoption_trade import IQOptionTrader
from signal_parser import parse_signal, validate_signal_data

# Telegram Bot Token
BOT_TOKEN = "7668747945:AAFDSkqfOIODmd_28GdKXOSkhQmVbcdKf6s"

# API credentials (required even for bots)
API_ID = 21985712
API_HASH = "679a48874074f8d8d059b81d69e3bcf7"

# IQ Option login credentials (move these to env vars ideally)
IQ_EMAIL = "george.wanga@gmail.com"
IQ_PASSWORD = "27959256"

# Create Telegram bot client
client = TelegramClient("bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)


@client.on(events.NewMessage)
async def handle_new_message(event):
    try:
        message_text = event.raw_text or "No message content"
        chat = await event.get_chat()
        chat_name = getattr(chat, "title", "Private Chat or Unknown")

        print(f"Channel: {chat_name}\nMessage: {message_text}\n")
        message_text = f'"""{message_text}"""'
        msg_signals = parse_signal(message_text)

        if validate_signal_data(msg_signals):
            trader = IQOptionTrader(IQ_EMAIL, IQ_PASSWORD)

            if trader.connect():
                trader.place_cfd_order(
                    instrument_type=msg_signals["instrument_type"],
                    instrument_id=msg_signals["instrument_id"],
                    stop_price=msg_signals["stop_price"],
                    stop_lose_value=msg_signals["stop_lose_value"],
                    take_profit_values=msg_signals["take_profit_values"],
                    side=msg_signals["side"],
                )
    except Exception as e:
        print(f"Error processing message: {e}")


async def main():
    print("Bot is listening for new messages...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
