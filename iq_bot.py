import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pytz
from iqoptionapi.stable_api import IQ_Option
from telethon import TelegramClient, events

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Telegram API credentials
API_ID = 21985712
API_HASH = "679a48874074f8d8d059b81d69e3bcf7"
PHONE_NUMBER = "+254729646982"

# IQ Option login credentials (consider using env vars or a config file)
IQ_EMAIL = "george.wanga@gmail.com"
IQ_PASSWORD = "27959256"

# Trading hours configuration (Kenyan time - EAT)
KENYAN_TZ = pytz.timezone('Africa/Nairobi')
TRADING_START_HOUR = 8  # 8 AM
TRADING_END_HOUR = 20   # 8 PM

def parse_signal(message: str) -> Dict[str, Optional[object]]:
    """
    Extract instrument_id, instrument_type, side, stop_price (entry),
    stop_lose_value (SL), and take-profit values from a signal message.
    
    Args:
        message: The signal message to parse
        
    Returns:
        Dict containing parsed signal data
    """
    try:
        txt = message.upper()

        # Extract side (BUY/SELL)
        side_match = re.search(r'\b(BUY|SELL)\b', txt)
        if not side_match:
            raise ValueError("Side not found")
        side = side_match.group(1).lower()

        # Extract instrument
        instr_re = re.compile(
            r'\b([A-Z]{3}/[A-Z]{3}|[A-Z]{6}|XAUUSD|XAU|GOLD)\b'
        )
        instr_match = instr_re.search(txt)
        if not instr_match:
            raise ValueError("Instrument not found")
        raw = instr_match.group(1)
        instrument_mapping = {'GOLD': 'XAUUSD', 'XAU': 'XAUUSD'}
        instrument_id = instrument_mapping.get(raw, raw)

        # Determine instrument type
        if instrument_id == "XAUUSD":
            instrument_type = "cfd"
        else:
            instrument_type = "forex"

        # Extract entry price (stop_price)
        rng = re.search(r'(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)', txt)
        if rng:
            stop_price = (float(rng.group(1)) + float(rng.group(2))) / 2
        else:
            stop_price = None
            for line in txt.splitlines():
                skip_tags = ('TP', 'TAKE PROFIT', 'SL', 'STOP LOSS')
                if any(tag in line for tag in skip_tags):
                    continue
                nums = re.findall(r'\d+(?:\.\d+)?', line)
                if nums:
                    stop_price = float(nums[0])
                    break
            if stop_price is None:
                num = re.search(r'\d+(?:\.\d+)?', txt)
                stop_price = float(num.group()) if num else None

        # Extract stop-loss
        sl = re.search(r'\b(?:SL|STOP LOSS)\b[^0-9]*([\d.]+)', txt)
        stop_loss = float(sl.group(1)) if sl else None

        # Extract take-profit values
        tps = re.findall(r'\bTP\s*\d*[^0-9]*([\d.]+)', txt)
        if not tps:
            tps = re.findall(r'\bTAKE PROFIT\s*\d*[^0-9]*([\d.]+)', txt)
        take_profit_values: List[float] = [float(v) for v in tps]

        return {
            'instrument_id': instrument_id,
            'instrument_type': instrument_type,
            'side': side,
            'stop_price': stop_price,
            'stop_lose_value': stop_loss,
            'take_profit_values': take_profit_values,
        }

    except Exception as e:
        logging.error(f"parse_signal error: {e}")
        return {
            'instrument_id': None,
            'instrument_type': None,
            'side': None,
            'stop_price': None,
            'stop_lose_value': None,
            'take_profit_values': [],
        }

def is_trading_hours() -> bool:
    """
    Check if current time is within trading hours (Mon-Fri, 8 AM-8 PM EAT).
    
    Returns:
        True if within trading hours, False otherwise
    """
    now = datetime.now(KENYAN_TZ)
    
    # Check if it's a weekday (Monday=0, Sunday=6)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    
    # Check if within trading hours (8 AM to 8 PM)
    if not (TRADING_START_HOUR <= now.hour < TRADING_END_HOUR):
        return False
    
    return True


def get_time_until_next_trading_session() -> int:
    """
    Calculate seconds until next trading session starts.
    
    Returns:
        Number of seconds to wait
    """
    now = datetime.now(KENYAN_TZ)
    
    # If it's weekend, wait until Monday 8 AM
    if now.weekday() >= 5:  # Weekend
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0:  # It's Sunday
            days_until_monday = 1
        
        next_monday = now + timedelta(days=days_until_monday)
        next_trading = next_monday.replace(
            hour=TRADING_START_HOUR, minute=0, second=0, microsecond=0
        )
        return int((next_trading - now).total_seconds())
    
    # If it's before trading hours today
    if now.hour < TRADING_START_HOUR:
        next_trading = now.replace(
            hour=TRADING_START_HOUR, minute=0, second=0, microsecond=0
        )
        return int((next_trading - now).total_seconds())
    
    # If it's after trading hours today, wait until next trading day
    if now.weekday() == 4:  # Friday - wait until Monday
        next_trading = now + timedelta(days=3)
    else:  # Monday-Thursday - wait until tomorrow
        next_trading = now + timedelta(days=1)
    
    next_trading = next_trading.replace(
        hour=TRADING_START_HOUR, minute=0, second=0, microsecond=0
    )
    return int((next_trading - now).total_seconds())


def validate_signal_data(signal: dict) -> bool:
    """
    Validates that all required signal fields are present and not empty.
    
    Args:
        signal: Dictionary containing signal data
        
    Returns:
        True if all required fields are valid, False otherwise
    """
    required_keys = [
        'instrument_id', 'instrument_type', 'side',
        'stop_price', 'stop_lose_value', 'take_profit_values'
    ]
    
    for key in required_keys:
        value = signal.get(key)
        if value is None:
            return False
        if isinstance(value, (str, list)) and not value:
            return False
    return True

class IQOptionTrader:
    """Handles IQ Option trading operations."""

    def __init__(self, email: str, password: str):
        """Initialize the trader with credentials."""
        self.email = email
        self.password = password
        self.api = IQ_Option(email, password)

    def connect(self) -> bool:
        """Connect to IQ Option API."""
        check, reason = self.api.connect()
        if check:
            logging.info("Connected to IQ Option.")
        else:
            logging.error(f"Connection failed: {reason}")
        return check

    def divide_geometric(self, x: float, n: int) -> List[float]:
        """Divide amount geometrically for multiple take-profit levels."""
        if n <= 0:
            return []

        a = x / (2 * (1 - (1 / (2 ** n))))
        parts = [a / (2 ** i) for i in range(n)]
        return parts

    def place_cfd_order(
        self,
        stop_price: float,
        stop_lose_value: float,
        take_profit_values: List[float],
        side: str,
        instrument_type: str,
        instrument_id: str,
        order_type: str = "stop",
        limit_price: Optional[float] = None,
        stop_lose_kind: str = "price",
        take_profit_kind: str = "price",
        use_trail_stop: bool = False,
        auto_margin_call: bool = True,
        use_token_for_commission: bool = False
    ) -> tuple[bool, List[str]]:
        """Place CFD orders with multiple take-profit levels."""
        order_ids = []
        account_balance = self.api.get_balance()
        trade_amount = account_balance * 0.02  # 2% of account balance

        leverages = self.api.get_available_leverages(
            instrument_type, instrument_id
        )
        leverage = int(leverages[1]["leverages"][0]["regulated_default"])

        n = len(take_profit_values)
        trade_amounts = self.divide_geometric(trade_amount, n)

        for take_profit_value, amount in zip(take_profit_values, trade_amounts):
            logging.info(
                f"Placing order - TP: {take_profit_value}, Amount: {amount}"
            )
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

# Initialize Telegram client
client = TelegramClient("session_name", API_ID, API_HASH)


@client.on(events.NewMessage(chats=None))
async def handle_new_message(event) -> None:
    """Handle incoming Telegram messages and process trading signals."""
    try:
        # Check if we're in trading hours
        if not is_trading_hours():
            now = datetime.now(KENYAN_TZ)
            logging.info(
                f"Outside trading hours (Mon-Fri 8AM-8PM EAT). "
                f"Current time: {now.strftime('%A %H:%M %Z')}"
            )
            return

        message_text = event.raw_text or "No message content"
        chat = await event.get_chat()
        chat_name = chat.title if chat and chat.title else "Unknown Channel"

        logging.info(f"Channel: {chat_name}")
        logging.info(f"Message: {message_text}")

        # Parse the signal from the message
        message_text = f'"""{message_text}"""'
        msg_signals = parse_signal(message_text)

        # Process valid signals
        if validate_signal_data(msg_signals):
            logging.info("Valid signal detected, attempting to place trade")
            trader = IQOptionTrader(IQ_EMAIL, IQ_PASSWORD)

            if trader.connect():
                success, order_ids = trader.place_cfd_order(
                    instrument_type=msg_signals["instrument_type"],
                    instrument_id=msg_signals["instrument_id"],
                    stop_price=msg_signals["stop_price"],
                    stop_lose_value=msg_signals["stop_lose_value"],
                    take_profit_values=msg_signals["take_profit_values"],
                    side=msg_signals["side"],
                )
                
                if success:
                    logging.info(f"Successfully placed {len(order_ids)} orders")
                else:
                    logging.error("Failed to place orders")
            else:
                logging.error("Failed to connect to IQ Option")
        else:
            logging.warning("Invalid or incomplete signal data")

    except Exception as e:
        logging.error(f"Error processing message: {e}")


async def main() -> None:
    """Main function to start the Telegram bot with trading hours management."""
    try:
        await client.start(PHONE_NUMBER)
        logging.info("Bot started successfully.")
        
        while True:
            if is_trading_hours():
                logging.info("Trading hours active. Listening for messages...")
                # Listen for messages during trading hours
                try:
                    await client.run_until_disconnected()
                except Exception as e:
                    logging.error(f"Error during trading session: {e}")
                    break
            else:
                # Calculate sleep time until next trading session
                sleep_seconds = get_time_until_next_trading_session()
                sleep_hours = sleep_seconds / 3600
                
                now = datetime.now(KENYAN_TZ)
                logging.info(
                    f"Outside trading hours. Current time: {now.strftime('%A %H:%M %Z')}"
                )
                logging.info(f"Sleeping for {sleep_hours:.1f} hours until next session")
                
                await asyncio.sleep(sleep_seconds)
                
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
