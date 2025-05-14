import asyncio
from telethon import TelegramClient, events
import logging
from iqoptionapi.stable_api import IQ_Option
import re
from typing import Optional, List, Dict

# Telegram API credentials
API_ID = 21985712
API_HASH = "679a48874074f8d8d059b81d69e3bcf7"
PHONE_NUMBER = "+254729646982"

# IQ Option login credentials (consider using env vars or a config file)
IQ_EMAIL = "george.wanga@gmail.com"
IQ_PASSWORD = "27959256"

# Create Telegram client
client = TelegramClient("session_name", API_ID, API_HASH)


class IQOptionTrader:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.api = IQ_Option(email, password)

    def connect(self) -> bool:
        check, reason = self.api.connect()
        if check:
            logging.info("Connected to IQ Option.")
        else:
            logging.error(f"Connection failed: {reason}")
        return check
    
    def divide_geometric(self, x, n):
        if n <= 0:
            return []

        a = x / (2 * (1 - (1 / (2 ** n))))
        parts = [a / (2 ** i) for i in range(n)]
        return parts

    def place_cfd_order(
        self,
        stop_price: float,
        stop_lose_value: float,
        take_profit_values: list,
        side: str,
        instrument_type="cfd",
        instrument_id="XAUUSD",
        order_type="stop",
        limit_price=None,
        stop_lose_kind="price",
        take_profit_kind="price",
        use_trail_stop=False,
        auto_margin_call=True,
        use_token_for_commission=False
    ):
        order_ids = []
        account_balance = self.api.get_balance()
        trade_amount = account_balance * 0.02  # 2% of account balance
        leverages = self.api.get_available_leverages(instrument_type, instrument_id)
        leverage = int(leverages[1]["leverages"][0]["regulated_default"])
        n = len(take_profit_values)
        trade_amounts = self.divide_geometric(trade_amount, n)
            
        for take_profit_value, amount in zip(take_profit_values, trade_amounts):
            print(f"Take Profit: {take_profit_value}, Amount: {amount}")
            amount = max(amount, 1)
            success, order_id = self.api.buy_order(
                instrument_type=instrument_type,
                instrument_id=instrument_id,
                side=side,
                amount=amount,
                leverage=leverage,
                type=order_type,
                limit_price=limit_price,
                stop_price=stop_price,
                stop_lose_value=stop_lose_value,
                stop_lose_kind=stop_lose_kind,
                take_profit_value=take_profit_value,
                take_profit_kind=take_profit_kind,
                use_trail_stop=use_trail_stop,
                auto_margin_call=auto_margin_call,
                use_token_for_commission=use_token_for_commission,
            )

            if success:
                logging.info(f"Order placed successfully. Order ID: {order_id}")
                order_ids.append(order_id)
            else:
                logging.error("Failed to place order.")

        return success, order_ids


def validate_signal_data(signal: dict) -> bool:
    required_keys = ['instrument_id', 'side', 'stop_price', 'stop_lose_value', 'take_profit_values']
    for key in required_keys:
        value = signal.get(key)
        if value is None:
            return False
        if isinstance(value, (str, list)) and not value:
            return False
    return True


def parse_signal(message: str) -> Dict[str, Optional[object]]:
    try:
        message = message.upper()

        alias_map = {
            'GOLD': 'XAUUSD',
            'XAU': 'XAUUSD',
            'XAUUSD': 'XAUUSD',
        }

        # Extract instrument and side
        match = re.search(r'\b(BUY|SELL)\b.*?\b(GOLD|XAUUSD|XAU)\b', message) or \
                re.search(r'\b(GOLD|XAUUSD|XAU)\b.*?\b(BUY|SELL)\b', message)

        if match:
            if match.group(1) in ['BUY', 'SELL']:
                side = match.group(1).lower()
                instrument_raw = match.group(2)
            else:
                instrument_raw = match.group(1)
                side = match.group(2).lower()
        else:
            raise ValueError("Instrument or side not found")

        instrument_id = alias_map.get(instrument_raw.strip(), instrument_raw.strip())

        # Extract entry price
        stop_price: Optional[float] = None

        try:
            price_match = re.search(
                rf'{instrument_raw}\s+{side.upper()}\s+([\d.]+)', message
            ) or re.search(
                rf'{side.upper()}\s+{instrument_raw}\s+([\d.]+)', message
            ) or re.search(
                rf'{side.upper()}\s*@?\s*([\d.]+)', message
            )

            if price_match:
                stop_price = float(price_match.group(1))
        except ValueError:
            stop_price = None

        if stop_price is None:
            try:
                range_match = re.search(r'ENTER\s*[<]?\s*([\d.]+)\s*[-–]\s*([\d.]+)', message) or \
                              re.search(r'([\d.]+)\s*[-–]\s*([\d.]+)', message)
                if range_match:
                    low = float(range_match.group(1))
                    high = float(range_match.group(2))
                    stop_price = round((low + high) / 2, 2)
            except ValueError:
                stop_price = None

        if stop_price is None:
            raise ValueError("Entry price not found.")

        # Stop Loss
        try:
            sl_match = re.search(r'\bSL\b\s*@?\s*[:\-]?\s*([\d.]+)', message) or \
                       re.search(r'STOP\s+LOSS\s*[:\-]?\s*([\d.]+)', message)
            stop_lose_value = float(sl_match.group(1)) if sl_match else None
        except ValueError:
            stop_lose_value = None

        # Take Profits
        try:
            tp_matches = re.findall(
                r'(?:TP\s*\d*|TP\d*|TAKE\s+PROFIT\s*\d*|TP)[:\s\-]*([\d.]+)',
                message
            )
            take_profit_values: List[float] = []
            for tp in tp_matches:
                try:
                    val = float(tp)
                    if val > 10:
                        take_profit_values.append(val)
                except ValueError:
                    continue
        except Exception:
            take_profit_values = []

        return {
            'instrument_id': instrument_id,
            'side': side,
            'stop_price': stop_price,
            'stop_lose_value': stop_lose_value,
            'take_profit_values': take_profit_values
        }

    except ValueError as ve:
        print(f"ValueError: {ve}")
        return {
            'instrument_id': None,
            'side': None,
            'stop_price': None,
            'stop_lose_value': None,
            'take_profit_values': []
        }

    except Exception as e:
        print(f"Unexpected error: {e}")
        return {
            'instrument_id': None,
            'side': None,
            'stop_price': None,
            'stop_lose_value': None,
            'take_profit_values': []
        }

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
