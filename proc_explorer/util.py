import psutil


class SharedProcess:
    """
    Singleton class to share the process object between the two widgets
    """

    _instance = None

    def __init__(self):
        self.pid = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SharedProcess, cls).__new__(cls)
        return cls._instance

    @property
    def proc(self) -> psutil.Process | None:
        if isinstance(self.pid, str):
            self.pid = int(self.pid)
        if isinstance(self.pid, int):
            return psutil.Process(pid=self.pid)


shared_process = SharedProcess()


class UndefinedType:
    """
    This is designed to mimic the `None` type as closely as possible
    but with one key difference
    we want `Undefined is None` to return False

    This is useful when we want to differentiate between a value that is `None` and a value that was never set
    """

    _instance = None
    _memory_address = 0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(UndefinedType, cls).__new__(cls)
            cls._memory_address = id(cls._instance)
        return cls._instance

    def __str__(self):
        return "Undefined"

    def __repr__(self):
        return "Undefined"

    def __bool__(self):
        return False

    def __hash__(self):
        return hash(self._memory_address)

    def __eq__(self, other):
        return (
            hasattr(other, "_memory_address")
            and self._memory_address == other._memory_address
        )


Undefined = UndefinedType()


def get_terminal_size() -> tuple[int, int]:
    try:
        from shutil import get_terminal_size as _get_terminal_size

        columns, lines = _get_terminal_size()
    except ImportError:
        try:
            from subprocess import check_output

            lines, columns = tuple(map(int, check_output(["stty", "size"]).split()))
        except Exception:
            print("Error getting screen size...")
            return 80, 24

    return lines, columns
