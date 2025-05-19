import logging
from iqoptionapi.stable_api import IQ_Option


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
        instrument_type=str,
        instrument_id=str,
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
