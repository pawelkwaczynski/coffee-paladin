# Branding — pochodzenie plików

## Paladyn (maskotka projektu)

| Plik | Co to jest | Skąd |
|---|---|---|
| `paladin.png` | oficjalna grafika statyczna, 1024×1536 | **wygenerowana w ChatGPT (OpenAI)** |
| `paladin.gif` | oficjalna animacja, 20 klatek, 768×1152, przezroczyste tło | **wygenerowana w ChatGPT (OpenAI)** |
| `paladin_welcome.gif` | animacja przeskalowana do okna powitalnego (352×480) | pochodna `paladin.gif` |
| `paladin_welcome.png` | klatka statyczna jako fallback | pochodna `paladin.gif` |

Grafika paladyna została **wygenerowana narzędziem ChatGPT (OpenAI)** na zamówienie
autora projektu i jest używana jako oficjalna maskotka `coffee-paladin`.
Wersje pochodne (skalowanie, kadrowanie, konwersja na półbloki ANSI w CLI) powstały
z tych dwóch plików źródłowych — nie ma innego źródła grafiki postaci.

Sztuka terminalowa (`heat --paladin`) to ta sama grafika
przekonwertowana automatycznie na znaki: wersja kolorowa używa półbloków `▀`/`▄`
w 24-bitowym kolorze, wersja zapasowa — cieniowania `░▒▓█` dla terminali bez truecolor.

## Ikona aplikacji (tarcza z ziarnem kawy)

| Plik | Co to jest | Skąd |
|---|---|---|
| `app_icon.png` | ikona aplikacji, 1024×1024 | **wygenerowana w ChatGPT (OpenAI)** na zamówienie autora |
| `app_icon_small.png` | ta sama tarcza bez ciemnej płytki, dla 16 i 32 px | kadr z `app_icon.png` |

Ikona jest **osobna od maskotki** i to jest celowe. Portret paladyna wygląda dobrze
w oknie powitalnym i w README, ale w rozmiarze 16 px — a tyle ma ikona w Finderze
i w Spotlight — zamienia się w plamę. Zmierzone: pełna grafika z ciemną płytką daje
w 16 px ciemny kafelek z drobną złotą plamką; sama tarcza jest w tym rozmiarze czytelna.
Dlatego `.icns` niesie **dwie różne warstwy**: bogatą dla 128 px i większych, uproszczoną
dla 16 i 32 px. Format icns to przewiduje i tak się to robi profesjonalnie.

Maskotka (`paladin.png`, `paladin.gif`) **zostaje** tam, gdzie ma miejsce i sens:
w README, w oknie powitalnym i w sztuce terminalowej.

## Logotypy

| Plik | Co to jest |
|---|---|
| `logo.png` | AIrON — studenckie koło naukowe (nagłówek menu) |
| `logo_footer.png`, `logo_footer_dark.png` | FOCUS FRAME (stopka menu) |

Logotypy należą do swoich właścicieli i są użyte za zgodą.
