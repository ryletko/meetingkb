from __future__ import annotations

import json
import time
from typing import Any

import requests


class OpenSearchError(RuntimeError):
    pass


class OpenSearchClient:
    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def available(self) -> bool:
        try:
            resp = requests.get(f"{self.url}/_cluster/health", timeout=2)
            return resp.ok
        except requests.RequestException:
            return False

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = requests.request(method, f"{self.url}{path}", timeout=60, **kwargs)
        if not resp.ok:
            raise OpenSearchError(f"{method} {path} failed: {resp.status_code} {resp.text}")
        if resp.content:
            return resp.json()
        return None

    def delete_index(self, index: str) -> None:
        resp = requests.delete(f"{self.url}/{index}", timeout=60)
        if resp.status_code == 404:
            return
        if not resp.ok:
            raise OpenSearchError(f"DELETE /{index} failed: {resp.status_code} {resp.text}")

    def create_index(self, index: str, body: dict[str, Any]) -> None:
        self.request("PUT", f"/{index}", json=body)

    def update_cluster_settings(self, body: dict[str, Any]) -> None:
        self.request("PUT", "/_cluster/settings", json=body)

    def bulk_index(self, index: str, docs: list[dict[str, Any]], chunk_size: int = 500) -> None:
        if not docs:
            return
        headers = {"Content-Type": "application/x-ndjson"}
        for start in range(0, len(docs), chunk_size):
            lines = []
            for doc in docs[start : start + chunk_size]:
                doc_id = doc["id"]
                lines.append(json.dumps({"index": {"_index": index, "_id": doc_id}}, ensure_ascii=False))  # noqa: E501
                lines.append(json.dumps(doc, ensure_ascii=False))
            data = "\n".join(lines) + "\n"
            result = self.request("POST", "/_bulk?refresh=wait_for", data=data.encode("utf-8"), headers=headers)  # noqa: E501
            if result.get("errors"):
                errors = [item for item in result.get("items", []) if item.get("index", {}).get("error")]  # noqa: E501
                raise OpenSearchError(f"Bulk indexing failed: {errors[:3]}")

    def search(self, index: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", f"/{index}/_search", json=body)

    def wait_available(self, timeout_sec: int = 120) -> bool:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            if self.available():
                return True
            time.sleep(2)
        return False
