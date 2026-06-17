from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

from liveMan import DouyinLiveWebFetcher

REQUEST_TIMEOUT_SEC = 2.0
ENV_FILE = Path(__file__).with_name("platform_ingest.env")
ENV_EXAMPLE_FILE = Path(__file__).with_name("platform_ingest.env.example")


@dataclass(frozen=True)
class IngestConfig:
    url: str
    token: str
    room_id: str | None


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
    )


def load_runtime_config(argv: list[str]) -> tuple[str, IngestConfig]:
    live_id = argv[1].strip() if len(argv) > 1 else _read_env("DOUYIN_LIVE_ID")
    if not live_id:
        raise ValueError("Missing Douyin live id")

    ingest_url = _require_env("INGEST_URL")
    ingest_token = _require_env("INGEST_TOKEN")
    room_id = _read_env("INGEST_ROOM_ID") or live_id
    return live_id, IngestConfig(url=ingest_url, token=ingest_token, room_id=room_id)


def build_ingest_payload(
    nickname: str,
    text: str,
    room_id: str | None,
) -> dict[str, str]:
    payload = {"nickname": nickname, "text": text}
    normalized_room_id = (room_id or "").strip()
    if normalized_room_id:
        payload["douyin_room_id"] = normalized_room_id
    return payload


def post_comment(config: IngestConfig, message) -> None:
    user = getattr(message, "user", None)
    nickname = getattr(user, "nick_name", "") or "观众"
    text = getattr(message, "content", "") or ""
    if not text:
        return

    response = requests.post(
        config.url,
        headers={"X-Ingest-Token": config.token},
        json=build_ingest_payload(nickname, text, config.room_id),
        timeout=REQUEST_TIMEOUT_SEC,
    )
    response.raise_for_status()


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

    fetcher = DouyinLiveWebFetcher(live_id)

    def on_comment(message) -> None:
        try:
            post_comment(ingest_config, message)
        except Exception as exc:
            print(f"[ingest] post failed: {exc}")

    fetcher.on_comment = on_comment
    print(f"[ingest] forwarding live {live_id} danmaku to {ingest_config.url}")
    fetcher.start()


if __name__ == "__main__":
    main()
