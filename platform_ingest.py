from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from liveMan import DouyinLiveWebFetcher

REQUEST_TIMEOUT_SEC = 2.0


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = app_dir()
ENV_FILE = APP_DIR / "platform_ingest.env"


def bundled_file(name: str) -> Path:
    candidates = [
        APP_DIR / name,
        Path(getattr(sys, "_MEIPASS", APP_DIR)) / name,
        APP_DIR / "_internal" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


ENV_EXAMPLE_FILE = bundled_file("platform_ingest.env.example")


@dataclass(frozen=True)
class IngestConfig:
    url: str
    token: str
    room_id: str | None
    game_code: str | None


def _read_env(name: str) -> str:
    return os.environ.get(name, "").strip()


def load_env_file(path: Path = ENV_FILE) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing env file: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip()


def _require_env(name: str) -> str:
    value = _read_env(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _usage() -> str:
    return (
        "Usage:\n"
        "  python platform_ingest.py\n"
        "  python platform_ingest.py <douyin_live_id>\n\n"
        "Config file:\n"
        f"  {ENV_FILE}\n\n"
        "Required config keys:\n"
        "  INGEST_URL    Cloud platform ingest URL, e.g. http://server:8080/ingest\n"
        "  INGEST_TOKEN  User ingest token copied from the platform\n"
        "  DOUYIN_LIVE_ID  Used when <douyin_live_id> is not passed\n\n"
        "Optional config keys:\n"
        "  INGEST_ROOM_ID  Sent as douyin_room_id; defaults to the live id\n"
        "  INGEST_GAME_CODE  Target platform game, e.g. danmaku_exam\n"
    )


def load_runtime_config(argv: list[str]) -> tuple[str, IngestConfig]:
    live_id = argv[1].strip() if len(argv) > 1 else _read_env("DOUYIN_LIVE_ID")
    if not live_id:
        raise ValueError("Missing Douyin live id")

    ingest_url = _require_env("INGEST_URL")
    ingest_token = _require_env("INGEST_TOKEN")
    room_id = _read_env("INGEST_ROOM_ID") or live_id
    game_code = _read_env("INGEST_GAME_CODE") or None
    return live_id, IngestConfig(
        url=ingest_url,
        token=ingest_token,
        room_id=room_id,
        game_code=game_code,
    )


def build_ingest_payload(
    room_id: str | None,
    game_code: str | None,
    *,
    event_type: str | None = None,
    nickname: str = "",
    text: str = "",
    gift_name: str = "",
    gift_count: int | None = None,
    like_count: int | None = None,
    metadata: dict | None = None,
) -> dict:
    payload: dict = {"nickname": nickname, "text": text}
    normalized_room_id = (room_id or "").strip()
    if normalized_room_id:
        payload["douyin_room_id"] = normalized_room_id
    normalized_game_code = (game_code or "").strip()
    if normalized_game_code:
        payload["game_code"] = normalized_game_code
    if event_type:
        payload["event_type"] = event_type
    if gift_name:
        payload["gift_name"] = gift_name
    if gift_count is not None:
        payload["gift_count"] = gift_count
    if like_count is not None:
        payload["like_count"] = like_count
    if metadata:
        payload["metadata"] = metadata
    return payload


def _post_payload(config: IngestConfig, payload: dict) -> None:
    response = requests.post(
        config.url,
        headers={"X-Ingest-Token": config.token},
        json=payload,
        timeout=REQUEST_TIMEOUT_SEC,
    )
    response.raise_for_status()


def post_comment(config: IngestConfig, message) -> None:
    user = getattr(message, "user", None)
    nickname = getattr(user, "nick_name", "") or "观众"
    text = getattr(message, "content", "") or ""
    if not text:
        return
    _post_payload(
        config,
        build_ingest_payload(
            config.room_id,
            config.game_code,
            event_type="chat",
            nickname=nickname,
            text=text,
        ),
    )


def post_event(config: IngestConfig, event: dict) -> None:
    _post_payload(
        config,
        build_ingest_payload(
            config.room_id,
            config.game_code,
            event_type=event.get("event_type"),
            nickname=event.get("nickname", "") or "观众",
            text=event.get("text", "") or "",
            gift_name=event.get("gift_name", "") or "",
            gift_count=event.get("gift_count"),
            like_count=event.get("like_count"),
            metadata=event.get("metadata"),
        ),
    )


def run_forwarder(
    live_id: str,
    ingest_config: IngestConfig,
    *,
    log=print,
) -> None:
    fetcher = DouyinLiveWebFetcher(live_id, log=log, log_events=False)
    forwarded_count = 0
    failed_count = 0
    last_progress_log = 0.0
    last_failure_log = 0.0

    def _dispatch(fn, *args) -> None:
        nonlocal failed_count, forwarded_count, last_failure_log, last_progress_log
        try:
            fn(*args)
        except Exception as exc:
            failed_count += 1
            now = time.monotonic()
            if failed_count == 1 or now - last_failure_log >= 10:
                log(f"[ingest] post failed ({failed_count} total): {exc}")
                last_failure_log = now
            return
        forwarded_count += 1
        now = time.monotonic()
        if forwarded_count == 1 or now - last_progress_log >= 10:
            log(f"[ingest] forwarded {forwarded_count} event(s)")
            last_progress_log = now

    fetcher.on_comment = lambda msg: _dispatch(post_comment, ingest_config, msg)
    fetcher.on_gift = lambda ev: _dispatch(post_event, ingest_config, ev)
    fetcher.on_like = lambda ev: _dispatch(post_event, ingest_config, ev)
    fetcher.on_member = lambda ev: _dispatch(post_event, ingest_config, ev)
    fetcher.on_social = lambda ev: _dispatch(post_event, ingest_config, ev)
    fetcher.on_fansclub = lambda ev: _dispatch(post_event, ingest_config, ev)
    fetcher.on_stats = lambda ev: _dispatch(post_event, ingest_config, ev)

    game_label = ingest_config.game_code or "platform default"
    log(
        f"[ingest] forwarding live {live_id} events to "
        f"{ingest_config.url} game={game_label}"
    )
    fetcher.start()


def main(argv: list[str] | None = None) -> None:
    argv = argv or sys.argv
    try:
        load_env_file()
        live_id, ingest_config = load_runtime_config(argv)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[config] {exc}")
        if isinstance(exc, FileNotFoundError) and ENV_EXAMPLE_FILE.exists():
            print(f"[config] Copy {ENV_EXAMPLE_FILE.name} to {ENV_FILE.name} and edit it.")
        print(_usage())
        raise SystemExit(1) from exc

    run_forwarder(live_id, ingest_config)


if __name__ == "__main__":
    main()
