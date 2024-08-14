import os
import psutil
from textual.widgets import DataTable

from proc_explorer.util import Undefined, get_terminal_size

import asyncio
from rich.text import Text

from proc_explorer.logger import logger
from proc_explorer.util import shared_process


class File:
    """
    A definition of a file object for the purposes of this widget
    """

    def __init__(self, path: str, fd: int):
        self.path = path  # file path
        self.fd = fd  # file descriptor

    @property
    def _filesize(self) -> int:
        """Returns the size of the file in bytes"""
        return os.stat(self.path).st_size

    @property
    def filesize(self) -> str:
        """Returns the size of the file in human readable format"""
        return psutil._common.bytes2human(self._filesize)


class OpenFilesListWidget(DataTable):
    def __init__(self, *args, **kwargs):
        default_kwargs = {
            "show_header": True,
            "cursor_type": "row",
        }
        """default kwargs for the widget. These will be merged **kwargs. **kwargs overrides default_kwargs if there is a conflict."""
        kwargs = {**default_kwargs, **kwargs}
        super().__init__(*args, **kwargs)

        self.__lock = asyncio.Lock()
        """async friendly lock to prevent deadlocks and concurrency issues"""

        self.__POLLING_INTERVAL = 0.50
        """seconds to wait between all polling. Primarily used by UI refresh loop"""
        self.__lock = asyncio.Lock()
        """async friendly lock to prevent deadlocks and concurrency issues"""
        self.__last_terminal_size = get_terminal_size()
        """Terminal screen size"""
        self.loading = True
        """Flag to indicate if the widget is loading. Widget renders a loader when this is True"""
        self.last_pid = Undefined  # None prevents initial render/logic

    @property
    def target_proc(self) -> psutil.Process | None:
        return shared_process.proc

    @property
    def has_pid_changed(self) -> bool:
        target_proc = self.target_proc
        if target_proc is None:
            return False
        return target_proc.pid != self.last_pid

    @property
    def open_files(self) -> list[File]:
        # TODO: rely on `lsof` instead if it exists
        # psutil is not able to retrieve as much information
        files = []
        proc = self.target_proc
        if proc is None:
            logger.log("OpenFilesListWidget target_proc is None")
            return files
        try:
            logger.log(f"proc is : {proc}")
            for popenfile in proc.open_files():
                file = File(popenfile.path, popenfile.fd)
                files.append(file)
            logger.log(f"OpenFilesListWidget grabbed the files!!!")
        except psutil.AccessDenied:
            pass
        except psutil.NoSuchProcess:
            pass
        return files

    def on_mount(self) -> None:
        """
        Mount event handler for the widget

        Any code that needs to run when the widget is mounted should be
        placed here

        the widget is mounted when it is added to the DOM of the app
        """
        self.run_worker(
            self._refresh_loop,
            group="open_files",
            name="open_files",
            thread=True,
            start=True,
        )
        logger.log("OpenFilesListWidget mounted!")

    @property
    def has_size_changed(self) -> bool:
        """Check if the terminal size has changed"""
        lines, columns = get_terminal_size()
        return not self.__last_terminal_size == (lines, columns)

    async def _refresh_loop(self) -> None:
        logger.log("OpenFilesListWidget refresh loop started!")
        while self.app._running:
            target_proc = self.target_proc
            target_pid = getattr(target_proc, "pid", None)

            logger.log("OpenFilesListWidget refresh loop running")
            if self.__lock.locked():
                logger.log("OpenFilesListWidget refresh loop is locked")
                await asyncio.sleep(self.__POLLING_INTERVAL)
                continue

            if target_proc and target_proc.pid == self.last_pid:
                logger.log("OpenFilesListWidget target_proc is the same as last_proc")
                await asyncio.sleep(self.__POLLING_INTERVAL)
                continue

            if self.has_pid_changed:
                logger.log(
                    f"OpenFilesListWidget pid has changed! last_pid: {self.last_pid}, target_proc.pid: {target_pid}"
                )
                await self._refresh()

            await asyncio.sleep(self.__POLLING_INTERVAL)

            self.last_pid = target_pid or self.last_pid

    async def _refresh(self, with_lock=True) -> None:
        logger.log("OpenFilesListWidget refreshing!")
        self.loading = True
        self.clear()
        await self._refresh_columns(with_lock=with_lock)
        await self._refresh_rows(with_lock=with_lock)
        self.loading = False
        logger.log("OpenFilesListWidget refreshed!")

    async def _refresh_rows(self, with_lock=True) -> None:
        """Refresh the rows of the widget"""
        if with_lock:
            async with self.__lock:
                await self.__refresh_rows()
        else:
            await self.__refresh_rows()

    async def __refresh_rows(self) -> None:
        self.rows.clear()
        for file in self.open_files:
            fd = str(file.fd)
            fp = file.path.replace(" ", "_")
            fs = file.filesize
            self.add_row(fd, fp, fs)
        logger.log("".join([file.path for file in self.open_files]))

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
            fd_width = 5
            if self.app.should_render_in_landscape_mode:  # pyright: ignore
                path_width = (columns // 2) - 25
            else:
                path_width = columns - 25
            filesize_width = 10
            self.columns.clear()
            self.add_column("FD", width=fd_width)
            self.add_column("Path", width=path_width)
            self.add_column("File Size", width=filesize_width)

    def on_data_table_row_highlighted(self, event) -> None:
        # RowHighlighted(cursor_row=1, row_key=<textual.widgets._data_table.RowKey object at 0x10874dcd0>
        """Event handler for when a row is highlighted"""
        row = self.get_row(event.row_key)
        logger.log(f"[!!] OpenFilesListWidget: highlighted row: {row}")
