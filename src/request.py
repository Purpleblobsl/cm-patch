import json
from dataclasses import dataclass
from typing import (
    Any,
    Dict,
    Literal,
    Self,
)
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from .utils import http_code_to_string, logger_get

# ------------------------------------------------------------------------------

log = logger_get(__name__)

# ------------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Request:
    method: Literal["GET", "POST", "DELETE", "PUT"]
    url: str
    headers: Dict[str, str] | None = None
    params: Dict[str, Any] | None = None
    data: Dict[str, Any] | None = None
    json: bool = True

    def fetch(self) -> Response:
        def parse_response_body(raw: bytes) -> Any:
            if not raw: return None

            try:
                return json.loads(raw) if raw else None
            except json.JSONDecodeError:
                return raw.decode(errors="replace")

        url = self.url

        if self.params:
            url = f"{url}?{urlencode(self.params)}"

        body = None
        headers = dict(self.headers or {})

        if self.data is not None:
            if self.json:
                body = json.dumps(self.data).encode("utf-8")
                headers["Content-Type"] = "application/json"

            else:
                body = urlencode(self.data).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded"

        log.debug("Request:\n%s", self)

        request = UrlRequest(
            url=url,
            data=body,
            headers=headers or {},
            method=self.method,
        )

        try:
            with urlopen(request) as response:
                response = Response(
                    status=response.status,
                    headers=dict(response.headers),
                    data=parse_response_body(response.read()),
                )

        except HTTPError as e:
            response = Response(
                status=e.code,
                headers=dict(e.headers),
                data=parse_response_body(e.read()),
            )

        log.debug("Response:\n%s", response)
        log.info(
            "%s %s | %s %s",
            response.status,
            response.status_text,
            self.method, url
        )

        return response

    def __str__(self) -> str:
        url = self.url
        if self.params:
            url = f"{url}?{urlencode(self.params)}"

        headers = dict(self.headers or {})

        if self.data is not None:
            if self.json:
                headers["Content-Type"] = "application/json"

            else:
                headers["Content-Type"] = "application/x-www-form-urlencoded"

        return (
            f"{self.method} {url}\n"
            f"headers={json.dumps(headers, indent=2)}\n"
            f"data={json.dumps(self.data, indent=2)}"
        )

@dataclass(frozen=True, slots=True)
class Response:
    status: int
    headers: dict[str, str]
    data: Any

    @property
    def status_text(self) -> str:
        return http_code_to_string(self.status)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def not_found(self) -> bool:
        return self.status == 404

    def __bool__(self):
        return self.ok

    def raise_for_status(self) -> Self:
        if not self.ok:
            raise RuntimeError(
                f"HTTP {self.status}: {self.data}"
            )

        return self

    def __str__(self) -> str:
        return (
            f"{self.status} {self.status_text}\n"
            f"headers={json.dumps(self.headers, indent=2)}\n"
            f"data={json.dumps(self.data, indent=2)}"
        )

