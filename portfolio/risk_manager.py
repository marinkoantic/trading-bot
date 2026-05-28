class RiskManager:

    def __init__(self):

        self.max_open_positions = 3

    def can_open_position(self, open_positions):

        return len(open_positions) < self.max_open_positions