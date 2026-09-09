from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PAGE = "https://pm10torun.pl/jadlospis/"
OUT = Path("menu.json")
UA = "Mozilla/5.0 (compatible; PM10-menu-bot/1.0)"


def get_current_link() -> tuple[str, str]:
    r = requests.get(PAGE, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    candidates = []
    for a in soup.find_all("a", href=True):
        label = " ".join(a.stripped_strings)
        m = re.search(r"jadłospis\s+(\d{1,2})\.(\d{1,2})\s*[-–]\s*(\d{1,2})\.(\d{1,2})", label, re.I)
        if m:
            candidates.append((a["href"], label, m.groups()))
    if not candidates:
        raise RuntimeError("Nie znaleziono linku do jadłospisu")

    today = datetime.now().date()
    for href, label, g in candidates:
        d1, m1, d2, m2 = map(int, g)
        year = today.year
        start = datetime(year, m1, d1).date()
        end_year = year + 1 if m2 < m1 else year
        end = datetime(end_year, m2, d2).date()
        if start <= today <= end:
            return urljoin(PAGE, href), label
    # Gdy uruchomienie wypada między publikacjami, zachowaj najnowszy link ze strony.
    href, label, _ = candidates[0]
    return urljoin(PAGE, href), label


def doc_to_text(data: bytes, suffix: str) -> str:
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / ("menu" + suffix)
        src.write_bytes(data)
        # LibreOffice dobrze radzi sobie ze starym binarnym .doc i nowszym .docx.
        subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "txt:Text", "--outdir", td, str(src)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        txt = Path(td) / "menu.txt"
        if not txt.exists():
            raise RuntimeError("LibreOffice nie utworzył pliku tekstowego")
        return txt.read_text(encoding="utf-8", errors="replace")


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def main() -> None:
    url, label = get_current_link()
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    suffix = ".docx" if url.lower().split("?")[0].endswith(".docx") else ".doc"
    text = normalize(doc_to_text(r.content, suffix))
    payload = {
        "source_page": PAGE,
        "source_document": url,
        "label": label,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "text": text,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Zapisano {OUT}: {label}, {len(text)} znaków")


if __name__ == "__main__":
    main()
