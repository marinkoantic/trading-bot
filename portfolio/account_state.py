class AccountState:

    def __init__(self):

        # ============================================
        # ACCOUNT
        # ============================================

        self.start_balance = 1000.0

        self.balance = 1000.0

        # ============================================
        # PNL
        # ============================================

        self.realized_pnl = 0.0

        self.unrealized_pnl = 0.0

        # ============================================
        # FEES
        # ============================================

        self.total_fees = 0.0

        # ============================================
        # FUTURES / MARGIN
        # ============================================

        self.used_margin = 0.0

        self.leverage = 10

    # =====================================================
    # REALIZED PNL
    # =====================================================

    def apply_realized_pnl(
        self,
        pnl
    ):

        self.realized_pnl += pnl

        self.balance += pnl

    # =====================================================
    # FEES
    # =====================================================

    def apply_fee(
        self,
        fee
    ):

        self.total_fees += fee

        self.balance -= fee

    # =====================================================
    # MARGIN
    # =====================================================

    def allocate_margin(
        self,
        position_value
    ):

        required_margin = (
            position_value
            / self.leverage
        )

        self.used_margin += (
            required_margin
        )

    def release_margin(
        self,
        position_value
    ):

        released_margin = (
            position_value
            / self.leverage
        )

        self.used_margin -= (
            released_margin
        )

        if self.used_margin < 0:

            self.used_margin = 0

    # =====================================================
    # EQUITY
    # =====================================================

    def get_equity(self):

        return (
            self.balance
            + self.unrealized_pnl
        )

    # =====================================================
    # AVAILABLE BALANCE
    # =====================================================

    def get_available_balance(self):

        return (
            self.get_equity()
            - self.used_margin
        )


account_state = AccountState()