import asyncio
from telethon import TelegramClient, events
from iqoption_trade import IQOptionTrader  # Assuming iqoption_trade.py is in the same folder
from signal_parser import parse_signal, validate_signal_data

# Telegram API credentials
API_ID = 21985712
API_HASH = "679a48874074f8d8d059b81d69e3bcf7"
PHONE_NUMBER = "+254729646982"

# IQ Option login credentials (consider using env vars or a config file)
IQ_EMAIL = "george.wanga@gmail.com"
IQ_PASSWORD = "27959256"

# Create Telegram client
client = TelegramClient("session_name", API_ID, API_HASH)


@client.on(events.NewMessage(chats=None))  # Listens to all new messages
async def handle_new_message(event):
    try:
        message_text = event.raw_text or "No message content"
        chat = await event.get_chat()
        chat_name = chat.title if chat and chat.title else "Unknown Channel"

        print(f"Channel: {chat_name}\nMessage: {message_text}\n")
        message_text = f'"""{message_text}"""'
        msg_signals = parse_signal(message_text)        

        # === Example trade trigger (you can customize based on message content) ===
        if validate_signal_data(msg_signals):  # Very basic example
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
    await client.start(PHONE_NUMBER)
    print("Listening for new messages...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
