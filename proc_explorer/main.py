from textual.binding import Binding
from textual.widgets import Header, Footer
from textual.containers import Container
from textual import events
from textual.app import App, ComposeResult

from proc_explorer.logger import logger
from proc_explorer.util import get_terminal_size


from proc_explorer.widgets.process_list import ProcessesListWidget
from proc_explorer.widgets.open_files import OpenFilesListWidget


class ProcExplorerApp(App):
    TITLE = "Process Explorer"
    CSS_PATH = "proc_explorer.tcss"
    CLOSE_TIMEOUT = 3.0

    BINDINGS = [
        Binding(key="t", action="toggle_widget", description="toggle widget focus"),
        Binding(key="q,ctrl+c", action="quit", description="Quit the app"),
        Binding(key="R", action="_restart()", description="Restart the app"),
    ]

    def __init__(self, *args, **kwargs) -> None:
        default_kwargs = {
            "watch_css": True,
        }
        kwargs = {**default_kwargs, **kwargs}  # merge default kwargs, prioritize kwargs
        super().__init__(*args, **kwargs)
        logger.log("App initialized!")

    @property
    def _is_running(self) -> bool:
        return self._running

    @property
    def should_render_in_landscape_mode(self) -> bool:
        lines, columns = get_terminal_size()
        logger.log(f"terminal lines: {lines},  columns: {columns}")
        return (columns // 3) > lines

    def _set_portrait_mode(self) -> None:
        logger.log("Switching to portrait mode!")
        self._container.styles.layout = "vertical"
        self._processes_widget.styles.width = "100%"
        self._processes_widget.styles.height = "50%"
        self._files_widget.styles.width = "100%"
        self._files_widget.styles.height = "50%"

    def _set_landscape_mode(self) -> None:
        logger.log("Switching to landscape mode!")
        self._container.styles.layout = "horizontal"
        self._processes_widget.styles.width = "50%"
        self._processes_widget.styles.height = "100%"
        self._files_widget.styles.width = "50%"
        self._files_widget.styles.height = "100%"

    def on_key(self, event: events.Key) -> None:
        logger.log(event)

    def on_mouse_move(self, event: events.MouseMove) -> None:
        logger.log(event)

    async def on_resize(self, event: events.Resize) -> None:
        logger.log(event)
        if self.should_render_in_landscape_mode:
            self._set_landscape_mode()
            await self._processes_widget._refresh_columns()
        else:
            self._set_portrait_mode()

    def on_mount(self) -> None:
        if self.should_render_in_landscape_mode:
            self._set_landscape_mode()
        else:
            self._set_portrait_mode()

    def compose(self) -> ComposeResult:
        self._header = Header(classes="header")
        self._processes_widget = ProcessesListWidget(classes="box")
        self._files_widget = OpenFilesListWidget(classes="box")
        self._container = Container(
            self._processes_widget,
            self._files_widget,
            id="main",
        )
        self._footer = Footer(classes="footer")

        yield self._header
        yield self._container
        yield self._footer
