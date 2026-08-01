# Testy `wykryj_twardy_pad()` — matryca dowodowa (Neo, 30.07.2026)

`test_wykryj_twardy_pad.py` — 16 przypadków bez uruchamiania demona i **bez dotykania**
`~/.coffee-paladin` (izolacja: import przez `importlib` + podmiana w module wszystkich
atrybutów `*_PATH`/`*_DIR` na katalog tymczasowy; `HOME` ze środowiska NIE wystarcza,
bo `guard.py` liczy je z `pwd`).

    T=$(mktemp -d) && python3 test_wykryj_twardy_pad.py "$T"; rm -rf "$T"

Zakres: A) 8 przypadków logiki (pad/czysty stop/okno `[puls-60, boot)`/podłoga 30 dni/
restore bez `-p`), B) 4 warianty formatu pulsu (nowy `epoch tekst`, legacy sam tekst,
śmieci, pusty plik), C) 4 scenariusze stref czasowych (w tym Kiritimati→Midway, delta 25 h,
oraz legacy+strefa — jedyny znany FAIL, patrz notatka v4).

Wynik na `v1.7.4` (b5262eb): **A 8/8, B 4/4, C 3/4**.
