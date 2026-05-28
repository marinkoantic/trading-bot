class ExposureTracker:

    def __init__(self):

        self.total_exposure = 0

    def update_exposure(self, value):

        self.total_exposure += value

    def get_exposure(self):

        return self.total_exposure