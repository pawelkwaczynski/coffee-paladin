# Branding — pochodzenie plików

## Paladyn (maskotka projektu)

| Plik | Co to jest | Skąd |
|---|---|---|
| `paladin.png` | oficjalna grafika statyczna, 1024×1536 | **projekt własny autora** |
| `paladin.gif` | oficjalna animacja, 20 klatek, 768×1152, przezroczyste tło | **projekt własny autora** |
| `paladin_welcome.gif` | animacja przeskalowana do okna powitalnego (352×480) | pochodna `paladin.gif` |
| `paladin_welcome.png` | klatka statyczna jako fallback | pochodna `paladin.gif` |

Grafika paladyna to **projekt własny autora projektu** i jest używana jako
oficjalna maskotka `coffee-paladin`.
Wersje pochodne (skalowanie, kadrowanie, konwersja na półbloki ANSI w CLI) powstały
z tych dwóch plików źródłowych — nie ma innego źródła grafiki postaci.

Sztuka terminalowa (`heat --paladin`) to ta sama grafika
przekonwertowana automatycznie na znaki: wersja kolorowa używa półbloków `▀`/`▄`
w 24-bitowym kolorze, wersja zapasowa — cieniowania `░▒▓█` dla terminali bez truecolor.

## Ikona aplikacji (tarcza z ziarnem kawy)

| Plik | Co to jest | Skąd |
|---|---|---|
| `app_icon.png` | ikona aplikacji, tarcza z ziarnem kawy | **projekt własny autora**, przycięta do widocznej treści |

Ikona jest **osobna od maskotki** i to jest celowe. Portret paladyna wygląda dobrze
w oknie powitalnym i w README, ale w rozmiarze 16 px — a tyle ma ikona w Finderze
i w Spotlight — zamienia się w plamę. Zmierzone: pełna grafika z ciemną płytką daje
w 16 px ciemny kafelek z drobną złotą plamką; sama tarcza jest w tym rozmiarze czytelna.
Tarcza wypełnia cały kadr, dzięki czemu jest czytelna także w 16 px i nie potrzebuje
osobnej wersji uproszczonej — zmierzone: wariant z płomieniami i bez nich są w tym
rozmiarze nie do odróżnienia. `tools/zrob_ikone.sh` nadal przyjmuje opcjonalną grafikę
dla małych rozmiarów, gdyby kiedyś okazała się potrzebna.

Maskotka (`paladin.png`, `paladin.gif`) **zostaje** tam, gdzie ma miejsce i sens:
w README, w oknie powitalnym i w sztuce terminalowej.

## Logotypy

| Plik | Co to jest |
|---|---|
| `logo.png` | do 3.2.7 logotyp koła naukowego AIrON w nagłówku menu; od 3.3.0 nie jest już częścią wydania (plik zostaje w tagu `v3.2.7`) |
| `logo_footer.png`, `logo_footer_dark.png` | FOCUS FRAME (stopka menu) |

Logotypy należą do swoich właścicieli i są użyte za zgodą.
