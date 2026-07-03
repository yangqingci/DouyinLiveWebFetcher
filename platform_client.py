from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

import requests

REQUEST_TIMEOUT_SEC = 10.0
DEFAULT_PLATFORM_URL = "http://www.yangqingci.com"


@dataclass(frozen=True)
class PlatformUser:
    id: int
    username: str
    display_name: str | None


@dataclass(frozen=True)
class PlatformStream:
    id: str
    display_name: str | None
    douyin_room_id: str
    ingest_token: str
    is_active: bool

    @property
    def label(self) -> str:
        name = self.display_name or self.douyin_room_id
        return f"{name} ({self.douyin_room_id})"


@dataclass(frozen=True)
class PlatformGame:
    code: str
    name: str
    description: str

    @property
    def label(self) -> str:
        return f"{self.name} ({self.code})"


@dataclass(frozen=True)
class PlatformBootstrapConfig:
    default_ingest_url: str
    ingest_path: str
    api_base_path: str
    features: dict[str, object]


@dataclass(frozen=True)
class PlatformBootstrap:
    user: PlatformUser
    streams: list[PlatformStream]
    games: list[PlatformGame]
    config: PlatformBootstrapConfig


class PlatformClientError(RuntimeError):
    pass


class PlatformClient:
    def __init__(self, base_url: str, access_token: str = "") -> None:
        self.base_url = normalize_platform_url(base_url)
        self.access_token = access_token.strip()

    def login(self, username: str, password: str) -> str:
        response = requests.post(
            self._url("/api/auth/login"),
            json={"username": username.strip(), "password": password},
            timeout=REQUEST_TIMEOUT_SEC,
        )
        payload = _response_json(response)
        if response.status_code >= 400:
            raise PlatformClientError(_error_message(payload, "登录失败"))
        token = str(payload.get("access_token", "")).strip()
        if not token:
            raise PlatformClientError("登录失败：平台没有返回 access_token")
        self.access_token = token
        return token

    def bootstrap(self) -> PlatformBootstrap:
        if not self.access_token:
            raise PlatformClientError("请先登录平台账号")
        response = requests.get(
            self._url("/api/client/bootstrap"),
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=REQUEST_TIMEOUT_SEC,
        )
        payload = _response_json(response)
        if response.status_code >= 400:
            raise PlatformClientError(_error_message(payload, "读取平台配置失败"))
        return _parse_bootstrap(payload)

    def _url(self, path: str) -> str:
        return urljoin(f"{self.base_url}/", path.lstrip("/"))


def normalize_platform_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    if normalized.endswith("/ingest"):
        normalized = normalized[: -len("/ingest")]
    return normalized or DEFAULT_PLATFORM_URL


def _response_json(response: requests.Response) -> dict[str, object]:
    try:
        payload = response.json()
    except ValueError:
        return {"detail": response.text.strip()}
    return payload if isinstance(payload, dict) else {"detail": str(payload)}


def _error_message(payload: dict[str, object], fallback: str) -> str:
    detail = payload.get("detail")
    if isinstance(detail, dict):
        message = str(detail.get("message") or fallback)
        if detail.get("captcha_required"):
            return f"{message}。请先到平台网页登录完成验证码验证。"
        return message
    if isinstance(detail, str) and detail:
        return detail
    return fallback


def _parse_bootstrap(payload: dict[str, object]) -> PlatformBootstrap:
    raw_user = payload.get("user")
    raw_config = payload.get("config")
    raw_streams = payload.get("streams")
    raw_games = payload.get("games")
    user_payload = raw_user if isinstance(raw_user, dict) else {}
    config_payload = raw_config if isinstance(raw_config, dict) else {}
    streams_payload = raw_streams if isinstance(raw_streams, list) else []
    games_payload = raw_games if isinstance(raw_games, list) else []
    raw_features = config_payload.get("features")
    return PlatformBootstrap(
        user=PlatformUser(
            id=int(user_payload.get("id") or 0),
            username=str(user_payload.get("username") or ""),
            display_name=user_payload.get("display_name"),
        ),
        streams=[
            PlatformStream(
                id=str(item.get("id") or ""),
                display_name=item.get("display_name"),
                douyin_room_id=str(item.get("douyin_room_id") or ""),
                ingest_token=str(item.get("ingest_token") or ""),
                is_active=bool(item.get("is_active")),
            )
            for item in streams_payload
            if isinstance(item, dict)
        ],
        games=[
            PlatformGame(
                code=str(item.get("code") or ""),
                name=str(item.get("name") or ""),
                description=str(item.get("description") or ""),
            )
            for item in games_payload
            if isinstance(item, dict)
        ],
        config=PlatformBootstrapConfig(
            default_ingest_url=str(config_payload.get("default_ingest_url") or ""),
            ingest_path=str(config_payload.get("ingest_path") or "/ingest"),
            api_base_path=str(config_payload.get("api_base_path") or "/api"),
            features=raw_features if isinstance(raw_features, dict) else {},
        ),
    )
