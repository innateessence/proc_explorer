from textual.widget import Widget


class OpenFilesListWidget(Widget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._target_pid = -1
        self._files = []
