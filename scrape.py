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
    "styczen": 1, "luty": 2, "marzec": 3, "kwiecien": 4,
    "maj": 5, "czerwiec": 6, "lipiec": 7, "sierpien": 8,
    "wrzesien": 9, "pazdziernik": 10, "listopad": 11, "grudzien": 12,
}
WEEKDAYS = {
    0: "poniedziałek", 1: "wtorek", 2: "środa", 3: "czwartek",
    4: "piątek", 5: "sobota", 6: "niedziela",
}


def ascii_pl(text: str) -> str:
    return text.lower().translate(str.maketrans("ąćęłńóśźż", "acelnoszz"))


def parse_range(label: str):
    clean = ascii_pl(label)
    m = re.search(r"jadlospis\s+(\d{1,2})\.(\d{1,2})\s*[-–]\s*(\d{1,2})\.(\d{1,2})", clean, re.I)
    if m:
        return tuple(map(int, m.groups()))
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
    candidates, fallback_docs = [], []
    for index, a in enumerate(soup.find_all("a", href=True)):
        href = urljoin(PAGE, a["href"])
        label = " ".join(a.stripped_strings).strip()
        path = urlparse(href).path.lower()
        parsed = parse_range(label)
        if parsed:
            candidates.append((href, label, parsed, index))
        elif path.endswith((".doc", ".docx")) and "jadlosp" in ascii_pl(label + " " + path):
            fallback_docs.append((href, label or Path(path).name, index))
    if not candidates:
        if fallback_docs:
            href, label, _ = fallback_docs[-1]
            return href, label
        raise RuntimeError("Nie znaleziono linku do jadłospisu")
    today = datetime.now().date()
    dated = []
    for href, label, (d1, m1, d2, m2), index in candidates:
        try:
            start = datetime(today.year, m1, d1).date()
            end = datetime(today.year + (m2 < m1), m2, d2).date()
        except ValueError:
            continue
        dated.append((start, end, href, label, index))
        if start <= today <= end:
            return href, label
    if dated:
        _, _, href, label, _ = max(dated, key=lambda x: (x[0], x[4]))
        return href, label
    if fallback_docs:
        href, label, _ = fallback_docs[-1]
        return href, label
    raise RuntimeError("Nie znaleziono prawidłowego linku do jadłospisu")


def doc_to_html(data: bytes, suffix: str) -> str:
    """Konwertuje Worda do HTML, dzięki czemu zachowujemy prawdziwe komórki tabeli."""
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / ("menu" + suffix)
        src.write_bytes(data)
        subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "html:HTML", "--outdir", td, str(src)],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        html_files = list(Path(td).glob("*.html")) + list(Path(td).glob("*.htm"))
        if not html_files:
            raise RuntimeError("LibreOffice nie utworzył pliku HTML")
        return html_files[0].read_text(encoding="utf-8", errors="replace")


def clean_cell(cell) -> str:
    # Separator spacji między akapitami/wierszami wewnątrz tej samej komórki.
    text = cell.get_text(" ", strip=True).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value: str):
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b", value)
    if not m:
        return None
    d, mo, y = map(int, m.groups())
    if y < 100:
        y += 2000
    try:
        return datetime(y, mo, d).date()
    except ValueError:
        return None


def parse_menu(html: str) -> dict[str, dict[str, str]]:
    """Czyta wiersze tabeli Worda: DATA | I ŚNIADANIE | II ŚNIADANIE | OBIAD."""
    soup = BeautifulSoup(html, "html.parser")
    days = {}

    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 4:
            continue
        values = [clean_cell(c) for c in cells]
        date = parse_date(values[0])
        if not date:
            continue

        breakfast_1, breakfast_2 = values[1], values[2]
        lunch = " ".join(v for v in values[3:] if v).strip()
        if not breakfast_1 or not breakfast_2 or not lunch:
            raise RuntimeError(
                f"Niepełny jadłospis dla {date.isoformat()}: "
                f"I={breakfast_1!r}, II={breakfast_2!r}, obiad={lunch!r}"
            )

        days[date.isoformat()] = {
            "day": WEEKDAYS[date.weekday()],
            "breakfast_1": breakfast_1,
            "breakfast_2": breakfast_2,
            "lunch": lunch,
        }

    if not days:
        raise RuntimeError("Nie udało się odczytać wierszy jadłospisu z tabeli")
    return days


def main() -> None:
    url, label = get_current_link()
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    suffix = ".docx" if url.lower().split("?")[0].endswith(".docx") else ".doc"
    html = doc_to_html(r.content, suffix)
    menu = parse_menu(html)
    payload = {
        "source_page": PAGE,
        "source_document": url,
        "label": label,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "menu": menu,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Zapisano {OUT}: {label}, {len(menu)} dni")


if __name__ == "__main__":
    main()
