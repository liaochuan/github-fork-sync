import time

import httpx

GITHUB_API = "https://api.github.com"


class GitHubClient:
    def __init__(
        self, token: str, timeout: float = 60.0, proxy: str | None = None
    ):
        kwargs: dict = {
            "base_url": GITHUB_API,
            "headers": {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            "timeout": timeout,
        }
        if proxy:
            kwargs["proxy"] = proxy
        self._client = httpx.Client(**kwargs)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        retries: int = 3,
    ) -> httpx.Response:
        last_exc = None
        for attempt in range(retries):
            try:
                resp = self._client.request(
                    method, path, params=params, json=json
                )
                resp.raise_for_status()
                return resp
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                last_exc = e
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                continue
        raise last_exc

    def get(self, path: str, *, params: dict | None = None) -> dict | list:
        return self._request("GET", path, params=params).json()

    def post(self, path: str, *, json: dict | None = None) -> dict:
        return self._request("POST", path, json=json).json()

    def get_all(
        self, path: str, *, params: dict | None = None
    ) -> list:
        if params is None:
            params = {}
        all_items: list = []
        url = path
        while url:
            resp = self._request("GET", url, params=params)
            all_items.extend(resp.json())
            link = resp.headers.get("Link", "")
            url = _parse_next_link(link)
            params = None
        return all_items

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _parse_next_link(link_header: str) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' in part:
            url = part.split(";")[0].strip().strip("<>")
            return url
    return None
