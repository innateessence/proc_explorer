from textual.binding import Binding
from textual.widgets import Header, Footer, DataTable
from textual.widget import Widget
from textual.containers import Container
from textual import events
from textual.app import App, ComposeResult
from textual.worker import Worker

from proc_explorer.logger import logger
from proc_explorer.util import get_terminal_size

import psutil
import time

import asyncio


class ProcessesListWidget(DataTable):
    BINDINGS = [
        Binding("k,up", "cursor_up", "Up", show=True),
        Binding("j,down", "cursor_down", "Down", show=True),
    ]

    def __init__(self, *args, **kwargs):
        default_kwargs = {
            "show_header": True,
            "cursor_type": "row",
        }
        """default kwargs for the widget. These will be merged **kwargs. **kwargs overrides default_kwargs if there is a conflict."""
        kwargs = {**default_kwargs, **kwargs}
        super().__init__(*args, **kwargs)
        self.__last_timestamp = time.time() - 60
        """timestamp of the last time the widget was refreshed"""
        self.__RERENDER_DELAY = 5.0
        """seconds to wait until re-rendering widget with UI refresh loop"""
        self.__POLLING_INTERVAL = 0.50
        """seconds to wait between all polling. Primarily used by UI refresh loop"""
        self.__lock = asyncio.Lock()
        """async friendly lock to prevent deadlocks and concurrency issues"""
        self.__last_terminal_size = get_terminal_size()
        """Terminal screen size"""
        self.loading = True
        """Flag to indicate if the widget is loading. Widget renders a loader when this is True"""

    # async def on_resize(self, event: events.Resize) -> None:
    #     """Resize event handler for the widget"""
    #     if self.loading or self.__lock.locked():
    #         return
    #     if self.has_size_changed:
    #         # await self._refresh()
    #         self.__last_terminal_size = get_terminal_size()

    @property
    def proc(self) -> psutil.Process | None:
        """Returns the process object for the currently highlighted row

        This will return None if there is no highlighted row for some reason.
        IE: while the widget is being mounted and the rows are being populated
        """
        row_values = self.row_values
        if not row_values:
            return None
        pid = row_values[0]
        return psutil.Process(pid=pid)

    @property
    def row_values(self) -> tuple[int, str, str] | None:
        """Returns the values of the currently highlighted row

        This will return None if there is no highlighted row for some reason.
        IE: while the widget is being mounted and the rows are being populated
        """
        if not self.rows:
            return None
        pid, name, status = self.get_row_at(self.cursor_row)
        logger.log(f"pid: {pid}, name: {name}, status: {status}")
        if pid is None or name is None or status is None:
            return None
        pid = int(pid)
        return pid, name, status

    @property
    def proc_pid(self) -> int | None:
        """Returns the PID of the currently highlighted row

        This will return None if there is no highlighted row for some reason.
        IE: while the widget is being mounted and the rows are being populated
        """
        row_values = self.row_values
        if not row_values:
            return None
        pid = row_values[0]
        return pid

    @property
    def proc_name(self) -> str | None:
        """Returns the name of the currently highlighted row

        This will return None if there is no highlighted row for some reason.
        IE: while the widget is being mounted and the rows are being populated"""
        row_values = self.row_values
        if not row_values:
            return None
        name = row_values[1]
        return name

    @property
    def proc_status(self) -> str | None:
        """Returns the status of the currently highlighted row

        This will return None if there is no highlighted row for some reason.
        IE: while the widget is being mounted and the rows are being populated
        """
        row_values = self.row_values
        if not row_values:
            return None
        status = row_values[2]
        return status

    @property
    def has_size_changed(self) -> bool:
        """Check if the terminal size has changed"""
        lines, columns = get_terminal_size()
        return not self.__last_terminal_size == (lines, columns)

    def on_mount(self) -> None:
        """
        Mount event handler for the widget

        Any code that needs to run when the widget is mounted should be
        placed here

        the widget is mounted when it is added DOM of the app
        """
        self.run_worker(self._refresh_loop(), exclusive=True)

    async def _refresh(self, remember_cursor_position=True) -> None:
        """Manually refresh the widget aka re-render the widget"""
        self.loading = True
        self.clear()
        old_pid = self.proc_pid
        await self._refresh_columns()
        await self._refresh_rows()
        if remember_cursor_position and old_pid is not None:
            self._move_cursor_to_closet_pid(old_pid)
        else:
            logger.log("Not moving cursor to prev position")
            logger.log(f"old_pid: {old_pid}")
        self.loading = False

    # @property
    # def __should_refresh_columns(self) -> bool:
    #     """Check if the columns should be refreshed"""
    #     _, last_columns = self.__last_terminal_size
    #     _, columns = get_terminal_size()
    #     if not self.columns:
    #         return True
    #     return not last_columns == columns

    async def _refresh_columns(self) -> None:
        """Refresh the columns of the widget"""
        # async with self.__lock:
        if not self.columns or self.has_size_changed:
            _, columns = get_terminal_size()
            self.columns.clear()
            self.add_column("PID", width=8)
            self.add_column("Name", width=columns - 28)
            self.add_column("Status", width=10)

    async def _refresh_rows(self) -> None:
        """Refresh the rows of the widget"""
        async with self.__lock:
            logger.log("Updating processes...")
            self.rows.clear()
            for proc in psutil.process_iter():
                try:
                    pid = proc.pid
                    name = proc.name()
                    status = proc.status()
                    self.add_row(str(pid), name, status)
                except psutil.NoSuchProcess:
                    pass
            self.__last_timestamp = time.time()

    async def _refresh_loop(self) -> None:
        """main event loop for refreshing the  widgets UI in the background"""
        while self.app._running:
            if time.time() - self.__last_timestamp < self.__RERENDER_DELAY:
                await asyncio.sleep(self.__POLLING_INTERVAL)
                continue

            if self.__lock.locked():
                await asyncio.sleep(self.__POLLING_INTERVAL)
                continue

            await self._refresh()

    def __distance_from_pid(self, pid) -> int:
        """
        gives us an idea of how far away we are from a specific PID

        used exclusively for locating the PID that most closely resembles the last PID we were focused on
        """
        distance = self.proc_pid - pid
        if distance < 0:
            distance *= -1
        return distance

    def _move_cursor_to_closet_pid(self, pid: int) -> None:
        """
        Find the PID closest to the PID we were last looking at, and focus that PID
        """
        logger.log(f"Moving cursor to PID: {pid}")
        logger.log(f"Current PID: {self.proc_pid}")
        while self.proc_pid != pid:
            logger.log(f"move_cursor iteration")
            distance_from_pid = self.__distance_from_pid(pid)
            logger.log(f"distance: {distance_from_pid}")

            if self.proc_pid and self.proc_pid > pid:
                cords = self.cursor_coordinate.up()
                logger.log("moving up")
            else:
                cords = self.cursor_coordinate.down()
                logger.log("moving down")

            logger.log(f"cords: {cords}")
            self.move_cursor(row=cords.row, column=cords.column)
            logger.log(f"moved cursor to: {self.cursor_coordinate}")

            new_distance_from_pid = self.__distance_from_pid(pid)
            logger.log(f"new distance: {new_distance_from_pid}")

            if distance_from_pid <= new_distance_from_pid:
                logger.log("did not get closer. breaking out of loop")
                break


class OpenFilesListWidget(Widget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._target_pid = -1
        self._files = []


class ProcExplorerApp(App):
    TITLE = "Process Explorer"
    CSS_PATH = "proc_explorer.tcss"
    CLOSE_TIMEOUT = 3.0

    BINDINGS = [
        Binding(key="t", action="toggle_widget", description="toggle widget focus"),
        Binding(key="q,ctrl+c", action="quit", description="Quit the app"),
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
    def should_render_in_portrait_mode(self) -> bool:
        lines, columns = get_terminal_size()
        logger.log(f"terminal lines: {lines},  columns: {columns}")
        return (columns // 4) > lines

    def _set_portrait_mode(self) -> None:
        logger.log("Switching to portrait mode!")
        self._container.styles.layout = "horizontal"
        self._processes_widget.styles.width = "50%"
        self._processes_widget.styles.height = "100%"
        self._files_widget.styles.width = "50%"
        self._files_widget.styles.height = "100%"

    def _set_landscape_mode(self) -> None:
        logger.log("Switching to landscape mode!")
        self._container.styles.layout = "vertical"
        self._processes_widget.styles.width = "100%"
        self._processes_widget.styles.height = "50%"
        self._files_widget.styles.width = "100%"
        self._files_widget.styles.height = "50%"

    def on_key(self, event: events.Key) -> None:
        logger.log(event)

    def on_mouse_move(self, event: events.MouseMove) -> None:
        logger.log(event)

    async def on_resize(self, event: events.Resize) -> None:
        logger.log(event)
        if self.should_render_in_portrait_mode:
            self._set_portrait_mode()
            # await self._processes_widget.
            await self._processes_widget._refresh_columns()
        else:
            self._set_landscape_mode()

    def on_mount(self) -> None:
        if self.should_render_in_portrait_mode:
            self._set_portrait_mode()
        else:
            self._set_landscape_mode()

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
