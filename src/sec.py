"""Minimal, well-behaved SEC EDGAR HTTP client."""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup


EDGAR_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
DEFAULT_USER_AGENT = "research-agent contact@example.com"


@dataclass
class FetchedDocument:
    url: str
    content_type: str
    body: bytes
    filename: str


class SECClient:
    """Fetch SEC pages with deterministic throttling and conservative retries."""

    def __init__(
        self,
        user_agent: str | None = None,
        min_interval: float = 0.25,
        timeout: float = 120.0,
        max_retries: int = 4,
    ) -> None:
        self.user_agent = user_agent or os.environ.get("SEC_USER_AGENT") or DEFAULT_USER_AGENT
        self.min_interval = min_interval
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_request = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def get(self, url: str) -> tuple[bytes, str]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    self._last_request = time.monotonic()
                    body = resp.read()
                    content_type = resp.headers.get("Content-Type", "")
                    return body, content_type
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code in {400, 404}:
                    raise
                if exc.code in {403, 429, 500, 502, 503, 504}:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
                continue
        raise RuntimeError(f"failed to fetch {url}: {last_error}") from last_error

    def filing_index_url(self, cik: str, accession: str) -> str:
        return f"{EDGAR_ARCHIVES}/{cik}/{accession.replace('-', '')}/{accession}-index.html"

    def _absolute_document_url(self, cik: str, accession: str, href: str) -> str:
        if href.startswith("/ix?doc="):
            query = urllib.parse.urlparse(href).query
            doc_path = urllib.parse.parse_qs(query).get("doc", [""])[0]
            return "https://www.sec.gov" + doc_path
        if href.startswith("http"):
            return href
        if href.startswith("/"):
            return "https://www.sec.gov" + href
        return f"{EDGAR_ARCHIVES}/{cik}/{accession.replace('-', '')}/{href}"

    def discover(self, source: dict[str, Any]) -> tuple[dict[str, str], str, str]:
        """Discover filing metadata and the target document URL from the index page."""
        cik = source["cik"]
        accession = source["accession"]
        form = source["form"]
        exhibit = source.get("exhibit_number") or ""

        index_url = self.filing_index_url(cik, accession)
        index_html, _ = self.get(index_url)
        soup = BeautifulSoup(index_html, "lxml")

        metadata: dict[str, str] = {}
        heads = soup.select(".infoHead")
        infos = soup.select(".info")
        for head, info in zip(heads, infos):
            key = " ".join(head.get_text(" ", strip=True).split())
            value = " ".join(info.get_text(" ", strip=True).split())
            if key:
                metadata[key] = value

        filing_date = metadata.get("Filing Date", "")
        period_of_report = metadata.get("Period of Report", "")

        target_type = "EX-99.1" if form == "8-K" else form
        document_name = ""
        document_href: str | None = None
        for row in soup.select("table.tableFile tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 4:
                continue
            row_type = " ".join(cells[3].get_text(" ", strip=True).split())
            if row_type.upper() == target_type.upper():
                link = row.find("a")
                if link is None:
                    continue
                document_href = link.get("href")
                document_name = " ".join(link.get_text(" ", strip=True).split())
                break

        if not document_href:
            # Some 8-K indexes render the exhibit type with whitespace or a
            # different casing; fall back to a case-insensitive contains match.
            for row in soup.select("table.tableFile tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) < 4:
                    continue
                row_type = " ".join(cells[3].get_text(" ", strip=True).split())
                if target_type.lower() in row_type.lower():
                    link = row.find("a")
                    if link is None:
                        continue
                    document_href = link.get("href")
                    document_name = " ".join(link.get_text(" ", strip=True).split())
                    break

        if not document_href:
            raise RuntimeError(
                f"could not discover {target_type} document for {accession}"
            )

        document_url = self._absolute_document_url(cik, accession, document_href)
        return (
            {
                "filing_date": filing_date,
                "period_of_report": period_of_report,
                "document_name": document_name,
            },
            document_url,
            document_name,
        )

    def fetch_document(self, url: str) -> FetchedDocument:
        body, content_type = self.get(url)
        path = urllib.parse.urlparse(url).path
        filename = os.path.basename(path) or "document"
        return FetchedDocument(
            url=url,
            content_type=content_type,
            body=body,
            filename=filename,
        )

