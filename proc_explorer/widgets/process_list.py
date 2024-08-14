from textual.binding import Binding
from textual.widgets import DataTable
from textual import events

from proc_explorer.logger import logger
from proc_explorer.util import get_terminal_size

import psutil
import time

import asyncio

from proc_explorer.util import shared_process


class ProcessesListWidget(DataTable):
    """
    Widget to display a list of processes.

    All other widgets that will be a dependency of this widget.
    This widget is exclusively used as acting like a fancy UI to point to a process.

    All other widgets will rely on the global 'pointer' this widget assigns, and show some data regarding that process.
    """

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

    async def on_resize(self, event: events.Resize) -> None:
        """Resize event handler for the widget"""
        if self.loading or self.__lock.locked():
            return
        if self.has_size_changed:
            await self._refresh()
            self.__last_terminal_size = get_terminal_size()

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

    def on_data_table_row_highlighted(self, row: int) -> None:
        """Event handler for when a row is highlighted"""
        pid = self.proc_pid
        if pid is not None:
            shared_process.pid = pid

        logger.log(f"highlighted row: {row} | pid: {shared_process.pid})")

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

        the widget is mounted when it is added to the DOM of the app
        """
        self.run_worker(
            self._refresh_loop, group="process_list", name="process_list", thread=True
        )

    async def _refresh(self, remember_cursor_position=True, with_lock=True) -> None:
        """
        Manually refresh the widget aka re-render the widget

        This also recalculates anything the UI depends on in order to properly render
        """
        self.loading = True
        old_pid = self.proc_pid
        self.clear()
        await self._refresh_columns(with_lock=with_lock)
        await self._refresh_rows(with_lock=with_lock)
        if remember_cursor_position and old_pid is not None:
            self._move_cursor_to_closet_pid(old_pid)
        else:
            logger.log("Not moving cursor to prev position")
            logger.log(f"old_pid: {old_pid}")
        self.loading = False

    async def _refresh_columns(self, with_lock=True) -> None:
        """
        Refresh the columns of the widget

        params:
            with_lock: bool = True
                if True, the method will acquire the lock before proceeding
        """
        if with_lock:
            async with self.__lock:
                await self.__refresh_columns()
        else:
            await self.__refresh_columns()

    async def __refresh_columns(self) -> None:
        """
        function to refresh the columns of the widget

        Call this directly if you cannot await the result for some reason
        """
        if self.has_size_changed or not self.columns:
            _, columns = get_terminal_size()
            pid_width = 8
            if self.app.should_render_in_landscape_mode:  # pyright: ignore
                name_width = (columns // 2) - 28
            else:
                name_width = columns - 28
            status_width = 10
            self.columns.clear()
            self.add_column("PID", width=pid_width)
            self.add_column("Name", width=name_width)
            self.add_column("Status", width=status_width)

    async def _refresh_rows(self, with_lock=True) -> None:
        """Refresh the rows of the widget"""
        if with_lock:
            async with self.__lock:
                await self.__refresh_rows()
        else:
            await self.__refresh_rows()

    async def __refresh_rows(self) -> None:
        """
        function to refresh the rows of the widget

        call this directly if you cannot await the result for some reason
        """
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
        """main event loop for refreshing the widgets UI in the background"""
        while self.app._running:
            if self.__lock.locked():
                await asyncio.sleep(self.__POLLING_INTERVAL)
                continue

            if time.time() - self.__last_timestamp < self.__RERENDER_DELAY:
                await asyncio.sleep(self.__POLLING_INTERVAL)
                continue

            await self._refresh()
            await asyncio.sleep(0.10)

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
