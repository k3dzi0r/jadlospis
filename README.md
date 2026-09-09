# Jadłospis PM10 Toruń

Automatyczny pośrednik dla jadłospisu Przedszkola Miejskiego nr 10 w Toruniu.

Workflow w dni robocze pobiera aktualny plik `.doc`/`.docx` ze strony przedszkola, konwertuje go przez LibreOffice do tekstu i zapisuje wynik w `menu.json`.

## Dane

Po pierwszym udanym uruchomieniu workflow wynik będzie dostępny jako:

`https://raw.githubusercontent.com/k3dzi0r/jadlospis/main/menu.json`

Workflow można też uruchomić ręcznie z zakładki **Actions → Aktualizuj jadlospis PM10 → Run workflow**.
