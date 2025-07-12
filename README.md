
# 🕵️ Web Content Discovery (Async)

A lightweight, **fully asynchronous** brute-force scanner for discovering hidden
files and directories on web servers.

> ⚠️ **Ethics & Legal**  
> Only use this tool against **targets you own or have explicit written permission to test**.  
> Unauthorized brute-forcing is illegal in most jurisdictions.

---

## ✨ Highlights

* **Ultra-fast**: Uses `asyncio` + `aiohttp` for thousands of requests per minute.
* **Wildcard-safe**: Accept only the status codes you care about (`200`, `204`, `302`, etc.).
* **Flexible URL scheme**: Replace the literal `FILL` keyword anywhere in the URL.
* **Extension fuzzing**: Add `.php`, `.bak`, `.json`, … in a single run.
* **Pretty output**: Coloured terminal feedback and progress bars.
* **Dual exports**: Human-readable `.txt` + machine-friendly `.json`.

---

## 🚀 Quick Start

### 1. Install dependencies

```bash
pip install aiohttp tqdm colorama
````

### 2. Run the scan

```bash
python web_content_discovery.py https://example.com/FILL -w paths.txt -e .php -e .bak
```

---

## 🧰 CLI Reference

| Flag                 | Default     | Description                                                    |
| :------------------- | :---------- | :------------------------------------------------------------- |
| `url` (positional)   | —           | Base URL with `FILL` placeholder, e.g. `https://site.com/FILL` |
| `-w`, `--wordlist`   | —           | Path to wordlist (required)                                    |
| `-e`, `--ext`        | —           | Extension(s) to append (repeatable)                            |
| `-t`, `--threads`    | `20`        | Max concurrent requests                                        |
| `--timeout`          | `5`         | Socket timeout (seconds)                                       |
| `-s`, `--status`     | `[200]`     | Acceptable status codes (repeatable)                           |
| `--follow-redirects` | _disabled_  | Follow 3xx redirects                                           |
| `--verify-ssl`       | _disabled_  | Validate TLS certificates                                      |
| `-o`, `--output`     | `./reports` | Directory for generated reports                                |

---

## 🎯 Examples

### Basic directory discovery

```bash
python web_content_discovery.py https://site.com/FILL -w dirs.txt
```

### File fuzzing with extensions

```bash
python web_content_discovery.py https://site.com/FILL -w files.txt \
  -e .php -e .html -e .txt \
  -s 200 -s 302
```

### High-speed scan (careful!)

```bash
python web_content_discovery.py https://site.com/FILL \
  -w raft-small-files.txt \
  -t 100 --timeout 3
```

---

## 📂 Output

After each run you’ll get:

- `reports/<hostname>.txt` – plain list of discovered URLs
    
- `reports/<hostname>.json` – structured array:
    
    ```json
    [
      {"url": "https://site.com/admin", "status": 200},
      {"url": "https://site.com/backup.zip", "status": 403}
    ]
    ```
    
---

# 🛡️ Legal Disclaimer
This tool is intended for educational purposes and for testing on domains you own or have explicit permission to test. Unauthorized use against third-party domains may be illegal.
