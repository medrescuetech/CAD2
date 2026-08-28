class SoftAssert:
    def __init__(self):
        self.errors = []

    def check(self, condition, message):
        if not condition:
            self.errors.append(message)

    def check_no_exception(self, func, message):
        try:
            func()
        except Exception as e:
            self.errors.append(f"{message}: {e}")

    def assert_all(self):
        if self.errors:
            raise AssertionError("; ".join(self.errors))
