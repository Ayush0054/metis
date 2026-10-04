"""Shared standard-library HTTP transport for workflow integrations."""

import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing {name}. Configure it before running Metis.")
    return value


class APIError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"API request failed with HTTP {status}.")


def request_json(url, token, method="GET", payload=None, retry=False):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "metis",
    }
    for attempt in range(3):
        try:
            request = Request(url, data=data, headers=headers, method=method)
            with urlopen(request, timeout=30) as response:
                if response.status == 204:
                    return None
                return json.load(response)
        except HTTPError as error:
            # Never log response bodies, credentials, or user-controlled text.
            if retry and error.code in {429, 500, 502, 503, 504, 529} and attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            raise APIError(error.code) from None
        except (URLError, TimeoutError):
            if retry and attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            raise RuntimeError("API request failed or timed out.") from None
