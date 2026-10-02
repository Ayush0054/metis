"""GitHub API service shared by workflows; no PR code is executed."""

import os
from urllib.parse import quote

from ._http import request_json, required_env


class GitHub:
    def __init__(self, repository, *, token=None, dry_run=False):
        parts = repository.split("/")
        if len(parts) != 2 or any(not part for part in parts):
            raise ValueError("Repository must be owner/name.")
        self.path = "/repos/" + "/".join(quote(part, safe="") for part in parts)
        self.token = token
        self.dry_run = dry_run

    def request(self, path="", *, method="GET", payload=None):
        if self.dry_run and method != "GET":
            return {"dry_run": True}
        base = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
        return request_json(base + self.path + path,
                            self.token if self.token is not None else required_env("GITHUB_TOKEN"),
                            method=method, payload=payload, retry=method == "GET")

    def pages(self, path, *, max_items=None):
        result = []
        page = 1
        while True:
            items = self.request(f"{path}?per_page=100&page={page}")
            if not isinstance(items, list):
                raise ValueError("Expected a GitHub API list.")
            result.extend(items)
            if max_items is not None and len(result) > max_items:
                raise ValueError("GitHub data exceeds the configured item budget.")
            if len(items) < 100:
                return result
            page += 1
