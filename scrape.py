from __future__ import annotations

import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

PAGE = "https://pm10torun.pl/jadlospis/"
OUT = Path("menu.json")
UA = "Mozilla/5.0 (compatible; PM10-menu-bot/1.0)"

MONTHS = {
    "styczen": 1,
    "luty": 2,
    "marzec": 3,
    "kwiecien": 4,
    "maj": 5,
    "czerwiec": 6,
    "lipiec": 7,
    "sierpien": 8,
    "wrzesien": 9,
    "pazdziernik": 10,
    "listopad": 11,
    "grudzien": 12,
}


def ascii_pl(text: str) -> str:
    return text.lower().translate(str.maketrans("ąćęłńóśźż", "acelnoszz"))


def parse_range(label: str):
    """Obsługuje m.in. 'jadłospis 31.08-11.09' oraz 'jadłospis 14-25 wrzesień'."""
    clean = ascii_pl(label)

    m = re.search(r"jadlospis\s+(\d{1,2})\.(\d{1,2})\s*[-–]\s*(\d{1,2})\.(\d{1,2})", clean, re.I)
    if m:
        d1, m1, d2, m2 = map(int, m.groups())
        return d1, m1, d2, m2

    month_names = "|".join(MONTHS)
    m = re.search(rf"jadlospis\s+(\d{{1,2}})\s*[-–]\s*(\d{{1,2}})\s+({month_names})", clean, re.I)
    if m:
        d1, d2 = map(int, m.groups()[:2])
        month = MONTHS[m.group(3).lower()]
        return d1, month, d2, month

    return None


def get_current_link() -> tuple[str, str]:
    r = requests.get(PAGE, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    candidates = []
    fallback_docs = []

    for index, a in enumerate(soup.find_all("a", href=True)):
        href = urljoin(PAGE, a["href"])
        label = " ".join(a.stripped_strings).strip()
        path = urlparse(href).path.lower()
        is_doc = path.endswith((".doc", ".docx"))

        parsed = parse_range(label)
        if parsed:
            candidates.append((href, label, parsed, index))
        elif is_doc and "jadlosp" in ascii_pl(label + " " + path):
            # Awaryjnie zachowujemy dokument związany z jadłospisem nawet,
            # jeśli strona ponownie zmieni sposób zapisu daty.
            fallback_docs.append((href, label or Path(path).name, index))

    if not candidates:
        if fallback_docs:
            href, label, _ = fallback_docs[-1]
            return href, label
        raise RuntimeError("Nie znaleziono linku do jadłospisu")

    today = datetime.now().date()
    dated = []
    for href, label, (d1, m1, d2, m2), index in candidates:
        year = today.year
        try:
            start = datetime(year, m1, d1).date()
            end_year = year + 1 if m2 < m1 else year
            end = datetime(end_year, m2, d2).date()
        except ValueError:
            continue
        dated.append((start, end, href, label, index))
        if start <= today <= end:
            return href, label

    if dated:
        # Jeśli jesteśmy między publikacjami, wybierz zakres o najpóźniejszej dacie początku.
        _, _, href, label, _ = max(dated, key=lambda item: (item[0], item[4]))
        return href, label

    if fallback_docs:
        href, label, _ = fallback_docs[-1]
        return href, label

    raise RuntimeError("Nie znaleziono prawidłowego linku do jadłospisu")


def doc_to_text(data: bytes, suffix: str) -> str:
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / ("menu" + suffix)
        src.write_bytes(data)
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
