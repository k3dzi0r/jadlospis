# Jadłospis PM10 Toruń

Automatyczny pośrednik i prosta strona z jadłospisem Przedszkola Miejskiego nr 10 w Toruniu.

Workflow w dni robocze pobiera aktualny plik `.doc`/`.docx` ze strony przedszkola, konwertuje go przez LibreOffice do tekstu i zapisuje wynik w `menu.json`.

## Strona

Po włączeniu GitHub Pages strona jest dostępna pod adresem:

`https://k3dzi0r.github.io/jadlospis/`

Widok automatycznie:
- pokazuje jadłospis na dziś,
- pokazuje następny dostępny dzień przedszkolny (np. w piątek od razu poniedziałek),
- pozwala rozwinąć cały aktualny jadłospis,
- korzysta z polskiej strefy czasowej `Europe/Warsaw`,
- pokazuje datę ostatniej aktualizacji danych.

GitHub Pages należy ustawić na publikowanie z gałęzi `main`, katalog `/ (root)`.

## Dane

Surowe dane są dostępne jako:

`https://raw.githubusercontent.com/k3dzi0r/jadlospis/main/menu.json`

Workflow można też uruchomić ręcznie z zakładki **Actions → Aktualizuj jadlospis PM10 → Run workflow**.
