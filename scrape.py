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
            end_year = today.year + 1 if m2 < m1 else today.year
            end = datetime(end_year, m2, d2).date()
        except ValueError:
            continue
        dated.append((start, end, href, label, index))
        if start <= today <= end:
            return href, label

    if dated:
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
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        txt = Path(td) / "menu.txt"
        if not txt.exists():
            raise RuntimeError("LibreOffice nie utworzył pliku tekstowego")
        return txt.read_text(encoding="utf-8", errors="replace")


def normalize(text: str) -> str:
    text = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_meal(text: str) -> str:
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,\n")
    return text


def parse_menu(text: str) -> dict[str, dict[str, str]]:
    """Rozbija tabelę LibreOffice na dni i trzy posiłki."""
    # Każdy dzień zaczyna się od daty dd.mm.yy lub dd.mm.yyyy.
    date_re = re.compile(r"(?m)^(\d{1,2})\.(\d{1,2})\.(\d{2,4})\s*$")
    matches = list(date_re.finditer(text))
    days = {}

    for i, match in enumerate(matches):
        d, m, y = map(int, match.groups())
        if y < 100:
            y += 2000
        date = datetime(y, m, d).date()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[match.end():end].strip()

        # Pierwsza linia po dacie to skrót/nazwa dnia tygodnia.
        lines = block.splitlines()
        if lines and ascii_pl(lines[0]).rstrip(".") in {
            "poniedz", "poniedzialek", "wtorek", "sroda", "czwartek", "piatek", "sobota", "niedziela"
        }:
            block = "\n".join(lines[1:]).strip()

        # Eksport tabeli z LibreOffice zachowuje komórki jako akapity rozdzielone pustą linią.
        cells = [clean_meal(x) for x in re.split(r"\n\s*\n", block) if clean_meal(x)]
        if len(cells) < 3:
            raise RuntimeError(f"Nie udało się rozpoznać 3 posiłków dla {date.isoformat()}: {cells}")

        # Gdy wewnątrz komórki pojawią się dodatkowe puste akapity, wszystko od trzeciej
        # części należy już do obiadu.
        breakfast_1 = cells[0]
        breakfast_2 = cells[1]
        lunch = " ".join(cells[2:])

        days[date.isoformat()] = {
            "day": WEEKDAYS[date.weekday()],
            "breakfast_1": breakfast_1,
            "breakfast_2": breakfast_2,
            "lunch": lunch,
        }

    if not days:
        raise RuntimeError("Nie udało się znaleźć żadnych dni w jadłospisie")
    return days


def main() -> None:
    url, label = get_current_link()
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    suffix = ".docx" if url.lower().split("?")[0].endswith(".docx") else ".doc"
    text = normalize(doc_to_text(r.content, suffix))
    menu = parse_menu(text)
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
