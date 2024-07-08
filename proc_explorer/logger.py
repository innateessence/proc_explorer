class Logger:
    """
    A simple logger class that logs messages and prints them later

    This exists because during the UI loop, sys.stdout appears to be overridden
    effectively blocking any print statements from being printed to the console while the UI's event loop is running
    """

    def __init__(self):
        self.msgs = []

    def log(self, s):
        """logs a message to be printed later"""
        s = str(s)
        self.msgs.append(s)

    def print(self):
        """prints all the logged messages"""
        for msg in self.msgs:
            print(msg)
        self.msgs = []


logger = Logger()
