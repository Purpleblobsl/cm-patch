import json
from dataclasses import dataclass
from typing import (
    Any,
    Literal,
    Self,
)
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest
from urllib.request import urlopen
from http import HTTPStatus

from .utils import logger_get

log = logger_get(__name__)

type Method = Literal["GET"]|Literal["POST"]

@dataclass(frozen=True, slots=True)
class Request:
    method: Method
    url: str
    headers: dict[str, str] | None = None
    params: dict[str, Any] | None = None
    data: dict[str, Any] | None = None
    json: bool = True

    def fetch(self) -> Response:
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
                    data=json.loads(response.read()),
                )

        except HTTPError as e:
            raw = e.read()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = raw.decode(errors="replace")

            response = Response(
                status=e.code,
                headers=dict(e.headers),
                data=data,
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
        return HTTPStatus(self.status).phrase

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

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

