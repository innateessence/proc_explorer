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
