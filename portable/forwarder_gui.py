from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from platform_client import (
    PlatformBootstrap,
    PlatformClient,
    PlatformGame,
    PlatformStream,
    normalize_platform_url,
)
from platform_ingest import ENV_FILE, IngestConfig, run_forwarder

DEFAULT_VALUES = {
    "PLATFORM_URL": "http://www.yangqingci.com",
    "ACCESS_TOKEN": "",
    "SELECTED_STREAM_ID": "",
    "SELECTED_GAME_CODE": "danmaku_exam",
}

LOG_POLL_BATCH_SIZE = 50
LOG_LINE_LIMIT = 500
LOG_QUEUE_LIMIT = 1000


def read_env(path: Path = ENV_FILE) -> dict[str, str]:
    values = dict(DEFAULT_VALUES)
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key in values:
            values[key] = value
        elif key == "INGEST_URL":
            values["PLATFORM_URL"] = normalize_platform_url(value)
        elif key == "INGEST_GAME_CODE":
            values["SELECTED_GAME_CODE"] = value
    return values


def write_env(values: dict[str, str], path: Path = ENV_FILE) -> None:
    content = (
        "# 弹幕采集器客户端配置，由图形界面生成。\n"
        "# 不保存平台登录密码。ACCESS_TOKEN 退出登录后会被清空。\n"
        f"PLATFORM_URL={normalize_platform_url(values['PLATFORM_URL'])}\n"
        f"ACCESS_TOKEN={values['ACCESS_TOKEN'].strip()}\n"
        f"SELECTED_STREAM_ID={values['SELECTED_STREAM_ID'].strip()}\n"
        f"SELECTED_GAME_CODE={values['SELECTED_GAME_CODE'].strip()}\n"
    )
    path.write_text(content, encoding="utf-8")


class ForwarderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("弹幕采集器")
        self.root.geometry("760x560")
        self.root.minsize(680, 500)
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.log_line_count = 0
        self.dropped_log_count = 0
        self.bootstrap: PlatformBootstrap | None = None
        self.streams: list[PlatformStream] = []
        self.games: list[PlatformGame] = []
        self.vars = {
            "PLATFORM_URL": tk.StringVar(),
            "USERNAME": tk.StringVar(),
            "PASSWORD": tk.StringVar(),
            "ACCESS_TOKEN": tk.StringVar(),
            "SELECTED_STREAM_ID": tk.StringVar(),
            "SELECTED_GAME_CODE": tk.StringVar(),
        }
        self._build_ui()
        self._load_values()
        self._poll_log_queue()
        if self.vars["ACCESS_TOKEN"].get().strip():
            self.refresh_platform_config(silent=True)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(9, weight=1)

        ttk.Label(frame, text="平台地址").grid(row=0, column=0, sticky=tk.W, pady=6)
        ttk.Entry(frame, textvariable=self.vars["PLATFORM_URL"]).grid(
            row=0,
            column=1,
            sticky=tk.EW,
            pady=6,
        )

        self.login_frame = ttk.Frame(frame)
        self.login_frame.grid(row=1, column=0, columnspan=2, sticky=tk.EW)
        self.login_frame.columnconfigure(1, weight=1)

        ttk.Label(self.login_frame, text="用户名").grid(row=0, column=0, sticky=tk.W, pady=6)
        ttk.Entry(self.login_frame, textvariable=self.vars["USERNAME"]).grid(
            row=0,
            column=1,
            sticky=tk.EW,
            pady=6,
        )
        ttk.Label(self.login_frame, text="密码").grid(row=1, column=0, sticky=tk.W, pady=6)
        ttk.Entry(self.login_frame, textvariable=self.vars["PASSWORD"], show="*").grid(
            row=1,
            column=1,
            sticky=tk.EW,
            pady=6,
        )
        self.login_button = ttk.Button(
            self.login_frame,
            text="登录",
            command=self.login,
        )
        self.login_button.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(8, 6))

        self.client_frame = ttk.Frame(frame)
        self.client_frame.grid(row=2, column=0, columnspan=2, sticky=tk.EW)
        self.client_frame.columnconfigure(1, weight=1)

        ttk.Label(self.client_frame, text="当前账号").grid(row=0, column=0, sticky=tk.W, pady=6)
        self.user_var = tk.StringVar(value="未登录")
        ttk.Label(self.client_frame, textvariable=self.user_var).grid(
            row=0,
            column=1,
            sticky=tk.W,
            pady=6,
        )

        ttk.Label(self.client_frame, text="直播间").grid(row=1, column=0, sticky=tk.W, pady=6)
        self.stream_box = ttk.Combobox(self.client_frame, state="readonly")
        self.stream_box.grid(row=1, column=1, sticky=tk.EW, pady=6)
        self.stream_box.bind("<<ComboboxSelected>>", lambda _event: self._set_stream_from_label())

        ttk.Label(self.client_frame, text="游戏").grid(row=2, column=0, sticky=tk.W, pady=6)
        self.game_box = ttk.Combobox(self.client_frame, state="readonly")
        self.game_box.grid(row=2, column=1, sticky=tk.EW, pady=6)
        self.game_box.bind("<<ComboboxSelected>>", lambda _event: self._set_game_from_label())

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(10, 8))
        self.refresh_button = ttk.Button(
            button_frame,
            text="刷新配置",
            command=lambda: self.refresh_platform_config(silent=False),
        )
        self.refresh_button.pack(side=tk.LEFT)
        self.start_button = ttk.Button(button_frame, text="开始采集", command=self.start_forwarder)
        self.start_button.pack(side=tk.LEFT, padx=8)
        self.logout_button = ttk.Button(button_frame, text="退出登录", command=self.logout)
        self.logout_button.pack(side=tk.LEFT)
        ttk.Button(button_frame, text="关闭", command=self.root.destroy).pack(side=tk.RIGHT)

        self.status_var = tk.StringVar(value="未登录")
        ttk.Label(frame, textvariable=self.status_var).grid(
            row=4,
            column=0,
            columnspan=2,
            sticky=tk.W,
            pady=(0, 8),
        )

        self.log_text = tk.Text(frame, height=14, wrap=tk.WORD)
        self.log_text.grid(row=9, column=0, columnspan=2, sticky=tk.NSEW)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.grid(row=9, column=2, sticky=tk.NS)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self._set_logged_in_ui(False)

    def _load_values(self) -> None:
        values = read_env()
        for key in ("PLATFORM_URL", "ACCESS_TOKEN", "SELECTED_STREAM_ID", "SELECTED_GAME_CODE"):
            self.vars[key].set(values.get(key, DEFAULT_VALUES[key]))

    def _save_values(self) -> None:
        write_env(
            {
                "PLATFORM_URL": self.vars["PLATFORM_URL"].get(),
                "ACCESS_TOKEN": self.vars["ACCESS_TOKEN"].get(),
                "SELECTED_STREAM_ID": self.vars["SELECTED_STREAM_ID"].get(),
                "SELECTED_GAME_CODE": self.vars["SELECTED_GAME_CODE"].get(),
            }
        )

    def _client(self) -> PlatformClient:
        return PlatformClient(
            self.vars["PLATFORM_URL"].get(),
            access_token=self.vars["ACCESS_TOKEN"].get(),
        )

    def login(self) -> None:
        platform_url = normalize_platform_url(self.vars["PLATFORM_URL"].get())
        username = self.vars["USERNAME"].get().strip()
        password = self.vars["PASSWORD"].get()
        if not platform_url:
            messagebox.showwarning("配置不完整", "请填写平台地址")
            return
        if not username or not password:
            messagebox.showwarning("配置不完整", "请填写用户名和密码")
            return

        self.login_button.configure(state=tk.DISABLED)
        self.status_var.set("正在登录")
        threading.Thread(
            target=self._login_worker,
            args=(platform_url, username, password),
            daemon=True,
        ).start()

    def _login_worker(self, platform_url: str, username: str, password: str) -> None:
        try:
            client = PlatformClient(platform_url)
            token = client.login(username, password)
            bootstrap = client.bootstrap()
        except Exception as exc:
            self.log_queue.put(("login_error", str(exc)))
            return
        self.log_queue.put(("login_success", platform_url, token, bootstrap))

    def refresh_platform_config(self, *, silent: bool) -> None:
        if not self.vars["ACCESS_TOKEN"].get().strip():
            if not silent:
                messagebox.showinfo("未登录", "请先登录平台账号")
            return
        self.refresh_button.configure(state=tk.DISABLED)
        self.status_var.set("正在读取平台配置")
        threading.Thread(
            target=self._refresh_worker,
            args=(silent,),
            daemon=True,
        ).start()

    def _refresh_worker(self, silent: bool) -> None:
        try:
            bootstrap = self._client().bootstrap()
        except Exception as exc:
            self.log_queue.put(("refresh_error", str(exc), silent))
            return
        self.log_queue.put(("refresh_success", bootstrap, silent))

    def logout(self) -> None:
        self.vars["ACCESS_TOKEN"].set("")
        self.vars["PASSWORD"].set("")
        self.bootstrap = None
        self.streams = []
        self.games = []
        self.user_var.set("未登录")
        self.stream_box.configure(values=())
        self.game_box.configure(values=())
        self._save_values()
        self._set_logged_in_ui(False)
        self.status_var.set("已退出登录")

    def _apply_bootstrap(self, bootstrap: PlatformBootstrap) -> None:
        self.bootstrap = bootstrap
        self.streams = bootstrap.streams
        self.games = bootstrap.games
        display_name = bootstrap.user.display_name or bootstrap.user.username
        self.user_var.set(f"{display_name} ({bootstrap.user.username})")
        self.stream_box.configure(values=[stream.label for stream in self.streams])
        self.game_box.configure(values=[game.label for game in self.games])
        self._select_saved_stream()
        self._select_saved_game()
        self._set_logged_in_ui(True)
        if not self.streams:
            self.status_var.set("平台账号未绑定直播间，请先到平台配置直播间")
        elif not self.games:
            self.status_var.set("当前账号没有可用游戏权限")
        else:
            self.status_var.set("已登录，配置已同步")

    def _select_saved_stream(self) -> None:
        selected_id = self.vars["SELECTED_STREAM_ID"].get().strip()
        index = 0
        for current_index, stream in enumerate(self.streams):
            if stream.id == selected_id:
                index = current_index
                break
        if self.streams:
            self.stream_box.current(index)
            self.vars["SELECTED_STREAM_ID"].set(self.streams[index].id)

    def _select_saved_game(self) -> None:
        selected_code = self.vars["SELECTED_GAME_CODE"].get().strip()
        index = 0
        for current_index, game in enumerate(self.games):
            if game.code == selected_code:
                index = current_index
                break
        if self.games:
            self.game_box.current(index)
            self.vars["SELECTED_GAME_CODE"].set(self.games[index].code)

    def _set_stream_from_label(self) -> None:
        index = self.stream_box.current()
        if 0 <= index < len(self.streams):
            self.vars["SELECTED_STREAM_ID"].set(self.streams[index].id)
            self._save_values()

    def _set_game_from_label(self) -> None:
        index = self.game_box.current()
        if 0 <= index < len(self.games):
            self.vars["SELECTED_GAME_CODE"].set(self.games[index].code)
            self._save_values()

    def _selected_stream(self) -> PlatformStream | None:
        selected_id = self.vars["SELECTED_STREAM_ID"].get().strip()
        return next((stream for stream in self.streams if stream.id == selected_id), None)

    def _selected_game(self) -> PlatformGame | None:
        selected_code = self.vars["SELECTED_GAME_CODE"].get().strip()
        return next((game for game in self.games if game.code == selected_code), None)

    def start_forwarder(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("采集中", "采集器已经在运行")
            return
        stream = self._selected_stream()
        game = self._selected_game()
        if stream is None:
            messagebox.showwarning("配置不完整", "请选择直播间")
            return
        if game is None:
            messagebox.showwarning("配置不完整", "请选择游戏")
            return
        ingest_url = self._ingest_url()
        if not ingest_url:
            messagebox.showwarning("配置不完整", "平台没有返回弹幕接入地址")
            return

        self._save_values()
        config = IngestConfig(
            url=ingest_url,
            token=stream.ingest_token,
            room_id=stream.douyin_room_id,
            game_code=game.code,
        )
        self.status_var.set("正在采集")
        self.start_button.configure(state=tk.DISABLED)
        self.worker = threading.Thread(
            target=self._run_worker,
            args=(stream.douyin_room_id, config),
            daemon=True,
        )
        self.worker.start()

    def _ingest_url(self) -> str:
        if self.bootstrap and self.bootstrap.config.default_ingest_url:
            return self.bootstrap.config.default_ingest_url
        return f"{normalize_platform_url(self.vars['PLATFORM_URL'].get())}/ingest"

    def _run_worker(self, live_id: str, config: IngestConfig) -> None:
        try:
            run_forwarder(live_id, config, log=self._enqueue_worker_log)
        except Exception as exc:
            self._enqueue_worker_log(f"[error] {exc}")
            self._enqueue_worker_log("[status] stopped")

    def _enqueue_worker_log(self, message: str) -> None:
        if message == "[status] stopped":
            self.log_queue.put(message)
            return

        if self.log_queue.qsize() >= LOG_QUEUE_LIMIT:
            self.dropped_log_count += 1
            return

        if self.dropped_log_count and self.log_queue.qsize() < LOG_QUEUE_LIMIT - 1:
            dropped_count = self.dropped_log_count
            self.dropped_log_count = 0
            self.log_queue.put(f"[log] skipped {dropped_count} log line(s) to keep the UI responsive")

        self.log_queue.put(str(message))

    def _poll_log_queue(self) -> None:
        processed = 0
        while processed < LOG_POLL_BATCH_SIZE:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            processed += 1
            self._handle_log_message(message)
        self.root.after(200, self._poll_log_queue)

    def _handle_log_message(self, message) -> None:
        if isinstance(message, tuple):
            event = message[0]
            if event == "login_success":
                _event, platform_url, token, bootstrap = message
                self.vars["PLATFORM_URL"].set(platform_url)
                self.vars["ACCESS_TOKEN"].set(token)
                self.vars["PASSWORD"].set("")
                self._apply_bootstrap(bootstrap)
                self._save_values()
                self.login_button.configure(state=tk.NORMAL)
                self._append_log("[auth] login succeeded")
                return
            if event == "login_error":
                self.login_button.configure(state=tk.NORMAL)
                self.status_var.set("登录失败")
                self._append_log(f"[auth] {message[1]}")
                messagebox.showerror("登录失败", message[1])
                return
            if event == "refresh_success":
                _event, bootstrap, silent = message
                self.refresh_button.configure(state=tk.NORMAL)
                self._apply_bootstrap(bootstrap)
                self._save_values()
                if not silent:
                    self._append_log("[config] platform config refreshed")
                return
            if event == "refresh_error":
                _event, error, silent = message
                self.refresh_button.configure(state=tk.NORMAL)
                self.status_var.set("读取平台配置失败")
                if not silent:
                    messagebox.showerror("读取平台配置失败", error)
                self._append_log(f"[config] {error}")
                return

        if message == "[status] stopped":
            self.status_var.set("已停止")
            self.start_button.configure(state=tk.NORMAL)
        else:
            self._append_log(message)

    def _append_log(self, message: str) -> None:
        self.log_text.insert(tk.END, message + "\n")
        self.log_line_count += 1
        if self.log_line_count > LOG_LINE_LIMIT:
            overflow = self.log_line_count - LOG_LINE_LIMIT
            self.log_text.delete("1.0", f"{overflow + 1}.0")
            self.log_line_count = LOG_LINE_LIMIT
        self.log_text.see(tk.END)

    def _set_logged_in_ui(self, logged_in: bool) -> None:
        state = tk.NORMAL if logged_in else tk.DISABLED
        self.refresh_button.configure(state=state)
        self.start_button.configure(state=state)
        self.logout_button.configure(state=state)
        self.stream_box.configure(state="readonly" if logged_in else tk.DISABLED)
        self.game_box.configure(state="readonly" if logged_in else tk.DISABLED)


def main() -> None:
    root = tk.Tk()
    ForwarderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
