#!/usr/bin/env python3
"""
Async web-content discovery tool.

High-level flow:
1. Load a wordlist of paths (e.g. admin, api).
2. Replace the keyword "FILL" in the user-supplied URL with each path.
3. Optionally append extensions (.php, .json, etc.).
4. Fire **concurrent** HTTP(S) requests until all candidates are tested.
5. Persist hits (status codes you care about) as JSON + plain text.

Usage:
    python web_content_discovery.py https://example.com/FILL -w webcontent.txt
"""

# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List, Tuple          # noqa: UP035 (Python 3.9+ still accepts List)
from urllib.parse import urlparse

import aiohttp                        # Asynchronous HTTP client
from colorama import init, Fore       # Cross-platform coloured terminal
from tqdm.asyncio import tqdm         # Progress bar for asyncio

# -----------------------------------------------------------------------------
# Colourama – initialise once, then use aliases for brevity
# -----------------------------------------------------------------------------
init(autoreset=True)
GREEN, YELLOW, RESET = Fore.GREEN, Fore.YELLOW, Fore.RESET


# -----------------------------------------------------------------------------
# Core Scanner Class
# -----------------------------------------------------------------------------
class WebContentDiscovery:
    """
    Discover hidden files and directories by brute-forcing paths.

    Lifecycle
    ---------
    1. __init__ : store user options
    2. _load_words : read wordlist into memory
    3. _generate_urls : build final list of candidate URLs
    4. run : perform async HTTP requests
    5. save_reports : write hits to disk
    """

    def __init__(
        self,
        base_url: str,
        wordlist: Path,
        extensions: List[str] = None,
        concurrency: int = 20,
        timeout: int = 5,
        follow_redirects: bool = False,
        verify_ssl: bool = False,
        output_dir: Path = Path("reports"),
        status_codes: List[int] = None,
    ):
        """
        Parameters
        ----------
        base_url : str
            Must contain the literal string **"FILL"** which will be replaced
            by every word in the wordlist.  Example: `https://site.com/FILL`
        wordlist : Path
            Plain-text file with one candidate path per line.
        extensions : List[str]
            Extra suffixes to append after each path.  Example: [".php", ".bak"]
        concurrency : int
            Max simultaneous HTTP requests (semaphore size).
        timeout : int
            Per-request socket timeout in seconds.
        follow_redirects : bool
            Follow HTTP 3xx redirects automatically.
        verify_ssl : bool
            Enforce valid TLS certificates (default False to reduce friction).
        output_dir : Path
            Folder where JSON and TXT reports will be written.
        status_codes : List[int]
            Which HTTP status codes are considered a "hit".
            Defaults to [200] if omitted.
        """
        self.base_url = base_url
        self.wordlist = wordlist
        self.extensions = extensions or []            # Ensure list, not None
        self.concurrency = concurrency
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.follow_redirects = follow_redirects
        self.verify_ssl = verify_ssl
        self.output_dir = output_dir
        self.status_codes = set(status_codes or [200])  # De-duplicate

        # Minimal headers to avoid 403s from default Python UA
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/114.0 Safari/537.36"
            )
        }

    # ------------------------------------------------------------------
    # Internal: load wordlist into memory
    # ------------------------------------------------------------------
    def _load_words(self) -> List[str]:
        """
        Read the wordlist file and return a list of non-empty lines.

        Exits the program gracefully if the file is missing.
        """
        try:
            lines = self.wordlist.read_text(encoding="utf-8").splitlines()
            return [ln.strip() for ln in lines if ln.strip()]
        except FileNotFoundError:
            print(f"[ERROR] Wordlist not found: {self.wordlist}", file=sys.stderr)
            sys.exit(1)

    # ------------------------------------------------------------------
    # Internal: build every URL that will actually be requested
    # ------------------------------------------------------------------
    def _generate_urls(self, words: List[str]) -> List[str]:
        """
        Replace "FILL" with each word, then append extensions.

        Examples
        --------
        base_url = "https://site.com/FILL"
        word = "admin"
        extensions = [".php", ".bak"]
            -> ["https://site.com/admin",
                "https://site.com/admin.php",
                "https://site.com/admin.bak"]
        """
        urls = []
        for w in words:
            base = self.base_url.replace("FILL", w)
            urls.append(base)
            for ext in self.extensions:
                urls.append(f"{base}{ext}")
        return urls

    # ------------------------------------------------------------------
    # Async worker: perform one HTTP request
    # ------------------------------------------------------------------
    async def _fetch(
        self,
        session: aiohttp.ClientSession,
        url: str,
        semaphore: asyncio.Semaphore,
    ) -> Tuple[str, int]:
        """
        Fetch a single URL under the global concurrency limit.

        Returns
        -------
        (url, status_code)
        status_code = 0 for any network/timeout/SSL error.
        """
        async with semaphore:               # Respect max concurrency
            try:
                async with session.get(
                    url,
                    allow_redirects=self.follow_redirects,
                    timeout=self.timeout,
                    ssl=self.verify_ssl,
                ) as resp:
                    return url, resp.status
            except Exception:
                # Swallow all exceptions -> status 0
                return url, 0

    # ------------------------------------------------------------------
    # Main entry-point for async execution
    # ------------------------------------------------------------------
    async def run(self) -> List[Tuple[str, int]]:
        """
        Orchestrate the entire scan.

        Steps
        -----
        1. Build wordlist & URL list
        2. Create aiohttp session with proper connector limits
        3. Dispatch all tasks with tqdm progress bar
        4. Filter results by status_codes
        5. Return list of (url, status) tuples that matched

        Caller must run inside `asyncio.run()` or an event loop.
        """
        words = self._load_words()
        urls = self._generate_urls(words)
        print(f"{YELLOW}[INFO]{RESET} Target: {self.base_url}")
        print(f"{YELLOW}[INFO]{RESET} Generated {len(urls)} URLs")

        # Concurrency guards
        semaphore = asyncio.Semaphore(self.concurrency)
        connector = aiohttp.TCPConnector(
            limit_per_host=self.concurrency, ssl=self.verify_ssl
        )

        # Re-use a single session for efficiency
        async with aiohttp.ClientSession(
            headers=self.headers, connector=connector
        ) as session:
            tasks = [self._fetch(session, url, semaphore) for url in urls]
            results = await tqdm.gather(*tasks, desc="Scanning", unit="req")

        # Keep only the hits
        return [res for res in results if res[1] in self.status_codes]

    # ------------------------------------------------------------------
    # Persist results to disk
    # ------------------------------------------------------------------
    def save_reports(self, hits: List[Tuple[str, int]]):
        """
        Save two artefacts:

        1. `{host}.txt` – newline-separated URLs
        2. `{host}.json` – structured JSON array

        The directory is created automatically if missing.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        host = urlparse(self.base_url).netloc or "scan"  # fallback name
        txt_path = self.output_dir / f"{host}.txt"
        json_path = self.output_dir / f"{host}.json"

        # Plain text
        txt_path.write_text("\n".join(url for url, _ in hits) + "\n")

        # Pretty JSON
        json_path.write_text(
            json.dumps(
                [{"url": url, "status": st} for url, st in hits],
                indent=2,
            )
        )

        print(f"{GREEN}[DONE]{RESET} Reports saved → {txt_path}   {json_path}")


# -----------------------------------------------------------------------------
# CLI Argument Parsing
# -----------------------------------------------------------------------------
def parse_cli():
    """
    Build an argparse CLI interface with sensible defaults.
    """
    parser = argparse.ArgumentParser(description="Async web-content discovery")
    parser.add_argument(
        "url",
        help='Base URL containing the keyword "FILL", e.g. https://site.com/FILL',
    )
    parser.add_argument(
        "-w",
        "--wordlist",
        required=True,
        type=Path,
        help="Path to wordlist with one path per line",
    )
    parser.add_argument(
        "-e",
        "--ext",
        action="append",
        default=[],
        help="File extensions to append (repeatable: -e .php -e .bak)",
    )
    parser.add_argument(
        "-t",
        "--threads",
        type=int,
        default=20,
        help="Max concurrent requests (default: 20)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="HTTP timeout in seconds (default: 5)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("reports"),
        help="Directory to save reports (default: ./reports)",
    )
    parser.add_argument(
        "-s",
        "--status",
        action="append",
        type=int,
        help="Acceptable status codes (repeatable: -s 200 -s 302)",
    )
    parser.add_argument(
        "--follow-redirects",
        action="store_true",
        help="Follow HTTP 3xx redirects",
    )
    parser.add_argument(
        "--verify-ssl",
        action="store_true",
        help="Verify SSL certificates (default: ignore)",
    )
    return parser.parse_args()


# -----------------------------------------------------------------------------
# Entry-point guard
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse  # Imported here to avoid circular issues if reused as lib

    args = parse_cli()

    scanner = WebContentDiscovery(
        base_url=args.url,
        wordlist=args.wordlist,
        extensions=args.ext,
        concurrency=args.threads,
        timeout=args.timeout,
        follow_redirects=args.follow_redirects,
        verify_ssl=args.verify_ssl,
        output_dir=args.output,
        status_codes=args.status or [200],  # Default to 200 if nothing given
    )

    try:
        hits = asyncio.run(scanner.run())
        scanner.save_reports(hits)
        print(f"{GREEN}[SUMMARY]{RESET} {len(hits)} hits found")
    except KeyboardInterrupt:
        print("\n[!] Aborted by user")
