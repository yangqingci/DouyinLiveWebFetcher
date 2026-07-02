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

from platform_ingest import ENV_FILE, IngestConfig, run_forwarder

DEFAULT_VALUES = {
    "INGEST_URL": "http://www.yangqingci.com/ingest",
    "INGEST_TOKEN": "",
    "DOUYIN_LIVE_ID": "",
    "INGEST_ROOM_ID": "",
    "INGEST_GAME_CODE": "danmaku_exam",
}

LOG_POLL_BATCH_SIZE = 50
LOG_LINE_LIMIT = 500
LOG_QUEUE_LIMIT = 1000

GAME_OPTIONS = (
    ("弹幕答题/驾考", "danmaku_exam"),
    ("语义猜词", "semantic_guess"),
    ("成语接龙", "idiom_chain"),
)


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
        if key in values:
            values[key] = value.strip()
    return values


def write_env(values: dict[str, str], path: Path = ENV_FILE) -> None:
    content = (
        "# 弹幕推送配置，由图形配置器生成。\n"
        f"INGEST_URL={values['INGEST_URL'].strip()}\n"
        f"INGEST_TOKEN={values['INGEST_TOKEN'].strip()}\n"
        f"DOUYIN_LIVE_ID={values['DOUYIN_LIVE_ID'].strip()}\n"
        f"INGEST_ROOM_ID={values['INGEST_ROOM_ID'].strip()}\n"
        f"INGEST_GAME_CODE={values['INGEST_GAME_CODE'].strip()}\n"
    )
    path.write_text(content, encoding="utf-8")


class ForwarderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("弹幕采集器")
        self.root.geometry("720x520")
        self.root.minsize(640, 460)
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.log_line_count = 0
        self.dropped_log_count = 0
        self.vars = {
            "INGEST_URL": tk.StringVar(),
            "INGEST_TOKEN": tk.StringVar(),
            "DOUYIN_LIVE_ID": tk.StringVar(),
            "INGEST_ROOM_ID": tk.StringVar(),
            "INGEST_GAME_CODE": tk.StringVar(),
        }
        self._build_ui()
        self._load_values()
        self._poll_log_queue()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(7, weight=1)

        ttk.Label(frame, text="平台接入地址").grid(row=0, column=0, sticky=tk.W, pady=6)
        ttk.Entry(frame, textvariable=self.vars["INGEST_URL"]).grid(
            row=0,
            column=1,
            sticky=tk.EW,
            pady=6,
        )

        ttk.Label(frame, text="Ingest Token").grid(row=1, column=0, sticky=tk.W, pady=6)
        ttk.Entry(frame, textvariable=self.vars["INGEST_TOKEN"], show="*").grid(
            row=1,
            column=1,
            sticky=tk.EW,
            pady=6,
        )

        ttk.Label(frame, text="抖音直播间 ID").grid(row=2, column=0, sticky=tk.W, pady=6)
        ttk.Entry(frame, textvariable=self.vars["DOUYIN_LIVE_ID"]).grid(
            row=2,
            column=1,
            sticky=tk.EW,
            pady=6,
        )

        ttk.Label(frame, text="平台绑定直播间 ID").grid(row=3, column=0, sticky=tk.W, pady=6)
        ttk.Entry(frame, textvariable=self.vars["INGEST_ROOM_ID"]).grid(
            row=3,
            column=1,
            sticky=tk.EW,
            pady=6,
        )

        ttk.Label(frame, text="目标游戏").grid(row=4, column=0, sticky=tk.W, pady=6)
        game_box = ttk.Combobox(
            frame,
            state="readonly",
            values=[f"{name} ({code})" for name, code in GAME_OPTIONS],
        )
        game_box.grid(row=4, column=1, sticky=tk.EW, pady=6)
        game_box.bind("<<ComboboxSelected>>", lambda _event: self._set_game_from_label(game_box.get()))
        self.game_box = game_box

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=5, column=0, columnspan=2, sticky=tk.EW, pady=(10, 8))
        ttk.Button(button_frame, text="保存配置", command=self.save_config).pack(side=tk.LEFT)
        self.start_button = ttk.Button(button_frame, text="开始采集", command=self.start_forwarder)
        self.start_button.pack(
            side=tk.LEFT,
            padx=8,
        )
        ttk.Button(button_frame, text="退出", command=self.root.destroy).pack(side=tk.RIGHT)

        self.status_var = tk.StringVar(value="未启动")
        ttk.Label(frame, textvariable=self.status_var).grid(
            row=6,
            column=0,
            columnspan=2,
            sticky=tk.W,
            pady=(0, 8),
        )

        self.log_text = tk.Text(frame, height=12, wrap=tk.WORD)
        self.log_text.grid(row=7, column=0, columnspan=2, sticky=tk.NSEW)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.grid(row=7, column=2, sticky=tk.NS)
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _load_values(self) -> None:
        values = read_env()
        for key, var in self.vars.items():
            var.set(values.get(key, DEFAULT_VALUES[key]))
        self._sync_game_box()

    def _set_game_from_label(self, label: str) -> None:
        for name, code in GAME_OPTIONS:
            if label == f"{name} ({code})":
                self.vars["INGEST_GAME_CODE"].set(code)
                return

    def _sync_game_box(self) -> None:
        current = self.vars["INGEST_GAME_CODE"].get().strip()
        for index, (name, code) in enumerate(GAME_OPTIONS):
            if code == current:
                self.game_box.current(index)
                return
        self.game_box.current(0)
        self.vars["INGEST_GAME_CODE"].set(GAME_OPTIONS[0][1])

    def _values(self) -> dict[str, str]:
        values = {key: var.get().strip() for key, var in self.vars.items()}
        if not values["INGEST_ROOM_ID"]:
            values["INGEST_ROOM_ID"] = values["DOUYIN_LIVE_ID"]
        return values

    def _validate(self, values: dict[str, str]) -> str | None:
        required = {
            "INGEST_URL": "平台接入地址",
            "INGEST_TOKEN": "Ingest Token",
            "DOUYIN_LIVE_ID": "抖音直播间 ID",
            "INGEST_GAME_CODE": "目标游戏",
        }
        for key, label in required.items():
            if not values[key]:
                return f"请填写{label}"
        return None

    def save_config(self) -> bool:
        values = self._values()
        error = self._validate(values)
        if error:
            messagebox.showwarning("配置不完整", error)
            return False
        write_env(values)
        self._append_log(f"[config] saved to {ENV_FILE}")
        return True

    def start_forwarder(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("采集中", "采集器已经在运行")
            return
        if not self.save_config():
            return
        values = self._values()
        config = IngestConfig(
            url=values["INGEST_URL"],
            token=values["INGEST_TOKEN"],
            room_id=values["INGEST_ROOM_ID"],
            game_code=values["INGEST_GAME_CODE"],
        )
        self.status_var.set("正在采集")
        self.start_button.configure(state=tk.DISABLED)
        self.worker = threading.Thread(
            target=self._run_worker,
            args=(values["DOUYIN_LIVE_ID"], config),
            daemon=True,
        )
        self.worker.start()

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
            if message == "[status] stopped":
                self.status_var.set("已停止")
                self.start_button.configure(state=tk.NORMAL)
            else:
                self._append_log(message)
        self.root.after(200, self._poll_log_queue)

    def _append_log(self, message: str) -> None:
        self.log_text.insert(tk.END, message + "\n")
        self.log_line_count += 1
        if self.log_line_count > LOG_LINE_LIMIT:
            overflow = self.log_line_count - LOG_LINE_LIMIT
            self.log_text.delete("1.0", f"{overflow + 1}.0")
            self.log_line_count = LOG_LINE_LIMIT
        self.log_text.see(tk.END)


def main() -> None:
    root = tk.Tk()
    ForwarderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
