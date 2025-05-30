import re
from typing import Optional, List, Dict

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

        # Alias mapping
        alias_map = {
            'GOLD': 'XAUUSD',
            'XAU': 'XAUUSD',
            'XAUUSD': 'XAUUSD',
        }

        # Match instrument and side
        match = re.search(r'\b([A-Z]{3,6})\b.*?\b(BUY|SELL)\b', message) or \
                re.search(r'\b(BUY|SELL)\b.*?\b([A-Z]{3,6})\b', message)
        
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
        
        # Determine instrument_type based on instrument_id
        instrument_type = "cfd" if instrument_id == "XAUUSD" else "forex"

        # Extract entry price
        stop_price: Optional[float] = None
        try:
            price_match = re.search(
                rf'{instrument_raw}\s+{side.upper()}\s+([\d.]+)', message
            ) or re.search(
                rf'{side.upper()}\s+{instrument_raw}\s+([\d.]+)', message
            ) or re.search(
                rf'{side.upper()}\s+(NOW\s+)?@?\s*([\d.]+)', message
            )

            if price_match:
                stop_price = float(price_match.group(1) if price_match.lastindex == 1 else price_match.group(2))
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

        # Take Profits (Updated Regex)
        try:
            tp_matches = re.findall(
                r'\bTP\d*\s*[:\s@=]?\s*(?:\d+\s+)?(\d+\.?\d*)', message, re.IGNORECASE
            ) or re.findall(
                r'TAKE\s+PROFIT\s*\d*\s*[:\-=]?\s*(\d+\.?\d*)', message, re.IGNORECASE
            )
        
            take_profit_values: List[float] = []
            for tp in tp_matches:
                try:
                    val = float(tp.strip())
                    if 0 < val < 100000:
                        take_profit_values.append(val)
                except ValueError:
                    continue
        except Exception:
            take_profit_values = []

        return {
            'instrument_id': instrument_id,
            'instrument_type': instrument_type,
            'side': side,
            'stop_price': stop_price,
            'stop_lose_value': stop_lose_value,
            'take_profit_values': take_profit_values
        }

    except ValueError as ve:
        print(f"ValueError: {ve}")
        return {
            'instrument_id': None,
            'instrument_type': None,
            'side': None,
            'stop_price': None,
            'stop_lose_value': None,
            'take_profit_values': []
        }

    except Exception as e:
        print(f"Unexpected error: {e}")
        return {
            'instrument_id': None,
            'instrument_type': None,
            'side': None,
            'stop_price': None,
            'stop_lose_value': None,
            'take_profit_values': []
        }