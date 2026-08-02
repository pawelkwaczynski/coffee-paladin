// heatbar.swift - thermal state of the Mac in the menu bar.
//
// It measures nothing on its own: it reads ~/.coffee-paladin/status.json, which the coffee-paladin daemon
// writes on every cycle (every 15 s). That is why it costs no CPU and can never disagree with
// the guard. Manual commands are passed back through a file and executed by the daemon, so
// exactly one process ever decides what gets paused.
//
// In the bar:  thermometer C67 G64 B33 fan3.3k 42W RAM62% DISK46%
//   C/G/B - chip, GPU, battery;  fan - rpm (warning when stopped while hot);  W - power draw;
//   brain - RAM used;  disk - disk used;  bolt - macOS is throttling;  pause - something paused.
//
// Pick what is shown: menu > Show in the bar (checkboxes), stored in ~/.coffee-paladin/heatbar.json.
// Language: TG_LANG=en|pl, or "lang" in ~/.coffee-paladin/config.json. Default: en.
//
// Build:  swiftc -O -o ~/.local/bin/coffee-paladin-bar heatbar.swift

import Cocoa

let VERSION = "2.1.9"
let APPNAME = "coffee-paladin"
let CODENAME = "Ristretto"
let SIGNATURE = "\(APPNAME) v\(VERSION) \u{201E}\(CODENAME)\u{201D}  ·  by panbookovsky"

// Katalog roboczy. TG_BASE pozwala uruchomic pasek w izolacji (testy UI, demo)
// bez ryzyka, ze klikniecie w oknie powitalnym przestawi konfiguracje zywej
// instalacji. Uwaga: expandingTildeInPath NIE slucha podmienionego HOME -
// dlatego potrzebna jest osobna zmienna, a nie sztuczka z katalogiem domowym.
let base = ProcessInfo.processInfo.environment["TG_BASE"].map {
    NSString(string: $0).expandingTildeInPath
} ?? NSString(string: "~/.coffee-paladin").expandingTildeInPath
let statusPath = base + "/status.json"
let historyPath = base + "/history.csv"
let logPath = base + "/guard.log"
let commandPath = base + "/command"
let configPath = base + "/config.json"
let prefsPath = base + "/heatbar.json"
let reportBin = NSString(string: "~/.local/bin/thermal-report").expandingTildeInPath

// MARK: - language

let SUPPORTED_LANGS = ["en", "pl", "ru", "zh", "es"]

let lang: String = {
    func norm(_ v: String) -> String? {
        let l = v.lowercased()
        for c in SUPPORTED_LANGS where l.hasPrefix(c) { return c }
        return nil
    }
    if let v = norm(ProcessInfo.processInfo.environment["TG_LANG"] ?? "") { return v }
    if let d = FileManager.default.contents(atPath: configPath),
       let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
       let v = norm((j["lang"] as? String) ?? "") { return v }
    return "en"
}()

let PL: [String: String] = [
    "!": "!",
    "no data - is coffee-paladin running?": "brak danych - czy coffee-paladin działa?",
    "data is stale (%@) - the guard may have died": "dane nieświeże (%@) - guard mógł paść",
    "the Mac shut down without warning: %@": "Mac zgasł bez ostrzeżenia: %@",
    "Battery:  %@": "Bateria:  %@",
    "Fans:  %@": "Wentylatory:  %@",
    "stopped": "stoi", "%d rpm": "%d obr/min", "%@ rpm": "%@ obr/min", "n/a": "n/d",
    "Draw:  %.1f W": "Pobór:  %.1f W",
    "RAM:  %.1f / %.1f GB (%d%%)": "RAM:  %.1f / %.1f GB (%d%%)",
    "swap %.2f GB": "swap %.2f GB",
    "Disk:  %d / %d GB used (%d%%)": "Dysk:  %d / %d GB zajęte (%d%%)",
    "Power:  %@": "Zasilanie:  %@",
    "AC adapter": "zasilacz", "battery %@": "bateria %@",
    "Load:  %.2f / %d cores": "Obciążenie:  %.2f / %d rdzeni",
    "Throttling: CPU capped at %d%% speed": "Dławienie: CPU ścięte do %d%% prędkości",
    "   readings: %.0f-%.0f C": "   ostatnie pomiary: %.0f-%.0f C",
    "rising %.1f C/min - about %.0f min to pause": "rośnie %.1f C/min - do pauzy ok. %.0f min",
    "rising %.1f C/min": "rośnie %.1f C/min",
    "Supervised jobs (safe-run):": "Zadania pod opieką (safe-run):",
    "Heating the most now (CPU ≈ heat):": "Najbardziej grzeją teraz (CPU ≈ ciepło):",
    "Eating the most RAM:": "Najwięcej RAM zjadają:",
    "Top CPU:  %@ (%d%%)": "Najwięcej CPU:  %@ (%d%%)",
    "Paused: %@": "Wstrzymane: %@",
    "  (manual)": "  (ręcznie)",
    "State: %@": "Stan: %@",
    "calm": "spokój", "warm": "ciepło", "HOT - paused": "GORĄCO - pauza", "CRITICAL": "KRYTYCZNIE",
    "Chip thresholds:  pause %.0f C, kill %.0f C": "Progi chipa:  pauza %.0f C, ubicie %.0f C",
    "Today: %d x pause": "Dziś: %d x pauza", ", %d x kill": ", %d x ubicie",
    "Resume paused jobs": "Wznów wstrzymane zadania",
    "Freeze all heavy jobs now": "Wstrzymaj ciężkie zadania",
    "A freeze is not a kill. The process stops between two instructions, keeps its memory and its open files, and carries on from the same place when you switch this off. It is safe.": "Wstrzymanie to nie zabicie. Proces staje między dwiema instrukcjami, zachowuje pamięć i otwarte pliki, a po wyłączeniu przełącznika liczy dalej od tego samego miejsca. Bezpiecznie.",
    "What a freeze does NOT protect: anything waiting on the network or watching a clock will notice the gap. A download or an upload can drop, a server can disconnect you, a video call freezes, a game stops responding.": "Czego wstrzymanie NIE chroni: cokolwiek czeka na sieć albo pilnuje zegara, zauważy przerwę. Pobieranie albo wysyłka mogą się zerwać, serwer może Cię rozłączyć, rozmowa wideo zamarznie, gra przestanie odpowiadać.",
    "The paladin will NEVER touch the system, Finder, your terminal or your AI agent.": "Paladyn NIGDY nie ruszy systemu, Findera, Twojego terminala ani Twojego agenta AI.",
    "Freeze all of them": "Wstrzymaj wszystkie",
    "Freeze heavy jobs now?": "Wstrzymać teraz ciężkie zadania?",
    "Nothing heavy is running right now. Anything that gets heavy will be frozen until you switch this back off.": "Nic ciężkiego teraz nie chodzi. Cokolwiek się rozpędzi, zostanie wstrzymane, dopóki nie przesuniesz przełącznika z powrotem.",
    "Freeze": "Wstrzymaj",
    "Pause jobs when the Mac overheats": "Włącz pauzowanie przy przegrzaniu",
    "OFF - the Mac is only being watched": "WYŁĄCZONE — Mac jest tylko obserwowany",
    "Show in the bar": "Pokaż na pasku",
    "Export report for a repair shop": "Raport dla serwisu",
    "As PDF…": "Jako PDF...",
    "As plain text (TXT)…": "Jako tekst (TXT)...",
    "Show the guard log": "Pokaż dziennik zdarzeń",
    "Quit coffee-paladin (protection stops)": "Wyłącz coffee-paladin (ochrona przestaje działać)",
    "Turn off thermal protection for this Mac?": "Czy chcesz wyłączyć ochronę termiczną tego Maca?",
    "The daemon and the menu bar both stop. Nothing will pause hot jobs until you start it again.":
        "Demon i pasek menu zostaną zatrzymane. Nic nie wstrzyma gorących zadań, dopóki nie uruchomisz programu ponownie.",
    "Quit anyway": "Wyłącz mimo to",
    "Cancel": "Anuluj",
    "Chip temperature": "Temperatura chipa", "GPU temperature": "Temperatura GPU",
    "Battery temperature": "Temperatura baterii", "Fan rpm": "Obroty wentylatorów",
    "Power draw (W)": "Pobór mocy (W)", "RAM used": "Zajęty RAM", "Disk used": "Zajęty dysk",
    "Throttling marker": "Znacznik dławienia", "Pause marker": "Znacznik pauzy",
    "Flame at critical": "Animacje na pasku (płomień, wentylator, filiżanka)",
    "Like the paladin? Pass it on!": "Lubisz paladyna? Podaj dalej!",
    "Share on X…": "Udostępnij na X...",
    "Share by e-mail…": "Udostępnij e-mailem...",
    "Copy link with note": "Kopiuj link z notką",
    "Star it on GitHub…": "Zostaw gwiazdkę na GitHubie...",
    "Is your Mac heating up with AI and renders? coffee-paladin watches the battery (temperature and charge), the chip (CPU) and the GPU. It pauses heavy jobs when the system overheats and resumes them by itself once the temperature drops, so you can sleep peacefully (literally!). Open source, free, for you:":
        "Twój Mac grzeje się przy AI i renderach? coffee-paladin pilnuje temperatur (i poziomu) baterii, chipa (CPU) oraz GPU. Pauzuje ciężkie zadania kiedy system ulega przegrzaniu i sam je wznawia, gdy temperatura spadnie, abyś Ty mógł spać spokojnie (dosłownie!). Open source, za darmo, dla Ciebie:",
    "Settings": "Ustawienia",
    "Chip pause threshold": "Wstrzymuj zadania powyżej",
    "Battery gate": "Wstrzymuj na baterii poniżej",
    "pause below this charge when unplugged": "bez zasilacza ciężkie zadania poczekają na ładowarkę",
    "TOO LOW - an idle M-series chip already sits at 40-55 C, the guard would pause constantly":
        "ZA NISKO - bezczynny chip M-serii ma 40-55 C, guard pauzowałby bez przerwy",
    "very conservative - a quiet, cool Mac, but long jobs will crawl":
        "bardzo ostrożnie - cichy, chłodny Mac, ale długie zadania będą się wlekły",
    "conservative - good for a fanless Mac (Air, 12-inch)":
        "ostrożnie - dobre dla Maca bez wentylatorów (Air, 12-cal)",
    "recommended - well below Apple's own throttling point (~100-108 C)":
        "zalecane - wyraźnie poniżej progu, na którym macOS sam dławi (~100-108 C)",
    "aggressive - close to the temperature at which macOS throttles by itself":
        "agresywnie - blisko temperatury, w której macOS sam zaczyna dławić",
    "Notifications": "Powiadomienia",
    "Watch only, never touch processes (dry run)": "Tylko obserwuj, nie ruszaj procesów (dry run)",
    "Language": "Język",
    "Sounds": "Dźwięki",
    "Name this Mac in the fleet…": "Nazwij tego Maca we flocie...",
    "e.g. render-01, studio-mini, mbp-14": "np. render-01, studio-mini, mbp-14",
    "With five identical MacBooks the system hostname says nothing. This name shows in the fleet table and menu on every machine. Empty = system hostname.":
        "Przy pięciu identycznych Macach nazwa systemowa nic nie mówi. Ta nazwa pokazuje się w tabeli floty i w menu na każdej maszynie. Puste = nazwa systemowa.",
    "Buy me a double espresso…": "Postaw mi podwójne espresso...",
    "Apple fleet": "Flota Apple",
    "battery": "bateria",
    "paused": "wstrzymane",
    "STALE - not reporting": "NIE RAPORTUJE",
    "no fleet folder - run: fleet --setup": "brak folderu floty — uruchom: fleet --setup",
    "no agent snapshots yet (agents publish about once a minute)":
        "brak migawek agentów (agenty publikują mniej więcej co minutę)",
    "now": "teraz",
    "%d min ago": "%d min temu",
    "%d h ago": "%d h temu",
    "The paladin stands guard. Choose how to begin:": "Paladyn staje na straży. Wybierz, jak zaczynamy:",
    "Enable protection": "Włącz ochronę",
    "Watch only for now": "Na razie tylko obserwuj",
    "Load info": "Informacje o obciążeniu",
    "Keep awake": "Nie usypiaj Maca",
    "Off": "Wyłącz",
    "%d min": "%d min",
    "%d h": "%d h",
    "Indefinitely": "Bezterminowo",
    "While an app is running": "Dopóki działa aplikacja",
    "While downloading (network active)": "Dopóki trwa pobieranie (aktywna sieć)",
    "released automatically when the Mac gets hot": "zwalniane samo, gdy Mac się grzeje",
    "Keep-awake: %@ left": "Czuwanie: zostało %@",
    "caffeinate holds for another %@": "caffeinate trzyma jeszcze %@",
    "Heavy processes right now: %d": "Ilość ciężkich procesów: %d",
    "Measurement interval": "Częstotliwość pomiarów",
    "Pick the report period.": "Wybierz okres raportu.",
    "Included: hardware, battery, sudden shutdowns, interventions, measurement timeline.":
        "W raporcie: sprzęt, bateria, nagłe wyłączenia, interwencje, oś pomiarów.",
    "From:": "Od:",
    "This topic will not work": "Ten temat nie zadziala",
    "Use only letters, digits, _ and -, up to 64 characters. A space stops the push silently, and # or ? publish to a shorter topic than the one you typed.": "Uzywaj tylko liter, cyfr, _ i -, do 64 znakow. Spacja cicho blokuje push, a # albo ? publikuja na krotszy temat niz ten, ktory wpisales.",
    "First steps with the paladin": "Pierwsze kroki z paladynem",
    "First steps…": "Pierwsze kroki...",
    "WHAT IT CAN DO\n• The paladin watches the chip, the battery, the fans and the power source - by default a reading every 15 seconds.\n• When things get too hot, it FREEZES heavy processes instead of letting the Mac cook itself. The pause destroys nothing: the process stops mid-instruction and continues once the chip cools. Example? Measured: 89 °C → 60 °C in 19 seconds, no loss.\n• It finds the real culprit: CPU is counted across the whole process tree, so it also sees a script that spawns hundreds of short jobs while using almost nothing itself.\n• On battery below 10% it pauses long jobs - they resume when you plug in.\n• It keeps a black box: after a hard failure the last 8 readings survive. One click turns them into a report for a repair shop (should you ever need it).\n• Keep-awake - works like the well-known Caffeine or Amphetamine, but unlike them it comes with a fuse: the sleep lock is released the moment things run hot. Sleep is the fastest cooling there is.": "CO POTRAFI\n• Paladyn pilnuje chipa, baterii, wentylatorów i zasilania – domyślny pomiar co 15 sekund.\n• Gdy robi się za gorąco, ZAMRAŻA ciężkie procesy zamiast pozwolić Macowi się ugotować. Pauza niczego nie niszczy: proces staje w miejscu i rusza dalej, gdy chip ostygnie. Przykład? Zmierzone: 89 °C → 60 °C w 19 sekund, obliczenia bez strat.\n• Znajduje prawdziwego winowajcę: liczy CPU całego drzewa procesów, więc widzi też skrypt, który odpala setki krótkich zadań i sam prawie nic nie zużywa.\n• Na baterii poniżej 10% wstrzymuje długie obliczenia - wznowi po podpięciu ładowarki.\n• Prowadzi czarną skrzynkę: po twardej awarii zostaje 8 ostatnich pomiarów. Jednym kliknięciem złożysz z tego raport dla serwisu (w razie potrzeby).\n• „Nie usypiaj Maca\" – działa jak znane programy Caffeine czy Amphetamine, ale w odróżnieniu od nich robi to z bezpiecznikiem: blokada snu puszcza w momencie, gdy robi się gorąco. Sen chłodzi najszybciej.",
    "WHAT WILL HAPPEN\n• Your choice in the welcome window decides how you start.\n\n\"Watch only\" mode: the paladin measures, logs and alerts, but PAUSES NOTHING.\n\n\"Enable protection\" mode: it pauses at the defined thresholds.\n\nSwitching is easy - one switch at the top of the menu.\n\n• Default thresholds: pause at 85 °C, resume at 76 °C, gentle closing of processes at 90 °C - and only after 4 critical readings in a row. Above 90 °C for over a minute is an emergency: despite the pauses the chip still holds critical (something we could not pause is heating, or pausing was not enough to cool the chip). The process is then woken up and gets SIGTERM - a polite \"shut down\": it has a chance to save its state, close its files, clean up. That is why we call this termination \"gentle\".\n\nA fanless Mac (e.g. an Air or Neo) gets more careful parameters. The thresholds are always picked for YOUR machine: see menu > \"About my Mac\".\n\n• Notifications: on. Sounds: off (enable them in Settings). At the critical level a system banner breaks through everything - Focus and full-screen included.\n• The system, Finder, your terminal and your AI agent are on the never-touch list. The guard will not freeze the session working next to it.": "CO SIĘ BĘDZIE DZIAŁO\n• Twój wybór z okna powitalnego decyduje o starcie.\n\nTryb „Tylko obserwuj\": paladyn mierzy, loguje i alarmuje, ale NICZEGO NIE WSTRZYMUJE.\n\nTryb „Włącz ochronę\": pauzuje na zdefiniowanych progach.\n\nTryby przełączysz łatwo – to jeden switch na górze menu.\n\n• Domyślne progi: pauza przy 85 °C, wznowienie przy 76 °C, łagodne zamknięcie procesów przy 90 °C - i to dopiero po 4 krytycznych odczytach z rzędu. Ponad 90 °C przez ponad 1 minutę to sytuacja awaryjna: mimo pauzowania chip dalej trzyma poziom krytyczny (czyli grzeje coś, czego nie mogliśmy zapauzować, albo pauza nie wystarczyła do chłodzenia chipa). Wtedy proces jest budzony i dostaje SIGTERM — grzeczne „zamknij się\": ma szansę zapisać stan, domknąć pliki, posprzątać. Dlatego ubicie go traktujemy jako „łagodne\".\n\nMac bez wentylatora (np. Air lub Neo) dostaje ostrożniejsze parametry. Progi zawsze są dobrane dla TWOJEJ maszyny: zobacz w menu > „O moim Macu\".\n\n• Powiadomienia: włączone. Dźwięki: wyłączone (włączysz w Ustawieniach). Przy poziomie krytycznym baner systemowy przebija się zawsze - nawet przez Skupienie i pełny ekran.\n• System, Finder, terminal i Twój agent AI są na liście nietykalnych. Strażnik nie zamrozi sesji, która przy nim pracuje.",
    "WHAT YOU CAN SET\n• Chip pause threshold - a slider; resume and terminate recalculate themselves.\n• Measurement interval 5-30 s: more often = faster reaction, but costlier in CPU use.\n• Heavy jobs (safe-run): all cores (fast) or efficiency cores only (cool and quiet), plus a CPU limit of 50-100%.\n• Battery gate, signals, keep-awake, this Mac's name in the fleet.": "CO MOŻESZ USTAWIĆ\n• Próg pauzy chipa - suwak; wznowienie i ubicie przeliczają się same.\n• Interwał pomiaru 5-30 s: częściej = szybsza reakcja, ale drożej w użyciu CPU.\n• Ciężkie zadania (safe-run): wszystkie rdzenie (szybko) albo tylko E-cores (chłodno i cicho), do tego limit CPU 50-100%.\n• Bramka baterii, sygnały, „Nie usypiaj\", nazwa tego Maca we flocie.",
    "PHONE PUSH (ntfy)\n• Settings → \"Phone push (ntfy.sh)...\". The topic name is the ONLY protection: anyone who knows or guesses it can read your alerts and send fake ones. Click \"Generate\" - you get a random, unguessable one.\n• On your phone install the ntfy app from ntfy.sh - mind the lookalike apps - and subscribe to the same topic.\n• No account, no server of ours. It works over the internet, not WiFi: the 90 °C pause reaches your phone on a train, over LTE.": "PUSH NA TELEFON (ntfy)\n• Ustawienia → „Push na telefon (ntfy.sh)...\". Nazwa tematu to JEDYNE zabezpieczenie: kto ją zna albo zgadnie, czyta Twoje alerty i może wysyłać fałszywe. Kliknij „Wygeneruj\" - dostaniesz losową, niezgadywalną.\n• Na telefonie zainstaluj aplikację ntfy ze strony ntfy.sh - uwaga na podszywające się apki - i zasubskrybuj ten sam temat.\n• Bez konta i bez naszego serwera. Działa przez internet, nie po WiFi: pauza przy 90 °C dojdzie na telefon w pociągu, na LTE.",
    "Enjoy your work!\nPaweł": "Przyjemnej pracy!\nPaweł",
    "Is your Mac heating up with AI and renders? coffee-paladin watches battery, chip and GPU temperatures. It pauses heavy jobs and resumes them by itself once the temperature drops.\n\nOpen source, free, for you:\n%@\n\n#panbookovsky #macbook #protect #temperature #guard":
        "Twój Mac grzeje się przy AI i renderach? coffee-paladin pilnuje temperatur baterii, chipa i GPU. Pauzuje ciężkie zadania i sam je wznawia, gdy temperatura spadnie.\n\nOpen source, za darmo, dla Ciebie:\n%@\n\n#panbookovsky #macbook #protect #temperature #guard",
    "you have to see this: coffee-paladin": "musisz to zobaczyć: coffee-paladin",
    "Hey,\n\nI found something you need on your Mac: coffee-paladin. It watches the chip, GPU and battery temperatures, and when things get hot it pauses heavy jobs and resumes them by itself once the machine cools down.\n\nIt is damn good, because the pause is lossless (the process freezes and continues from the same spot), it sends nothing anywhere, and it is free, open source:\n%@\n\nThe knight with the coffee in the attachment is its mascot.\n\nCheers!":
        "Hej,\n\nznalazłem coś, co musisz mieć na Macu: coffee-paladin. Pilnuje temperatur chipa, GPU i baterii, a jak robi się gorąco, pauzuje ciężkie zadania i sam je wznawia, gdy maszyna ostygnie.\n\nJest zajebiste, bo pauza jest bezstratna (proces zamiera i rusza z tego samego miejsca), nic nigdzie nie wysyła i jest za darmo, open source:\n%@\n\nRycerz z kawą w załączniku to jego maskotka.\n\nPozdro!",
    "chip": "chip", "fans": "wentylatory", "draw": "pobór", "state": "stan", "snapshot": "migawka",
    "To:": "Do:",
    "Everything on record": "Całość, wszystkie zapisy",
    "Cores:  %d performance + %d efficiency  ·  Neural Engine: %d":
        "Rdzenie:  %d wydajnościowych + %d oszczędne  ·  Neural Engine: %d",
    "Disk: %d GB (%d%% free)": "Dysk: %d GB (%d%% wolnego)",
    "max capacity: %d%%": "maks. pojemność: %d%%",
    "Sensors:": "Czujniki:",
    "chip and GPU (macmon/IOReport):  %@": "chip i GPU (macmon/IOReport):  %@",
    "thermal state (Apple API):  %@": "stan termiczny (API Apple):  %@",
    "battery (ioreg):  %@": "bateria (ioreg):  %@",
    "CPU throttling (pmset):  %@": "dławienie CPU (pmset):  %@",
    "limited warranty (est.): until %@": "limited warranty (szac.): do %@",
    "set up: %@": "skonfigurowany: %@",
    "Turns off banners, their sounds and phone push - one gate for all.":
        "Wyłącza dymki, dźwięki przy nich i push na telefon — jedna bramka dla wszystkich.",
    "Exception: the critical banner shouts regardless.":
        "Wyjątek: baner krytyczny krzyczy niezależnie.",
    "It is the ‹Pause jobs when the Mac overheats› switch: OFF = watch-only.":
        "To stan przełącznika ‹Włącz pauzowanie przy przegrzaniu›: wyłączony = tylko obserwacja.",
    "fastest reaction - the guard itself burns ~3.5% of one core all the time":
        "najszybsza reakcja, ale strażnik sam pali ~3,5% jednego rdzenia bez przerwy",
    "reacts up to 5 s sooner than default, costs ~1.8% of one core":
        "reaguje do 5 s szybciej niż domyślnie, kosztuje ~1,8% jednego rdzenia",
    "default: good reaction at ~1.2% of one core":
        "domyślnie: dobra reakcja przy ~1,2% jednego rdzenia",
    "frugal - an automatic pause may come tens of seconds after the threshold":
        "oszczędnie, ale automatyczna pauza może przyjść kilkadziesiąt sekund po progu",
    "Keep-awake: while %@ is running": "Czuwanie: dopóki działa %@",
    "Keep-awake: while downloading": "Czuwanie: dopóki trwa pobieranie",
    "Keep-awake: indefinitely": "Czuwanie: bezterminowo",
    "Heavy jobs (safe-run)": "Ciężkie zadania (safe-run)",
    "Efficiency cores only (cool and quiet)": "Tylko rdzenie energooszczędne (chłodno i cicho)",
    "All cores (fast - the paladin still watches the temperature)":
        "Wszystkie rdzenie (szybko — temperatury i tak pilnuje paladyn)",
    "CPU limit for heavy jobs": "Limit CPU dla ciężkich zadań",
    "below 100% the whole job gets tiny micro-pauses (works for any program)":
        "poniżej 100% całe zadanie dostaje mikropauzy (działa z każdym programem)",
    "Start at login": "Uruchamiaj przy starcie komputera",
    "About my Mac": "O moim Macu",
    "Phone push (ntfy.sh)…": "Push na telefon (ntfy.sh)...",
    "Enter a secret topic name. Install the ntfy app on your phone and subscribe to the same topic - pauses, kills and alarms will arrive as push notifications. Leave empty to disable.":
        "Wpisz sekretną nazwę tematu. Zainstaluj na telefonie aplikację ntfy i zasubskrybuj ten sam temat — pauzy, ubicia i alarmy przyjdą jako push. Puste pole wyłącza.",
    "The topic name is the ONLY protection: anyone who knows or guesses it can read your alerts and send fake ones. Click Generate for a random unguessable name. On your phone install the ntfy.sh app (from ntfy.sh - mind the lookalike apps) and subscribe to the same topic. Leave empty to disable.":
        "Nazwa tematu to JEDYNE zabezpieczenie: kto ją zna lub zgadnie, widzi Twoje alerty i może wysyłać fałszywe. Kliknij Wygeneruj, aby dostać losową, niezgadywalną nazwę. Na telefonie zainstaluj aplikację ntfy.sh (ze strony ntfy.sh - uwaga na podobne apki) i zasubskrybuj ten sam temat. Puste pole wyłącza.",
    "A project of the AIrON student research club.": "Projekt w ramach koła naukowego AHE w Łodzi.",
    "Generate": "Wygeneruj",
    "Model:  %@": "Model:  %@",
    "Chip:  %@": "Chip:  %@",
    "Cores:  %d performance + %d efficiency": "Rdzenie:  %d wydajnościowych + %d energooszczędnych",
    "RAM:  %d GB": "RAM:  %d GB",
    "Fans:  %d": "Wentylatory:  %d",
    "macOS:  %@": "macOS:  %@",
    "Serial:  %@": "Nr seryjny:  %@",
    "Battery cycles:  %@": "Cykle baterii:  %@",
    "Chip sensor (macmon):  %@": "Czujnik chipa (macmon):  %@",
    "yes": "tak",
    "no": "nie",
    "Keep the Mac awake while heavy jobs run": "Trzymaj caffeinate na ciężkie zadania",
    "Keeping the Mac awake (heavy job running)": "Trzymam Maca w czuwaniu (działa ciężkie zadanie)",
    "resume at %.0f °C, terminate at %.0f C": "wznowienie przy %.0f °C, ubicie przy %.0f °C",
    "no fans (fanless Mac)": "brak wentylatorów (Mac bez wentylatorów)",
    "What does watch-only mode do?": "Co daje tryb „tylko obserwuj”?",
    "Report a problem (GitHub)…": "Zgłoś problem lub pomysł (GitHub)...",
    "Write to the author (GitHub)…": "Napisz do autora (GitHub)...",
    "Watch only (dry run)": "Tylko obserwuj (dry run)",
    "WATCH-ONLY MODE - measuring and alerting, pausing nothing":
        "TRYB OBSERWACJI - mierzę i alarmuję, niczego nie wstrzymuję",
    "Enable protection (pause heavy jobs when hot)":
        "Włącz ochronę (wstrzymuj ciężkie zadania, gdy gorąco)",
    """
Protection is now OFF\n- coffee-paladin has entered watch-only mode.

It still measures everything (chip, GPU, battery, fans) and writes to the event log exactly \
what it WOULD do - "would pause ffmpeg (630% CPU)" - but it sends no signal and never touches \
a single process.

Use it to see whether the thresholds suit your machine before you let the paladin freeze real \
work. Open "Show the guard log" after a heavy job and you will know if it would have interfered \
too eagerly, or not soon enough.

Remember: while this switch is off, NOTHING protects the Mac.\nFlip it back on when you are done.
""": """
Ochrona jest teraz WYŁĄCZONA\n- coffee-paladin przeszedł w tryb biernej obserwacji.

Dalej mierzy wszystko (chip, GPU, baterię, wentylatory) i zapisuje w dzienniku zdarzeń \
dokładnie to, co ZROBIŁBY - „wstrzymałbym ffmpeg (630% CPU)” - ale nie wysyła żadnego \
sygnału i nie rusza ani jednego procesu.

Służy do sprawdzenia, czy progi pasują do Twojej maszyny, zanim pozwolisz paladynowi \
zamrażać realną pracę. Po ciężkim zadaniu otwórz „Pokaż dziennik zdarzeń” i zobaczysz, \
czy wtrącałby się za gorliwie, czy odwrotnie - za późno.

Pamiętaj: póki ten przełącznik jest wyłączony, NIC nie chroni Maca.\nWłącz go z powrotem, \
gdy skończysz.
""",
]

let RU: [String: String] = [
    "Keep the Mac awake while heavy jobs run": "Не давать Mac засыпать, пока идут тяжёлые задачи",
    "Keeping the Mac awake (heavy job running)": "Держу Mac в бодрствовании (идёт тяжёлая задача)",
    "no data - is coffee-paladin running?": "нет данных - работает ли coffee-paladin?",
    "data is stale (%@) - the guard may have died": "данные устарели (%@) - демон мог упасть",
    "the Mac shut down without warning: %@": "Mac выключился без предупреждения: %@",
    "Battery:  %@": "Батарея:  %@",
    "Fans:  %@": "Вентиляторы:  %@",
    "stopped": "стоит",
    "%d rpm": "%d об/мин", "%@ rpm": "%@ об/мин",
    "n/a": "н/д",
    "Draw:  %.1f W": "Мощность:  %.1f Вт",
    "RAM:  %.1f / %.1f GB (%d%%)": "RAM:  %.1f / %.1f ГБ (%d%%)",
    "swap %.2f GB": "своп %.2f ГБ",
    "Disk:  %d / %d GB used (%d%%)": "Диск:  занято %d / %d ГБ (%d%%)",
    "Power:  %@": "Питание:  %@",
    "AC adapter": "адаптер питания",
    "battery %@": "батарея %@",
    "Load:  %.2f / %d cores": "Нагрузка:  %.2f / %d ядер",
    "Throttling: CPU capped at %d%% speed": "Троттлинг: CPU ограничен до %d%% скорости",
    "   readings: %.0f-%.0f C": "   измерения: %.0f-%.0f C",
    "rising %.1f C/min - about %.0f min to pause": "растёт на %.1f C/мин - до паузы около %.0f мин",
    "rising %.1f C/min": "растёт на %.1f C/мин",
    "Supervised jobs (safe-run):": "Задачи под присмотром (safe-run):",
    "Heating the most now (CPU ≈ heat):": "Сильнее всего греют сейчас (CPU ≈ тепло):",
    "Eating the most RAM:": "Больше всего памяти занимают:",
    "Top CPU:  %@ (%d%%)": "Больше всего CPU:  %@ (%d%%)",
    "Paused: %@": "Приостановлено: %@",
    "  (manual)": "  (вручную)",
    "State: %@": "Состояние: %@",
    "calm": "спокойно",
    "warm": "тепло",
    "HOT - paused": "ГОРЯЧО - пауза",
    "CRITICAL": "КРИТИЧНО",
    "Chip thresholds:  pause %.0f C, kill %.0f C": "Пороги чипа:  пауза %.0f C, завершение %.0f C",
    "Today: %d x pause": "Сегодня: %d x пауза",
    ", %d x kill": ", %d x завершение",
    "Resume paused jobs": "Возобновить приостановленные задачи",
    "Freeze all heavy jobs now": "Приостановить тяжёлые задачи",
    "A freeze is not a kill. The process stops between two instructions, keeps its memory and its open files, and carries on from the same place when you switch this off. It is safe.": "Приостановка - не убийство. Процесс замирает между двумя инструкциями, сохраняет память и открытые файлы и продолжит с того же места, когда вы выключите переключатель. Это безопасно.",
    "What a freeze does NOT protect: anything waiting on the network or watching a clock will notice the gap. A download or an upload can drop, a server can disconnect you, a video call freezes, a game stops responding.": "Что приостановка НЕ защищает: всё, что ждёт сеть или следит за часами, заметит паузу. Загрузка или выгрузка может оборваться, сервер может вас отключить, видеозвонок замрёт, игра перестанет отвечать.",
    "The paladin will NEVER touch the system, Finder, your terminal or your AI agent.": "Паладин НИКОГДА не тронет систему, Finder, ваш терминал и вашего ИИ-агента.",
    "Freeze all of them": "Приостановить все",
    "Freeze heavy jobs now?": "Приостановить тяжёлые задачи сейчас?",
    "Nothing heavy is running right now. Anything that gets heavy will be frozen until you switch this back off.": "Сейчас ничего тяжёлого не работает. Всё, что станет тяжёлым, будет приостановлено, пока вы не выключите этот переключатель.",
    "Freeze": "Приостановить",
    "Pause jobs when the Mac overheats": "Приостанавливать задачи при перегреве",
    "OFF - the Mac is only being watched": "ВЫКЛЮЧЕНО — Mac только под наблюдением",
    "Show in the bar": "Показывать в строке меню",
    "Export report for a repair shop": "Отчёт для сервисного центра",
    "As PDF…": "В PDF...",
    "As plain text (TXT)…": "Текстом (TXT)...",
    "Show the guard log": "Показать журнал",
    "Quit coffee-paladin (protection stops)": "Выключить coffee-paladin (защита прекращается)",
    "Turn off thermal protection for this Mac?": "Отключить тепловую защиту этого Mac?",
    "The daemon and the menu bar both stop. Nothing will pause hot jobs until you start it again.":
        "Демон и строка меню будут остановлены. Ничто не приостановит горячие задачи, пока вы не запустите программу снова.",
    "Quit anyway": "Всё равно выключить",
    "Cancel": "Отмена",
    "Chip temperature": "Температура чипа",
    "GPU temperature": "Температура GPU",
    "Battery temperature": "Температура батареи",
    "Fan rpm": "Обороты вентиляторов",
    "Power draw (W)": "Потребляемая мощность (Вт)",
    "RAM used": "Занятая память",
    "Disk used": "Занятый диск",
    "Throttling marker": "Индикатор троттлинга",
    "Pause marker": "Индикатор паузы",
    "Flame at critical": "Анимации в строке меню (пламя, вентилятор, чашка)",
    "Like the paladin? Pass it on!": "Нравится паладин? Передай дальше!",
    "Share on X…": "Поделиться в X...",
    "Share by e-mail…": "Поделиться по почте...",
    "Copy link with note": "Скопировать ссылку с заметкой",
    "Star it on GitHub…": "Поставить звезду на GitHub...",
    "Is your Mac heating up with AI and renders? coffee-paladin watches the battery (temperature and charge), the chip (CPU) and the GPU. It pauses heavy jobs when the system overheats and resumes them by itself once the temperature drops, so you can sleep peacefully (literally!). Open source, free, for you:":
        "Ваш Mac греется под ИИ и рендерами? coffee-paladin следит за батареей (температура и заряд), чипом (CPU) и GPU. Он ставит тяжёлые задачи на паузу при перегреве и сам возобновляет их, когда температура падает, чтобы вы могли спать спокойно (буквально!). Open source, бесплатно, для вас:",
    "Settings": "Настройки",
    "Chip pause threshold": "Пауза при температуре чипа выше",
    "Battery gate": "Пауза при заряде ниже",
    "pause below this charge when unplugged": "без адаптера тяжёлые задачи подождут зарядку",
    "TOO LOW - an idle M-series chip already sits at 40-55 C, the guard would pause constantly": "СЛИШКОМ НИЗКО - чип M-серии без нагрузки уже при 40-55 C, пауза была бы постоянной",
    "very conservative - a quiet, cool Mac, but long jobs will crawl": "очень осторожно - тихий и холодный Mac, но долгие задачи будут ползти",
    "conservative - good for a fanless Mac (Air, 12-inch)": "осторожно - подходит для Mac без вентиляторов (Air)",
    "recommended - well below Apple's own throttling point (~100-108 C)": "рекомендуется - заметно ниже порога троттлинга macOS (~100-108 C)",
    "aggressive - close to the temperature at which macOS throttles by itself": "агрессивно - близко к температуре, при которой macOS сам снижает частоты",
    "Notifications": "Уведомления",
    "Watch only, never touch processes (dry run)": "Только наблюдать, не трогать процессы (dry run)",
    "resume at %.0f °C, terminate at %.0f C": "возобновление при %.0f C, завершение при %.0f C",
    "What does watch-only mode do?": "Что делает режим наблюдения?",
    "Report a problem (GitHub)…": "Сообщить о проблеме (GitHub)...",
    "Write to the author (GitHub)…": "Написать автору (GitHub)...",
    "Watch only (dry run)": "Только наблюдение (dry run)",
    """
Protection is now OFF\n- coffee-paladin has entered watch-only mode.

It still measures everything (chip, GPU, battery, fans) and writes to the event log exactly \
what it WOULD do - "would pause ffmpeg (630% CPU)" - but it sends no signal and never touches \
a single process.

Use it to see whether the thresholds suit your machine before you let the paladin freeze real \
work. Open "Show the guard log" after a heavy job and you will know if it would have interfered \
too eagerly, or not soon enough.

Remember: while this switch is off, NOTHING protects the Mac.\nFlip it back on when you are done.
""": """
Защита сейчас ВЫКЛЮЧЕНА
- coffee-paladin перешёл в режим пассивного наблюдения.

Он по-прежнему измеряет всё (чип, GPU, батарею, вентиляторы) и записывает в журнал \
ровно то, что СДЕЛАЛ БЫ - «приостановил бы ffmpeg (630% CPU)» - но не посылает \
ни одного сигнала и не трогает ни один процесс.

Это нужно, чтобы проверить, подходят ли пороги вашей машине, прежде чем разрешить \
паладину замораживать реальную работу. После тяжёлой задачи откройте «Показать журнал \
стража» и увидите, вмешивался бы он слишком рьяно или, наоборот, слишком поздно.

Помните: пока этот переключатель выключен, НИЧТО не защищает Mac.
Включите его обратно, когда закончите.
""",
    "WATCH-ONLY MODE - measuring and alerting, pausing nothing": "РЕЖИМ НАБЛЮДЕНИЯ - измеряю и предупреждаю, ничего не приостанавливаю",
    "Enable protection (pause heavy jobs when hot)": "Включить защиту (пауза тяжёлых задач при нагреве)",
    "Language": "Язык",
    "Sounds": "Звуки",
    "Name this Mac in the fleet…": "Имя этого Mac в парке...",
    "e.g. render-01, studio-mini, mbp-14": "напр. render-01, studio-mini, mbp-14",
    "With five identical MacBooks the system hostname says nothing. This name shows in the fleet table and menu on every machine. Empty = system hostname.":
        "Когда MacBook пять одинаковых, системное имя ничего не говорит. Это имя видно в таблице парка и в меню на каждой машине. Пустое = системное имя.",
    "Buy me a double espresso…": "Угостить двойным эспрессо...",
    "Apple fleet": "Парк Apple",
    "battery": "батарея",
    "paused": "приостановлено",
    "STALE - not reporting": "НЕ ОТЧИТЫВАЕТСЯ",
    "no fleet folder - run: fleet --setup": "нет папки парка - выполните: fleet --setup",
    "no agent snapshots yet (agents publish about once a minute)":
        "нет снимков агентов (агенты публикуют примерно раз в минуту)",
    "now": "сейчас",
    "%d min ago": "%d мин назад",
    "%d h ago": "%d ч назад",
    "The paladin stands guard. Choose how to begin:": "Паладин заступает на стражу. С чего начнём:",
    "Enable protection": "Включить защиту",
    "Watch only for now": "Пока только наблюдать",
    "Load info": "Сведения о нагрузке",
    "Keep awake": "Не давать Mac спать",
    "Off": "Выключить",
    "%d min": "%d мин",
    "%d h": "%d ч",
    "Indefinitely": "Бессрочно",
    "While an app is running": "Пока работает приложение",
    "While downloading (network active)": "Пока идёт загрузка (сеть активна)",
    "released automatically when the Mac gets hot": "снимается само, когда Mac нагревается",
    "Keep-awake: %@ left": "Бодрствование: осталось %@",
    "caffeinate holds for another %@": "caffeinate держит ещё %@",
    "Heavy processes right now: %d": "Тяжёлых процессов сейчас: %d",
    "Measurement interval": "Частота измерений",
    "Pick the report period.": "Выберите период отчёта.",
    "Included: hardware, battery, sudden shutdowns, interventions, measurement timeline.":
        "В отчёте: железо, батарея, внезапные отключения, вмешательства, шкала измерений.",
    "From:": "С:",
    "This topic will not work": "Эта тема не сработает",
    "Use only letters, digits, _ and -, up to 64 characters. A space stops the push silently, and # or ? publish to a shorter topic than the one you typed.": "Используйте только буквы, цифры, _ и -, до 64 символов. Пробел молча блокирует push, а # или ? публикуют в более короткую тему, чем введённая.",
    "First steps with the paladin": "Первые шаги с паладином",
    "First steps…": "Первые шаги...",
    "WHAT IT CAN DO\n• The paladin watches the chip, the battery, the fans and the power source - by default a reading every 15 seconds.\n• When things get too hot, it FREEZES heavy processes instead of letting the Mac cook itself. The pause destroys nothing: the process stops mid-instruction and continues once the chip cools. Example? Measured: 89 °C → 60 °C in 19 seconds, no loss.\n• It finds the real culprit: CPU is counted across the whole process tree, so it also sees a script that spawns hundreds of short jobs while using almost nothing itself.\n• On battery below 10% it pauses long jobs - they resume when you plug in.\n• It keeps a black box: after a hard failure the last 8 readings survive. One click turns them into a report for a repair shop (should you ever need it).\n• Keep-awake - works like the well-known Caffeine or Amphetamine, but unlike them it comes with a fuse: the sleep lock is released the moment things run hot. Sleep is the fastest cooling there is.": "ЧТО ОН УМЕЕТ\n• Паладин следит за чипом, батареей, вентиляторами и питанием - по умолчанию замер каждые 15 секунд.\n• Когда становится слишком горячо, ЗАМОРАЖИВАЕТ тяжёлые процессы, вместо того чтобы дать Mac свариться. Пауза ничего не разрушает: процесс замирает и продолжает с того же места, когда чип остынет. Пример? Измерено: 89 °C → 60 °C за 19 секунд, без потерь.\n• Находит настоящего виновника: CPU считается по всему дереву процессов, поэтому виден и скрипт, порождающий сотни коротких задач.\n• На батарее ниже 10% длинные задачи ставятся на паузу - возобновятся после подключения зарядки.\n• Ведёт чёрный ящик: после жёсткого сбоя остаются 8 последних замеров. Один клик - и из них готов отчёт для сервиса (если понадобится).\n• «Не усыплять Mac» - работает как известные Caffeine или Amphetamine, но в отличие от них с предохранителем: блокировка сна снимается, как только становится горячо. Сон охлаждает быстрее всего.",
    "WHAT WILL HAPPEN\n• Your choice in the welcome window decides how you start.\n\n\"Watch only\" mode: the paladin measures, logs and alerts, but PAUSES NOTHING.\n\n\"Enable protection\" mode: it pauses at the defined thresholds.\n\nSwitching is easy - one switch at the top of the menu.\n\n• Default thresholds: pause at 85 °C, resume at 76 °C, gentle closing of processes at 90 °C - and only after 4 critical readings in a row. Above 90 °C for over a minute is an emergency: despite the pauses the chip still holds critical (something we could not pause is heating, or pausing was not enough to cool the chip). The process is then woken up and gets SIGTERM - a polite \"shut down\": it has a chance to save its state, close its files, clean up. That is why we call this termination \"gentle\".\n\nA fanless Mac (e.g. an Air or Neo) gets more careful parameters. The thresholds are always picked for YOUR machine: see menu > \"About my Mac\".\n\n• Notifications: on. Sounds: off (enable them in Settings). At the critical level a system banner breaks through everything - Focus and full-screen included.\n• The system, Finder, your terminal and your AI agent are on the never-touch list. The guard will not freeze the session working next to it.": "ЧТО БУДЕТ ПРОИСХОДИТЬ\n• Ваш выбор в окне приветствия определяет старт.\n\nРежим «Только наблюдать»: паладин измеряет, ведёт журнал и предупреждает, но НИЧЕГО НЕ ОСТАНАВЛИВАЕТ.\n\nРежим «Включить защиту»: ставит на паузу по заданным порогам.\n\nПереключиться легко - один переключатель вверху меню.\n\n• Пороги по умолчанию: пауза при 85 °C, возобновление при 76 °C, мягкое закрытие процессов при 90 °C - и только после 4 критических замеров подряд. Выше 90 °C дольше минуты - аварийная ситуация: несмотря на паузы чип держит критический уровень (греет то, что мы не могли поставить на паузу, или паузы не хватило для охлаждения). Тогда процесс будят, и он получает SIGTERM - вежливое «завершись»: есть шанс сохранить состояние, закрыть файлы, прибраться. Поэтому такое завершение мы называем «мягким».\n\nMac без вентилятора (например, Air или Neo) получает более осторожные параметры. Пороги всегда подобраны для ВАШЕЙ машины: см. меню > «Об этом Mac».\n\n• Уведомления: включены. Звуки: выключены (включаются в Настройках). На критическом уровне системный баннер пробивается всегда - даже через Фокусирование и полный экран.\n• Система, Finder, терминал и ваш ИИ-агент - в списке неприкасаемых. Страж не заморозит сессию, которая работает рядом с ним.",
    "WHAT YOU CAN SET\n• Chip pause threshold - a slider; resume and terminate recalculate themselves.\n• Measurement interval 5-30 s: more often = faster reaction, but costlier in CPU use.\n• Heavy jobs (safe-run): all cores (fast) or efficiency cores only (cool and quiet), plus a CPU limit of 50-100%.\n• Battery gate, signals, keep-awake, this Mac's name in the fleet.": "ЧТО МОЖНО НАСТРОИТЬ\n• Порог паузы чипа - ползунок; возобновление и завершение пересчитываются сами.\n• Интервал замеров 5-30 с: чаще = быстрее реакция, но дороже по CPU.\n• Тяжёлые задачи (safe-run): все ядра (быстро) или только E-ядра (тихо), плюс лимит CPU 50-100%.\n• Порог батареи, сигналы, keep-awake, имя этого Mac в парке.",
    "PHONE PUSH (ntfy)\n• Settings → \"Phone push (ntfy.sh)...\". The topic name is the ONLY protection: anyone who knows or guesses it can read your alerts and send fake ones. Click \"Generate\" - you get a random, unguessable one.\n• On your phone install the ntfy app from ntfy.sh - mind the lookalike apps - and subscribe to the same topic.\n• No account, no server of ours. It works over the internet, not WiFi: the 90 °C pause reaches your phone on a train, over LTE.": "PUSH НА ТЕЛЕФОН (ntfy)\n• Настройки → «Push на телефон (ntfy.sh)...». Имя темы - ЕДИНСТВЕННАЯ защита: кто его знает или угадает, читает ваши оповещения и может слать поддельные. Нажмите «Сгенерировать» - получите случайное.\n• На телефон установите приложение ntfy с сайта ntfy.sh - остерегайтесь подражателей - и подпишитесь на ту же тему.\n• Без аккаунта и без нашего сервера. Работает через интернет: пауза при 90 °C дойдёт на телефон в поезде, по LTE.",
    "Enjoy your work!\nPaweł": "Приятной работы!\nПавел",
    "Sponsor on GitHub…": "Поддержать на GitHub...",
    "Is your Mac heating up with AI and renders? coffee-paladin watches battery, chip and GPU temperatures. It pauses heavy jobs and resumes them by itself once the temperature drops.\n\nOpen source, free, for you:\n%@\n\n#panbookovsky #macbook #protect #temperature #guard":
        "Ваш Mac греется под ИИ и рендерами? coffee-paladin следит за температурой батареи, чипа и GPU. Ставит тяжёлые задачи на паузу и сам возобновляет их, когда температура падает.\n\nOpen source, бесплатно, для вас:\n%@\n\n#panbookovsky #macbook #protect #temperature #guard",
    "you have to see this: coffee-paladin": "ты должен это увидеть: coffee-paladin",
    "Hey,\n\nI found something you need on your Mac: coffee-paladin. It watches the chip, GPU and battery temperatures, and when things get hot it pauses heavy jobs and resumes them by itself once the machine cools down.\n\nIt is damn good, because the pause is lossless (the process freezes and continues from the same spot), it sends nothing anywhere, and it is free, open source:\n%@\n\nThe knight with the coffee in the attachment is its mascot.\n\nCheers!":
        "Привет!\n\nНашёл то, что нужно каждому Mac: coffee-paladin. Следит за температурой чипа, GPU и батареи, а когда становится горячо - ставит тяжёлые задачи на паузу и сам возобновляет их после остывания.\n\nОно отличное: пауза без потерь (процесс замирает и продолжает с того же места), ничего никуда не отправляет, бесплатно и open source:\n%@\n\nРыцарь с кофе во вложении - его маскот.\n\nПока!",
    "chip": "чип", "fans": "вентиляторы", "draw": "мощность", "state": "состояние", "snapshot": "снимок",
    "To:": "По:",
    "Everything on record": "Всё, что записано",
    "Cores:  %d performance + %d efficiency  ·  Neural Engine: %d":
        "Ядра:  %d производительных + %d экономичных  ·  Neural Engine: %d",
    "Disk: %d GB (%d%% free)": "Диск: %d ГБ (%d%% свободно)",
    "max capacity: %d%%": "макс. ёмкость: %d%%",
    "Sensors:": "Датчики:",
    "chip and GPU (macmon/IOReport):  %@": "чип и GPU (macmon/IOReport):  %@",
    "thermal state (Apple API):  %@": "тепловое состояние (API Apple):  %@",
    "battery (ioreg):  %@": "батарея (ioreg):  %@",
    "CPU throttling (pmset):  %@": "троттлинг CPU (pmset):  %@",
    "limited warranty (est.): until %@": "гарантия (оцен.): до %@",
    "set up: %@": "настроен: %@",
    "Turns off banners, their sounds and phone push - one gate for all.":
        "Отключает уведомления, их звуки и push — один шлюз для всего.",
    "Exception: the critical banner shouts regardless.":
        "Исключение: критический баннер кричит независимо.",
    "It is the ‹Pause jobs when the Mac overheats› switch: OFF = watch-only.":
        "Это состояние переключателя ‹Пауза при перегреве›: выключен = только наблюдение.",
    "fastest reaction - the guard itself burns ~3.5% of one core all the time":
        "самая быстрая реакция, но страж сам жжёт ~3,5% ядра постоянно",
    "reacts up to 5 s sooner than default, costs ~1.8% of one core":
        "реагирует до 5 с быстрее, стоит ~1,8% ядра",
    "default: good reaction at ~1.2% of one core":
        "по умолчанию: хорошая реакция при ~1,2% ядра",
    "frugal - an automatic pause may come tens of seconds after the threshold":
        "экономно, но автопауза может прийти через десятки секунд после порога",
    "Keep-awake: while %@ is running": "Бодрствование: пока работает %@",
    "Keep-awake: while downloading": "Бодрствование: пока идёт загрузка",
    "Keep-awake: indefinitely": "Бодрствование: бессрочно",
    "Heavy jobs (safe-run)": "Тяжёлые задачи (safe-run)",
    "Efficiency cores only (cool and quiet)": "Только энергоэффективные ядра (холодно и тихо)",
    "All cores (fast - the paladin still watches the temperature)":
        "Все ядра (быстро — за температурой всё равно следит паладин)",
    "CPU limit for heavy jobs": "Лимит CPU для тяжёлых задач",
    "below 100% the whole job gets tiny micro-pauses (works for any program)":
        "ниже 100% вся задача получает микропаузы (работает с любой программой)",
    "Start at login": "Запускать при входе в систему",
    "About my Mac": "Об этом Mac",
    "Phone push (ntfy.sh)…": "Push на телефон (ntfy.sh)...",
    "Enter a secret topic name. Install the ntfy app on your phone and subscribe to the same topic - pauses, kills and alarms will arrive as push notifications. Leave empty to disable.":
        "Введите секретное имя темы. Установите приложение ntfy на телефон и подпишитесь на ту же тему - паузы, завершения и тревоги придут как push. Пустое поле отключает.",
    "The topic name is the ONLY protection: anyone who knows or guesses it can read your alerts and send fake ones. Click Generate for a random unguessable name. On your phone install the ntfy.sh app (from ntfy.sh - mind the lookalike apps) and subscribe to the same topic. Leave empty to disable.":
        "Имя темы - ЕДИНСТВЕННАЯ защита: кто его знает или угадает, видит ваши оповещения и может слать поддельные. Нажмите «Сгенерировать», чтобы получить случайное имя. Установите на телефон приложение ntfy.sh (с сайта ntfy.sh - остерегайтесь похожих приложений) и подпишитесь на ту же тему. Пустое поле отключает.",
    "A project of the AIrON student research club.": "Проект научного кружка AIrON (AHE, Лодзь).",
    "Generate": "Сгенерировать",
    "Model:  %@": "Модель:  %@",
    "Chip:  %@": "Чип:  %@",
    "Cores:  %d performance + %d efficiency": "Ядра:  %d производительных + %d энергоэффективных",
    "RAM:  %d GB": "RAM:  %d ГБ",
    "Fans:  %d": "Вентиляторы:  %d",
    "macOS:  %@": "macOS:  %@",
    "Serial:  %@": "Серийный номер:  %@",
    "Battery cycles:  %@": "Циклы батареи:  %@",
    "Chip sensor (macmon):  %@": "Датчик чипа (macmon):  %@",
    "yes": "да",
    "no": "нет",
]

let ZH: [String: String] = [
    "Keep the Mac awake while heavy jobs run": "繁重任务运行时保持 Mac 唤醒",
    "Keeping the Mac awake (heavy job running)": "正在保持 Mac 唤醒（繁重任务运行中）",
    "no data - is coffee-paladin running?": "没有数据 - coffee-paladin 在运行吗？",
    "data is stale (%@) - the guard may have died": "数据已过期（%@）- 守护进程可能已停止",
    "the Mac shut down without warning: %@": "Mac 毫无预警地关机了：%@",
    "Battery:  %@": "电池：  %@",
    "Fans:  %@": "风扇：  %@",
    "stopped": "停转",
    "%d rpm": "%d 转/分", "%@ rpm": "%@ 转/分",
    "n/a": "无",
    "Draw:  %.1f W": "功耗：  %.1f W",
    "RAM:  %.1f / %.1f GB (%d%%)": "内存：  %.1f / %.1f GB（%d%%）",
    "swap %.2f GB": "交换 %.2f GB",
    "Disk:  %d / %d GB used (%d%%)": "磁盘：  已用 %d / %d GB（%d%%）",
    "Power:  %@": "电源：  %@",
    "AC adapter": "电源适配器",
    "battery %@": "电池 %@",
    "Load:  %.2f / %d cores": "负载：  %.2f / %d 核",
    "Throttling: CPU capped at %d%% speed": "降频：CPU 被限制到 %d%% 速度",
    "   readings: %.0f-%.0f C": "   测量值：%.0f-%.0f C",
    "rising %.1f C/min - about %.0f min to pause": "每分钟上升 %.1f C - 约 %.0f 分钟后暂停",
    "rising %.1f C/min": "每分钟上升 %.1f C",
    "Supervised jobs (safe-run):": "受监管的任务（safe-run）：",
    "Heating the most now (CPU ≈ heat):": "当前发热最多（CPU ≈ 热量）：",
    "Eating the most RAM:": "内存占用最多：",
    "Top CPU:  %@ (%d%%)": "CPU 占用最高：  %@（%d%%）",
    "Paused: %@": "已暂停：%@",
    "  (manual)": "（手动）",
    "State: %@": "状态：%@",
    "calm": "正常",
    "warm": "偏热",
    "HOT - paused": "过热 - 已暂停",
    "CRITICAL": "危急",
    "Chip thresholds:  pause %.0f C, kill %.0f C": "芯片阈值：  暂停 %.0f C，终止 %.0f C",
    "Today: %d x pause": "今天：%d 次暂停",
    ", %d x kill": "，%d 次终止",
    "Resume paused jobs": "恢复已暂停的任务",
    "Freeze all heavy jobs now": "立即暂停繁重任务",
    "A freeze is not a kill. The process stops between two instructions, keeps its memory and its open files, and carries on from the same place when you switch this off. It is safe.": "暂停不是终止。进程停在两条指令之间，保留内存和已打开的文件，你关掉开关后会从原地继续。是安全的。",
    "What a freeze does NOT protect: anything waiting on the network or watching a clock will notice the gap. A download or an upload can drop, a server can disconnect you, a video call freezes, a game stops responding.": "暂停不能保护什么：任何等待网络或盯着时钟的东西都会察觉到这段空白。下载或上传可能中断，服务器可能把你断开，视频通话会卡住，游戏会失去响应。",
    "The paladin will NEVER touch the system, Finder, your terminal or your AI agent.": "圣骑士绝不会碰系统、访达、你的终端或你的 AI 代理。",
    "Freeze all of them": "全部暂停",
    "Freeze heavy jobs now?": "现在暂停繁重任务？",
    "Nothing heavy is running right now. Anything that gets heavy will be frozen until you switch this back off.": "目前没有繁重任务在运行。之后出现的繁重任务都会被暂停，直到你关掉这个开关。",
    "Freeze": "暂停",
    "Pause jobs when the Mac overheats": "过热时暂停任务",
    "OFF - the Mac is only being watched": "已关闭 —— 仅在观察这台 Mac",
    "Show in the bar": "菜单栏显示内容",
    "Export report for a repair shop": "导出维修报告",
    "As PDF…": "PDF 格式...",
    "As plain text (TXT)…": "纯文本（TXT）...",
    "Show the guard log": "查看守护日志",
    "Quit coffee-paladin (protection stops)": "退出 coffee-paladin(保护将停止)",
    "Turn off thermal protection for this Mac?": "要关闭这台 Mac 的过热保护吗？",
    "The daemon and the menu bar both stop. Nothing will pause hot jobs until you start it again.":
        "守护进程和菜单栏都会停止。在你再次启动之前，没有任何东西会暂停过热的任务。",
    "Quit anyway": "仍然退出",
    "Cancel": "取消",
    "Chip temperature": "芯片温度",
    "GPU temperature": "GPU 温度",
    "Battery temperature": "电池温度",
    "Fan rpm": "风扇转速",
    "Power draw (W)": "功耗（W）",
    "RAM used": "内存占用",
    "Disk used": "磁盘占用",
    "Throttling marker": "降频标记",
    "Pause marker": "暂停标记",
    "Flame at critical": "菜单栏动画（火焰、风扇、咖啡杯）",
    "Like the paladin? Pass it on!": "喜欢圣骑士?转发一下!",
    "Share on X…": "分享到 X...",
    "Share by e-mail…": "通过邮件分享...",
    "Copy link with note": "复制链接和推荐语",
    "Star it on GitHub…": "在 GitHub 上点星...",
    "Is your Mac heating up with AI and renders? coffee-paladin watches the battery (temperature and charge), the chip (CPU) and the GPU. It pauses heavy jobs when the system overheats and resumes them by itself once the temperature drops, so you can sleep peacefully (literally!). Open source, free, for you:":
        "你的 Mac 在 AI 任务和渲染时发热?coffee-paladin 监控电池(温度和电量)、芯片(CPU)和 GPU。系统过热时自动暂停繁重任务,温度下降后自动恢复,让你安心入睡(字面意义上!)。开源免费,为你而做:",
    "Settings": "设置",
    "Chip pause threshold": "芯片温度高于此值时暂停",
    "Battery gate": "电量低于此值时暂停",
    "pause below this charge when unplugged": "未接电源时，繁重任务将等待充电",
    "TOO LOW - an idle M-series chip already sits at 40-55 C, the guard would pause constantly": "太低 - M 系列芯片空闲时已有 40-55 C，守护会不停暂停",
    "very conservative - a quiet, cool Mac, but long jobs will crawl": "非常保守 - 机器安静凉爽，但长任务会很慢",
    "conservative - good for a fanless Mac (Air, 12-inch)": "保守 - 适合无风扇的 Mac（Air）",
    "recommended - well below Apple's own throttling point (~100-108 C)": "推荐 - 明显低于 macOS 自身降频点（约 100-108 C）",
    "aggressive - close to the temperature at which macOS throttles by itself": "激进 - 接近 macOS 自动降频的温度",
    "Notifications": "通知",
    "Watch only, never touch processes (dry run)": "仅观察，不干预进程（dry run）",
    "resume at %.0f °C, terminate at %.0f C": "%.0f C 时恢复，%.0f C 时终止",
    "What does watch-only mode do?": "「仅观察」模式是什么？",
    "Report a problem (GitHub)…": "报告问题（GitHub）...",
    "Write to the author (GitHub)…": "给作者写信(GitHub)...",
    "Watch only (dry run)": "仅观察（dry run）",
    """
Protection is now OFF\n- coffee-paladin has entered watch-only mode.

It still measures everything (chip, GPU, battery, fans) and writes to the event log exactly \
what it WOULD do - "would pause ffmpeg (630% CPU)" - but it sends no signal and never touches \
a single process.

Use it to see whether the thresholds suit your machine before you let the paladin freeze real \
work. Open "Show the guard log" after a heavy job and you will know if it would have interfered \
too eagerly, or not soon enough.

Remember: while this switch is off, NOTHING protects the Mac.\nFlip it back on when you are done.
""": """
保护现已关闭
- coffee-paladin 已进入被动观察模式。

它仍然测量一切（芯片、GPU、电池、风扇），并把它本来会做的事原样写进日志：\
「本会暂停 ffmpeg（630% CPU）」，但不发送任何信号，也不碰任何进程。

这是为了在让圣骑士真正冻结工作之前，先确认阈值是否适合你的机器。跑完一个重任务后\
打开「查看守护日志」，你就会知道它是会插手得太急，还是反过来，太迟。

请记住：只要这个开关是关的，就没有任何东西在保护这台 Mac。
完成后请把它打开。
""",
    "WATCH-ONLY MODE - measuring and alerting, pausing nothing": "仅观察模式 - 只测量和提醒，不暂停任何任务",
    "Enable protection (pause heavy jobs when hot)": "启用保护（过热时暂停繁重任务）",
    "Language": "语言",
    "Sounds": "提示音",
    "Name this Mac in the fleet…": "为此 Mac 设置机群名称...",
    "e.g. render-01, studio-mini, mbp-14": "例如 render-01、studio-mini、mbp-14",
    "With five identical MacBooks the system hostname says nothing. This name shows in the fleet table and menu on every machine. Empty = system hostname.":
        "五台一样的 MacBook,系统主机名毫无意义。此名称会显示在每台机器的机群表和菜单中。留空 = 系统主机名。",
    "Buy me a double espresso…": "请我喝双份浓缩咖啡...",
    "Apple fleet": "Apple 机群",
    "battery": "电池",
    "paused": "已暂停",
    "STALE - not reporting": "未上报",
    "no fleet folder - run: fleet --setup": "没有机群文件夹 - 运行: fleet --setup",
    "no agent snapshots yet (agents publish about once a minute)":
        "还没有代理快照(代理约每分钟发布一次)",
    "now": "现在",
    "%d min ago": "%d 分钟前",
    "%d h ago": "%d 小时前",
    "The paladin stands guard. Choose how to begin:": "圣骑士开始站岗。选择如何开始:",
    "Enable protection": "启用保护",
    "Watch only for now": "暂时仅观察",
    "Load info": "负载信息",
    "Keep awake": "保持 Mac 唤醒",
    "Off": "关闭",
    "%d min": "%d 分钟",
    "%d h": "%d 小时",
    "Indefinitely": "无限期",
    "While an app is running": "当某个应用运行时",
    "While downloading (network active)": "下载期间(网络活跃)",
    "released automatically when the Mac gets hot": "Mac 变热时自动解除",
    "Keep-awake: %@ left": "保持唤醒:剩余 %@",
    "caffeinate holds for another %@": "caffeinate 还将保持 %@",
    "Heavy processes right now: %d": "当前繁重进程数:%d",
    "Measurement interval": "测量频率",
    "Pick the report period.": "选择报告时间段。",
    "Included: hardware, battery, sudden shutdowns, interventions, measurement timeline.":
        "报告含:硬件、电池、突然关机、干预、测量时间线。",
    "From:": "从:",
    "This topic will not work": "这个主题无法使用",
    "Use only letters, digits, _ and -, up to 64 characters. A space stops the push silently, and # or ? publish to a shorter topic than the one you typed.": "只能使用字母、数字、_ 和 -,最多 64 个字符。空格会让推送静默失败,而 # 或 ? 会发布到比你输入的更短的主题。",
    "First steps with the paladin": "圣骑士入门指南",
    "First steps…": "入门指南...",
    "WHAT IT CAN DO\n• The paladin watches the chip, the battery, the fans and the power source - by default a reading every 15 seconds.\n• When things get too hot, it FREEZES heavy processes instead of letting the Mac cook itself. The pause destroys nothing: the process stops mid-instruction and continues once the chip cools. Example? Measured: 89 °C → 60 °C in 19 seconds, no loss.\n• It finds the real culprit: CPU is counted across the whole process tree, so it also sees a script that spawns hundreds of short jobs while using almost nothing itself.\n• On battery below 10% it pauses long jobs - they resume when you plug in.\n• It keeps a black box: after a hard failure the last 8 readings survive. One click turns them into a report for a repair shop (should you ever need it).\n• Keep-awake - works like the well-known Caffeine or Amphetamine, but unlike them it comes with a fuse: the sleep lock is released the moment things run hot. Sleep is the fastest cooling there is.": "它能做什么\n• 圣骑士监控芯片、电池、风扇和电源 - 默认每15秒测量一次。\n• 过热时会冻结繁重进程,而不是让 Mac 煮熟自己。暂停不会破坏任何东西:进程原地停住,芯片冷却后从同一处继续。例子?实测:89 °C → 60 °C 只用19秒,零损失。\n• 找到真正的元凶:按整个进程树统计 CPU,连派生数百个短任务的脚本也看得见。\n• 电量低于10%时暂停长任务 - 插上电源后自动恢复。\n• 黑匣子:硬故障后保留最后8次测量,一键生成维修报告(以备不时之需)。\n• 保持唤醒 - 像知名的 Caffeine 或 Amphetamine 一样,但不同的是它带保险丝:一旦过热立即释放睡眠锁。睡眠是最快的降温方式。",
    "WHAT WILL HAPPEN\n• Your choice in the welcome window decides how you start.\n\n\"Watch only\" mode: the paladin measures, logs and alerts, but PAUSES NOTHING.\n\n\"Enable protection\" mode: it pauses at the defined thresholds.\n\nSwitching is easy - one switch at the top of the menu.\n\n• Default thresholds: pause at 85 °C, resume at 76 °C, gentle closing of processes at 90 °C - and only after 4 critical readings in a row. Above 90 °C for over a minute is an emergency: despite the pauses the chip still holds critical (something we could not pause is heating, or pausing was not enough to cool the chip). The process is then woken up and gets SIGTERM - a polite \"shut down\": it has a chance to save its state, close its files, clean up. That is why we call this termination \"gentle\".\n\nA fanless Mac (e.g. an Air or Neo) gets more careful parameters. The thresholds are always picked for YOUR machine: see menu > \"About my Mac\".\n\n• Notifications: on. Sounds: off (enable them in Settings). At the critical level a system banner breaks through everything - Focus and full-screen included.\n• The system, Finder, your terminal and your AI agent are on the never-touch list. The guard will not freeze the session working next to it.": "将会发生什么\n• 欢迎窗口的选择决定起点。\n\n「仅观察」模式:圣骑士测量、记录、警报,但不暂停任何进程。\n\n「启用保护」模式:按设定的阈值暂停。\n\n切换很简单 - 菜单顶部的一个开关。\n\n• 默认阈值:85 °C 暂停,76 °C 恢复,90 °C 温和关闭进程 - 且需连续4次危险读数。超过 90 °C 持续一分钟以上属于紧急情况:尽管已暂停,芯片仍处于危险级别(发热的是我们无法暂停的东西,或暂停不足以降温)。此时进程会被唤醒并收到 SIGTERM - 礼貌的「请关闭」:它有机会保存状态、关闭文件、清理现场。所以我们称这种终止为「温和」。\n\n无风扇的 Mac(如 Air 或 Neo)获得更保守的参数。阈值总是为你的机器挑选:见菜单 >「关于我的 Mac」。\n\n• 通知:开。声音:关(可在设置中打开)。危险级别时系统横幅总会弹出 - 专注模式和全屏也不例外。\n• 系统、Finder、终端和你的 AI 代理都在不可触碰清单上。守卫不会冻结在它身边工作的会话。",
    "WHAT YOU CAN SET\n• Chip pause threshold - a slider; resume and terminate recalculate themselves.\n• Measurement interval 5-30 s: more often = faster reaction, but costlier in CPU use.\n• Heavy jobs (safe-run): all cores (fast) or efficiency cores only (cool and quiet), plus a CPU limit of 50-100%.\n• Battery gate, signals, keep-awake, this Mac's name in the fleet.": "你可以设置\n• 芯片暂停阈值 - 滑块;恢复和终止自动换算。\n• 测量间隔 5-30 秒:更频繁 = 反应更快,但 CPU 开销更大。\n• 繁重任务(safe-run):全部核心(快)或仅能效核心(安静),外加 50-100% CPU 限制。\n• 电池阈值、信号、保持唤醒、这台 Mac 在机群中的名字。",
    "PHONE PUSH (ntfy)\n• Settings → \"Phone push (ntfy.sh)...\". The topic name is the ONLY protection: anyone who knows or guesses it can read your alerts and send fake ones. Click \"Generate\" - you get a random, unguessable one.\n• On your phone install the ntfy app from ntfy.sh - mind the lookalike apps - and subscribe to the same topic.\n• No account, no server of ours. It works over the internet, not WiFi: the 90 °C pause reaches your phone on a train, over LTE.": "手机推送(ntfy)\n• 设置 →「手机推送(ntfy.sh)...」。主题名是唯一的保护:知道或猜到的人能读你的警报并发送假消息。点「生成」获得随机名称。\n• 在手机上安装来自 ntfy.sh 的 ntfy 应用 - 谨防仿冒 - 并订阅同一主题。\n• 无需账户,无我们的服务器。走互联网而非 WiFi:90 °C 的暂停会通过 LTE 送达火车上的你。",
    "Enjoy your work!\nPaweł": "祝工作愉快!\nPaweł",
    "Sponsor on GitHub…": "在 GitHub 上赞助...",
    "Is your Mac heating up with AI and renders? coffee-paladin watches battery, chip and GPU temperatures. It pauses heavy jobs and resumes them by itself once the temperature drops.\n\nOpen source, free, for you:\n%@\n\n#panbookovsky #macbook #protect #temperature #guard":
        "你的 Mac 在 AI 任务和渲染时发热?coffee-paladin 监控电池、芯片和 GPU 温度。自动暂停繁重任务,温度下降后自动恢复。\n\n开源免费,为你而做:\n%@\n\n#panbookovsky #macbook #protect #temperature #guard",
    "you have to see this: coffee-paladin": "你一定要看看:coffee-paladin",
    "Hey,\n\nI found something you need on your Mac: coffee-paladin. It watches the chip, GPU and battery temperatures, and when things get hot it pauses heavy jobs and resumes them by itself once the machine cools down.\n\nIt is damn good, because the pause is lossless (the process freezes and continues from the same spot), it sends nothing anywhere, and it is free, open source:\n%@\n\nThe knight with the coffee in the attachment is its mascot.\n\nCheers!":
        "嘿!\n\n我发现了每台 Mac 都需要的东西:coffee-paladin。它监控芯片、GPU 和电池温度,过热时自动暂停繁重任务,冷却后自动恢复。\n\n它真的很棒:暂停是无损的(进程冻结后从原处继续),不向任何地方发送数据,免费开源:\n%@\n\n附件里拿着咖啡的骑士是它的吉祥物。\n\n再见!",
    "chip": "芯片", "fans": "风扇", "draw": "功耗", "state": "状态", "snapshot": "快照",
    "To:": "至:",
    "Everything on record": "全部记录",
    "Cores:  %d performance + %d efficiency  ·  Neural Engine: %d":
        "核心:  %d 性能 + %d 能效  ·  神经网络引擎: %d",
    "Disk: %d GB (%d%% free)": "磁盘: %d GB(%d%% 可用)",
    "max capacity: %d%%": "最大容量: %d%%",
    "Sensors:": "传感器:",
    "chip and GPU (macmon/IOReport):  %@": "芯片与 GPU(macmon/IOReport):  %@",
    "thermal state (Apple API):  %@": "热状态(Apple API):  %@",
    "battery (ioreg):  %@": "电池(ioreg):  %@",
    "CPU throttling (pmset):  %@": "CPU 降频(pmset):  %@",
    "limited warranty (est.): until %@": "保修(估计): 至 %@",
    "set up: %@": "配置于: %@",
    "Turns off banners, their sounds and phone push - one gate for all.":
        "关闭通知、其声音和手机推送——同一道闸门。",
    "Exception: the critical banner shouts regardless.":
        "例外:危险横幅无论如何都会警报。",
    "It is the ‹Pause jobs when the Mac overheats› switch: OFF = watch-only.":
        "即主开关‹过热时暂停任务›:关闭 = 仅观察。",
    "fastest reaction - the guard itself burns ~3.5% of one core all the time":
        "反应最快,但守卫自身持续占用约3.5%单核",
    "reacts up to 5 s sooner than default, costs ~1.8% of one core":
        "比默认快最多5秒,占用约1.8%单核",
    "default: good reaction at ~1.2% of one core":
        "默认:约1.2%单核,反应良好",
    "frugal - an automatic pause may come tens of seconds after the threshold":
        "省电,但自动暂停可能在超过阈值后数十秒才触发",
    "Keep-awake: while %@ is running": "保持唤醒:%@ 运行期间",
    "Keep-awake: while downloading": "保持唤醒:下载期间",
    "Keep-awake: indefinitely": "保持唤醒:无限期",
    "Heavy jobs (safe-run)": "繁重任务(safe-run)",
    "Efficiency cores only (cool and quiet)": "仅能效核心(凉爽安静)",
    "All cores (fast - the paladin still watches the temperature)":
        "全部核心(快 - 温度仍由圣骑士监控)",
    "CPU limit for heavy jobs": "繁重任务的 CPU 限制",
    "below 100% the whole job gets tiny micro-pauses (works for any program)":
        "低于 100% 时整个任务会得到微暂停(适用于任何程序)",
    "Start at login": "登录时启动",
    "About my Mac": "关于我的 Mac",
    "Phone push (ntfy.sh)…": "手机推送(ntfy.sh)...",
    "Enter a secret topic name. Install the ntfy app on your phone and subscribe to the same topic - pauses, kills and alarms will arrive as push notifications. Leave empty to disable.":
        "输入一个保密的主题名。在手机上安装 ntfy 应用并订阅同一主题 - 暂停、终止和警报会以推送形式送达。留空则禁用。",
    "The topic name is the ONLY protection: anyone who knows or guesses it can read your alerts and send fake ones. Click Generate for a random unguessable name. On your phone install the ntfy.sh app (from ntfy.sh - mind the lookalike apps) and subscribe to the same topic. Leave empty to disable.":
        "主题名是唯一的保护:知道或猜到它的人都能看到你的警报并发送伪造消息。点击「生成」获取随机且难以猜测的名称。在手机上安装 ntfy.sh 应用(来自 ntfy.sh, 谨防仿冒应用)并订阅同一主题。留空则禁用。",
    "A project of the AIrON student research club.": "AIrON 学生科研社团项目(罗兹 AHE)。",
    "Generate": "生成",
    "Model:  %@": "型号:  %@",
    "Chip:  %@": "芯片:  %@",
    "Cores:  %d performance + %d efficiency": "核心:  %d 性能 + %d 能效",
    "RAM:  %d GB": "内存:  %d GB",
    "Fans:  %d": "风扇:  %d",
    "macOS:  %@": "macOS:  %@",
    "Serial:  %@": "序列号:  %@",
    "Battery cycles:  %@": "电池循环:  %@",
    "Chip sensor (macmon):  %@": "芯片传感器(macmon):  %@",
    "yes": "是",
    "no": "否",
]

let ES: [String: String] = [
    "Keep the Mac awake while heavy jobs run": "Mantener el Mac despierto mientras corren tareas pesadas",
    "Keeping the Mac awake (heavy job running)": "Manteniendo el Mac despierto (tarea pesada en curso)",
    "no data - is coffee-paladin running?": "sin datos - ¿está funcionando coffee-paladin?",
    "data is stale (%@) - the guard may have died": "datos obsoletos (%@) - el guardián pudo detenerse",
    "the Mac shut down without warning: %@": "el Mac se apagó sin aviso: %@",
    "Battery:  %@": "Batería:  %@",
    "Fans:  %@": "Ventiladores:  %@",
    "stopped": "parado",
    "%d rpm": "%d rpm", "%@ rpm": "%@ rpm",
    "n/a": "n/d",
    "Draw:  %.1f W": "Consumo:  %.1f W",
    "RAM:  %.1f / %.1f GB (%d%%)": "RAM:  %.1f / %.1f GB (%d%%)",
    "swap %.2f GB": "swap %.2f GB",
    "Disk:  %d / %d GB used (%d%%)": "Disco:  %d / %d GB usados (%d%%)",
    "Power:  %@": "Alimentación:  %@",
    "AC adapter": "adaptador de corriente",
    "battery %@": "batería %@",
    "Load:  %.2f / %d cores": "Carga:  %.2f / %d núcleos",
    "Throttling: CPU capped at %d%% speed": "Estrangulamiento: CPU limitada al %d%% de velocidad",
    "   readings: %.0f-%.0f C": "   lecturas: %.0f-%.0f C",
    "rising %.1f C/min - about %.0f min to pause": "sube %.1f C/min - pausa en unos %.0f min",
    "rising %.1f C/min": "sube %.1f C/min",
    "Supervised jobs (safe-run):": "Tareas supervisadas (safe-run):",
    "Heating the most now (CPU ≈ heat):": "Lo que más calienta ahora (CPU ≈ calor):",
    "Eating the most RAM:": "Lo que más RAM consume:",
    "Top CPU:  %@ (%d%%)": "Mayor uso de CPU:  %@ (%d%%)",
    "Paused: %@": "En pausa: %@",
    "  (manual)": "  (manual)",
    "State: %@": "Estado: %@",
    "calm": "tranquilo",
    "warm": "templado",
    "HOT - paused": "CALIENTE - en pausa",
    "CRITICAL": "CRÍTICO",
    "Chip thresholds:  pause %.0f C, kill %.0f C": "Umbrales del chip:  pausa %.0f C, terminar %.0f C",
    "Today: %d x pause": "Hoy: %d x pausa",
    ", %d x kill": ", %d x terminación",
    "Resume paused jobs": "Reanudar tareas en pausa",
    "Freeze all heavy jobs now": "Pausar las tareas pesadas",
    "A freeze is not a kill. The process stops between two instructions, keeps its memory and its open files, and carries on from the same place when you switch this off. It is safe.": "Pausar no es matar. El proceso se detiene entre dos instrucciones, conserva su memoria y sus archivos abiertos, y sigue desde el mismo punto cuando desactivas esto. Es seguro.",
    "What a freeze does NOT protect: anything waiting on the network or watching a clock will notice the gap. A download or an upload can drop, a server can disconnect you, a video call freezes, a game stops responding.": "Lo que una pausa NO protege: todo lo que espera a la red o vigila un reloj notará el hueco. Una descarga o una subida puede cortarse, un servidor puede desconectarte, una videollamada se congela, un juego deja de responder.",
    "The paladin will NEVER touch the system, Finder, your terminal or your AI agent.": "El paladín NUNCA tocará el sistema, el Finder, tu terminal ni tu agente de IA.",
    "Freeze all of them": "Pausar todas",
    "Freeze heavy jobs now?": "¿Pausar ahora las tareas pesadas?",
    "Nothing heavy is running right now. Anything that gets heavy will be frozen until you switch this back off.": "Ahora mismo no hay nada pesado en marcha. Todo lo que se vuelva pesado quedará en pausa hasta que vuelvas a desactivar esto.",
    "Freeze": "Pausar",
    "Pause jobs when the Mac overheats": "Pausar tareas cuando el Mac se recalienta",
    "OFF - the Mac is only being watched": "DESACTIVADO: el Mac solo está siendo observado",
    "Show in the bar": "Mostrar en la barra",
    "Export report for a repair shop": "Informe para el servicio técnico",
    "As PDF…": "Como PDF...",
    "As plain text (TXT)…": "Como texto (TXT)...",
    "Show the guard log": "Ver el registro",
    "Quit coffee-paladin (protection stops)": "Salir de coffee-paladin (la protección se detiene)",
    "Turn off thermal protection for this Mac?": "¿Desactivar la protección térmica de este Mac?",
    "The daemon and the menu bar both stop. Nothing will pause hot jobs until you start it again.":
        "El demonio y la barra de menús se detienen. Nada pausará los trabajos calientes hasta que lo vuelvas a iniciar.",
    "Quit anyway": "Salir igualmente",
    "Cancel": "Cancelar",
    "Chip temperature": "Temperatura del chip",
    "GPU temperature": "Temperatura de la GPU",
    "Battery temperature": "Temperatura de la batería",
    "Fan rpm": "Revoluciones del ventilador",
    "Power draw (W)": "Consumo (W)",
    "RAM used": "RAM usada",
    "Disk used": "Disco usado",
    "Throttling marker": "Indicador de throttling",
    "Pause marker": "Indicador de pausa",
    "Flame at critical": "Animaciones en la barra (llama, ventilador, taza)",
    "Like the paladin? Pass it on!": "¿Te gusta el paladín? ¡Pásalo!",
    "Share on X…": "Compartir en X...",
    "Share by e-mail…": "Compartir por correo...",
    "Copy link with note": "Copiar enlace con nota",
    "Star it on GitHub…": "Dale una estrella en GitHub...",
    "Is your Mac heating up with AI and renders? coffee-paladin watches the battery (temperature and charge), the chip (CPU) and the GPU. It pauses heavy jobs when the system overheats and resumes them by itself once the temperature drops, so you can sleep peacefully (literally!). Open source, free, for you:":
        "¿Tu Mac se calienta con IA y renders? coffee-paladin vigila la batería (temperatura y carga), el chip (CPU) y la GPU. Pausa las tareas pesadas cuando el sistema se sobrecalienta y las reanuda solo cuando baja la temperatura, para que puedas dormir tranquilo (¡literalmente!). Open source, gratis, para ti:",
    "Settings": "Ajustes",
    "Chip pause threshold": "Pausar por encima de",
    "Battery gate": "Pausar con batería por debajo de",
    "pause below this charge when unplugged": "sin adaptador, las tareas pesadas esperarán al cargador",
    "TOO LOW - an idle M-series chip already sits at 40-55 C, the guard would pause constantly": "DEMASIADO BAJO - un chip M en reposo ya está a 40-55 C, pausaría sin parar",
    "very conservative - a quiet, cool Mac, but long jobs will crawl": "muy conservador - un Mac frío y silencioso, pero las tareas largas irán lentas",
    "conservative - good for a fanless Mac (Air, 12-inch)": "conservador - adecuado para un Mac sin ventiladores (Air)",
    "recommended - well below Apple's own throttling point (~100-108 C)": "recomendado - muy por debajo del throttling de macOS (~100-108 C)",
    "aggressive - close to the temperature at which macOS throttles by itself": "agresivo - cerca de la temperatura a la que macOS reduce la frecuencia",
    "Notifications": "Notificaciones",
    "Watch only, never touch processes (dry run)": "Solo observar, no tocar procesos (dry run)",
    "resume at %.0f °C, terminate at %.0f C": "reanuda a %.0f C, termina a %.0f C",
    "What does watch-only mode do?": "¿Qué hace el modo de solo observación?",
    "Report a problem (GitHub)…": "Informar de un problema (GitHub)...",
    "Write to the author (GitHub)…": "Escribir al autor (GitHub)...",
    "Watch only (dry run)": "Solo observación (dry run)",
    """
Protection is now OFF\n- coffee-paladin has entered watch-only mode.

It still measures everything (chip, GPU, battery, fans) and writes to the event log exactly \
what it WOULD do - "would pause ffmpeg (630% CPU)" - but it sends no signal and never touches \
a single process.

Use it to see whether the thresholds suit your machine before you let the paladin freeze real \
work. Open "Show the guard log" after a heavy job and you will know if it would have interfered \
too eagerly, or not soon enough.

Remember: while this switch is off, NOTHING protects the Mac.\nFlip it back on when you are done.
""": """
La protección está AHORA DESACTIVADA
- coffee-paladin ha entrado en modo de observación pasiva.

Sigue midiendo todo (chip, GPU, batería, ventiladores) y anota en el registro \
exactamente lo que HARÍA: «pausaría ffmpeg (630% CPU)», pero no envía ninguna \
señal ni toca ningún proceso.

Sirve para comprobar si los umbrales encajan con tu máquina antes de dejar que el \
paladín congele trabajo real. Después de una tarea pesada abre «Ver el registro del \
guardián» y sabrás si se entrometería con demasiado celo o, al revés, demasiado tarde.

Recuerda: mientras este interruptor esté apagado, NADA protege el Mac.
Vuelve a activarlo cuando termines.
""",
    "WATCH-ONLY MODE - measuring and alerting, pausing nothing": "MODO OBSERVACIÓN - mido y aviso, no pauso nada",
    "Enable protection (pause heavy jobs when hot)": "Activar la protección (pausar tareas pesadas al calentarse)",
    "Language": "Idioma",
    "Sounds": "Sonidos",
    "Name this Mac in the fleet…": "Nombra este Mac en la flota...",
    "e.g. render-01, studio-mini, mbp-14": "p. ej. render-01, studio-mini, mbp-14",
    "With five identical MacBooks the system hostname says nothing. This name shows in the fleet table and menu on every machine. Empty = system hostname.":
        "Con cinco MacBooks idénticos el nombre del sistema no dice nada. Este nombre aparece en la tabla de flota y el menú de cada máquina. Vacío = nombre del sistema.",
    "Apple fleet": "Flota Apple",
    "battery": "batería",
    "paused": "en pausa",
    "STALE - not reporting": "SIN REPORTAR",
    "no fleet folder - run: fleet --setup": "sin carpeta de flota - ejecuta: fleet --setup",
    "no agent snapshots yet (agents publish about once a minute)":
        "aún no hay instantáneas de agentes (publican una vez por minuto)",
    "now": "ahora",
    "%d min ago": "hace %d min",
    "%d h ago": "hace %d h",
    "Buy me a double espresso…": "Invítame a un espresso doble...",
    "The paladin stands guard. Choose how to begin:": "El paladín monta guardia. Elige cómo empezar:",
    "Enable protection": "Activar protección",
    "Watch only for now": "Solo observar por ahora",
    "Load info": "Información de carga",
    "Keep awake": "Mantener el Mac despierto",
    "Off": "Apagar",
    "%d min": "%d min",
    "%d h": "%d h",
    "Indefinitely": "Indefinidamente",
    "While an app is running": "Mientras corra una aplicación",
    "While downloading (network active)": "Mientras se descarga (red activa)",
    "released automatically when the Mac gets hot": "se libera solo cuando el Mac se calienta",
    "Keep-awake: %@ left": "Despierto: quedan %@",
    "caffeinate holds for another %@": "caffeinate aguanta %@ más",
    "Heavy processes right now: %d": "Procesos pesados ahora: %d",
    "Measurement interval": "Frecuencia de medición",
    "Pick the report period.": "Elige el periodo del informe.",
    "Included: hardware, battery, sudden shutdowns, interventions, measurement timeline.":
        "Incluye: hardware, batería, apagados repentinos, intervenciones, línea de mediciones.",
    "From:": "Desde:",
    "This topic will not work": "Este tema no funcionará",
    "Use only letters, digits, _ and -, up to 64 characters. A space stops the push silently, and # or ? publish to a shorter topic than the one you typed.": "Usa solo letras, dígitos, _ y -, hasta 64 caracteres. Un espacio bloquea el push en silencio, y # o ? publican en un tema más corto del que escribiste.",
    "First steps with the paladin": "Primeros pasos con el paladín",
    "First steps…": "Primeros pasos...",
    "WHAT IT CAN DO\n• The paladin watches the chip, the battery, the fans and the power source - by default a reading every 15 seconds.\n• When things get too hot, it FREEZES heavy processes instead of letting the Mac cook itself. The pause destroys nothing: the process stops mid-instruction and continues once the chip cools. Example? Measured: 89 °C → 60 °C in 19 seconds, no loss.\n• It finds the real culprit: CPU is counted across the whole process tree, so it also sees a script that spawns hundreds of short jobs while using almost nothing itself.\n• On battery below 10% it pauses long jobs - they resume when you plug in.\n• It keeps a black box: after a hard failure the last 8 readings survive. One click turns them into a report for a repair shop (should you ever need it).\n• Keep-awake - works like the well-known Caffeine or Amphetamine, but unlike them it comes with a fuse: the sleep lock is released the moment things run hot. Sleep is the fastest cooling there is.": "CO POTRAFI\n• Paladyn pilnuje chipa, baterii, wentylatorów i zasilania – domyślny pomiar co 15 sekund.\n• Gdy robi się za gorąco, ZAMRAŻA ciężkie procesy zamiast pozwolić Macowi się ugotować. Pauza niczego nie niszczy: proces staje w miejscu i rusza dalej, gdy chip ostygnie. Przykład? Zmierzone: 89 °C → 60 °C w 19 sekund, obliczenia bez strat.\n• Znajduje prawdziwego winowajcę: liczy CPU całego drzewa procesów, więc widzi też skrypt, który odpala setki krótkich zadań i sam prawie nic nie zużywa.\n• Na baterii poniżej 10% wstrzymuje długie obliczenia - wznowi po podpięciu ładowarki.\n• Prowadzi czarną skrzynkę: po twardej awarii zostaje 8 ostatnich pomiarów. Jednym kliknięciem złożysz z tego raport dla serwisu (w razie potrzeby).\n• „Nie usypiaj Maca\" – działa jak znane programy Caffeine czy Amphetamine, ale w odróżnieniu od nich robi to z bezpiecznikiem: blokada snu puszcza w momencie, gdy robi się gorąco. Sen chłodzi najszybciej.",
    "WHAT WILL HAPPEN\n• Your choice in the welcome window decides how you start.\n\n\"Watch only\" mode: the paladin measures, logs and alerts, but PAUSES NOTHING.\n\n\"Enable protection\" mode: it pauses at the defined thresholds.\n\nSwitching is easy - one switch at the top of the menu.\n\n• Default thresholds: pause at 85 °C, resume at 76 °C, gentle closing of processes at 90 °C - and only after 4 critical readings in a row. Above 90 °C for over a minute is an emergency: despite the pauses the chip still holds critical (something we could not pause is heating, or pausing was not enough to cool the chip). The process is then woken up and gets SIGTERM - a polite \"shut down\": it has a chance to save its state, close its files, clean up. That is why we call this termination \"gentle\".\n\nA fanless Mac (e.g. an Air or Neo) gets more careful parameters. The thresholds are always picked for YOUR machine: see menu > \"About my Mac\".\n\n• Notifications: on. Sounds: off (enable them in Settings). At the critical level a system banner breaks through everything - Focus and full-screen included.\n• The system, Finder, your terminal and your AI agent are on the never-touch list. The guard will not freeze the session working next to it.": "CO SIĘ BĘDZIE DZIAŁO\n• Twój wybór z okna powitalnego decyduje o starcie.\n\nTryb „Tylko obserwuj\": paladyn mierzy, loguje i alarmuje, ale NICZEGO NIE WSTRZYMUJE.\n\nTryb „Włącz ochronę\": pauzuje na zdefiniowanych progach.\n\nTryby przełączysz łatwo – to jeden switch na górze menu.\n\n• Domyślne progi: pauza przy 85 °C, wznowienie przy 76 °C, łagodne zamknięcie procesów przy 90 °C - i to dopiero po 4 krytycznych odczytach z rzędu. Ponad 90 °C przez ponad 1 minutę to sytuacja awaryjna: mimo pauzowania chip dalej trzyma poziom krytyczny (czyli grzeje coś, czego nie mogliśmy zapauzować, albo pauza nie wystarczyła do chłodzenia chipa). Wtedy proces jest budzony i dostaje SIGTERM — grzeczne „zamknij się\": ma szansę zapisać stan, domknąć pliki, posprzątać. Dlatego ubicie go traktujemy jako „łagodne\".\n\nMac bez wentylatora (np. Air lub Neo) dostaje ostrożniejsze parametry. Progi zawsze są dobrane dla TWOJEJ maszyny: zobacz w menu > „O moim Macu\".\n\n• Powiadomienia: włączone. Dźwięki: wyłączone (włączysz w Ustawieniach). Przy poziomie krytycznym baner systemowy przebija się zawsze - nawet przez Skupienie i pełny ekran.\n• System, Finder, terminal i Twój agent AI są na liście nietykalnych. Strażnik nie zamrozi sesji, która przy nim pracuje.",
    "WHAT YOU CAN SET\n• Chip pause threshold - a slider; resume and terminate recalculate themselves.\n• Measurement interval 5-30 s: more often = faster reaction, but costlier in CPU use.\n• Heavy jobs (safe-run): all cores (fast) or efficiency cores only (cool and quiet), plus a CPU limit of 50-100%.\n• Battery gate, signals, keep-awake, this Mac's name in the fleet.": "CO MOŻESZ USTAWIĆ\n• Próg pauzy chipa - suwak; wznowienie i ubicie przeliczają się same.\n• Interwał pomiaru 5-30 s: częściej = szybsza reakcja, ale drożej w użyciu CPU.\n• Ciężkie zadania (safe-run): wszystkie rdzenie (szybko) albo tylko E-cores (chłodno i cicho), do tego limit CPU 50-100%.\n• Bramka baterii, sygnały, „Nie usypiaj\", nazwa tego Maca we flocie.",
    "PHONE PUSH (ntfy)\n• Settings → \"Phone push (ntfy.sh)...\". The topic name is the ONLY protection: anyone who knows or guesses it can read your alerts and send fake ones. Click \"Generate\" - you get a random, unguessable one.\n• On your phone install the ntfy app from ntfy.sh - mind the lookalike apps - and subscribe to the same topic.\n• No account, no server of ours. It works over the internet, not WiFi: the 90 °C pause reaches your phone on a train, over LTE.": "PUSH AL TELÉFONO (ntfy)\n• Ajustes → «Push al teléfono (ntfy.sh)...». El nombre del tema es la ÚNICA protección: quien lo conozca puede leer tus alertas y enviar falsas. Pulsa «Generar» - obtienes uno aleatorio.\n• Instala en el teléfono la app ntfy desde ntfy.sh - cuidado con las imitaciones - y suscríbete al mismo tema.\n• Sin cuenta y sin servidor nuestro. Funciona por internet: la pausa de 90 °C llega a tu teléfono en el tren, por LTE.",
    "Enjoy your work!\nPaweł": "¡Que disfrutes del trabajo!\nPaweł",
    "Sponsor on GitHub…": "Patrocinar en GitHub...",
    "Is your Mac heating up with AI and renders? coffee-paladin watches battery, chip and GPU temperatures. It pauses heavy jobs and resumes them by itself once the temperature drops.\n\nOpen source, free, for you:\n%@\n\n#panbookovsky #macbook #protect #temperature #guard":
        "¿Tu Mac se calienta con IA y renders? coffee-paladin vigila la temperatura de batería, chip y GPU. Pausa las tareas pesadas y las reanuda solo cuando baja la temperatura.\n\nOpen source, gratis, para ti:\n%@\n\n#panbookovsky #macbook #protect #temperature #guard",
    "you have to see this: coffee-paladin": "tienes que ver esto: coffee-paladin",
    "Hey,\n\nI found something you need on your Mac: coffee-paladin. It watches the chip, GPU and battery temperatures, and when things get hot it pauses heavy jobs and resumes them by itself once the machine cools down.\n\nIt is damn good, because the pause is lossless (the process freezes and continues from the same spot), it sends nothing anywhere, and it is free, open source:\n%@\n\nThe knight with the coffee in the attachment is its mascot.\n\nCheers!":
        "¡Hola!\n\nEncontré algo que necesitas en tu Mac: coffee-paladin. Vigila la temperatura del chip, la GPU y la batería, y cuando hay calor pausa las tareas pesadas y las reanuda solo al enfriarse.\n\nEs buenísimo: la pausa no pierde nada (el proceso se congela y sigue desde el mismo punto), no envía nada a ningún sitio y es gratis, open source:\n%@\n\nEl caballero con café del adjunto es su mascota.\n\n¡Saludos!",
    "chip": "chip", "fans": "ventiladores", "draw": "consumo", "state": "estado", "snapshot": "instantánea",
    "To:": "Hasta:",
    "Everything on record": "Todo lo registrado",
    "Cores:  %d performance + %d efficiency  ·  Neural Engine: %d":
        "Núcleos:  %d de rendimiento + %d eficientes  ·  Neural Engine: %d",
    "Disk: %d GB (%d%% free)": "Disco: %d GB (%d%% libre)",
    "max capacity: %d%%": "capacidad máx.: %d%%",
    "Sensors:": "Sensores:",
    "chip and GPU (macmon/IOReport):  %@": "chip y GPU (macmon/IOReport):  %@",
    "thermal state (Apple API):  %@": "estado térmico (API de Apple):  %@",
    "battery (ioreg):  %@": "batería (ioreg):  %@",
    "CPU throttling (pmset):  %@": "limitación de CPU (pmset):  %@",
    "limited warranty (est.): until %@": "garantía (est.): hasta %@",
    "set up: %@": "configurado: %@",
    "Turns off banners, their sounds and phone push - one gate for all.":
        "Apaga avisos, sus sonidos y el push al móvil: una sola puerta para todo.",
    "Exception: the critical banner shouts regardless.":
        "Excepción: el banner crítico grita igualmente.",
    "It is the ‹Pause jobs when the Mac overheats› switch: OFF = watch-only.":
        "Es el estado del interruptor ‹Pausar al sobrecalentarse›: apagado = solo observación.",
    "fastest reaction - the guard itself burns ~3.5% of one core all the time":
        "reacción más rápida, pero el guardián quema ~3,5% de un núcleo sin parar",
    "reacts up to 5 s sooner than default, costs ~1.8% of one core":
        "reacciona hasta 5 s antes, cuesta ~1,8% de un núcleo",
    "default: good reaction at ~1.2% of one core":
        "por defecto: buena reacción con ~1,2% de un núcleo",
    "frugal - an automatic pause may come tens of seconds after the threshold":
        "ahorrador, pero la pausa automática puede llegar decenas de segundos tras el umbral",
    "Keep-awake: while %@ is running": "Despierto: mientras corre %@",
    "Keep-awake: while downloading": "Despierto: mientras se descarga",
    "Keep-awake: indefinitely": "Despierto: indefinidamente",
    "Heavy jobs (safe-run)": "Tareas pesadas (safe-run)",
    "Efficiency cores only (cool and quiet)": "Solo núcleos de eficiencia (frío y silencioso)",
    "All cores (fast - the paladin still watches the temperature)":
        "Todos los núcleos (rápido - el paladín sigue vigilando la temperatura)",
    "CPU limit for heavy jobs": "Límite de CPU para tareas pesadas",
    "below 100% the whole job gets tiny micro-pauses (works for any program)":
        "por debajo del 100% la tarea recibe micropausas (funciona con cualquier programa)",
    "Start at login": "Iniciar al iniciar sesión",
    "About my Mac": "Acerca de mi Mac",
    "Phone push (ntfy.sh)…": "Push al teléfono (ntfy.sh)...",
    "Enter a secret topic name. Install the ntfy app on your phone and subscribe to the same topic - pauses, kills and alarms will arrive as push notifications. Leave empty to disable.":
        "Escribe un nombre de tema secreto. Instala la app ntfy en el teléfono y suscríbete al mismo tema: pausas, terminaciones y alarmas llegarán como push. Vacío = desactivado.",
    "The topic name is the ONLY protection: anyone who knows or guesses it can read your alerts and send fake ones. Click Generate for a random unguessable name. On your phone install the ntfy.sh app (from ntfy.sh - mind the lookalike apps) and subscribe to the same topic. Leave empty to disable.":
        "El nombre del tema es la ÚNICA protección: quien lo conozca o adivine verá tus alertas y podrá enviar falsas. Pulsa Generar para obtener un nombre aleatorio. Instala en el teléfono la app ntfy.sh (de ntfy.sh, cuidado con las imitaciones) y suscríbete al mismo tema. Vacío = desactivado.",
    "A project of the AIrON student research club.": "Proyecto del club científico AIrON (AHE, Łódź).",
    "Generate": "Generar",
    "Model:  %@": "Modelo:  %@",
    "Chip:  %@": "Chip:  %@",
    "Cores:  %d performance + %d efficiency": "Núcleos:  %d de rendimiento + %d de eficiencia",
    "RAM:  %d GB": "RAM:  %d GB",
    "Fans:  %d": "Ventiladores:  %d",
    "macOS:  %@": "macOS:  %@",
    "Serial:  %@": "Número de serie:  %@",
    "Battery cycles:  %@": "Ciclos de batería:  %@",
    "Chip sensor (macmon):  %@": "Sensor del chip (macmon):  %@",
    "yes": "sí",
    "no": "no",
]

let DICTS: [String: [String: String]] = ["pl": PL, "ru": RU, "zh": ZH, "es": ES]

func T(_ s: String) -> String { DICTS[lang]?[s] ?? s }

// MARK: - icons

// Kawa = filizanka (cup.and.saucer) — swiadomy wybor Pawla po probie z "mug".
let MUG = "cup.and.saucer"
let MUG_FILL = "cup.and.saucer.fill"

/// Male logo "app-icon style" rysowane w locie: squircle z gradientem i bialym termometrem.
/// Zadnych plikow zasobow — pasek zostaje jednym samowystarczalnym plikiem Swift.
func makeLogo(_ size: CGFloat = 22) -> NSImage {
    let img = NSImage(size: NSSize(width: size, height: size))
    img.lockFocus()
    let rect = NSRect(x: 0, y: 0, width: size, height: size)
    let path = NSBezierPath(roundedRect: rect, xRadius: size * 0.24, yRadius: size * 0.24)
    NSGradient(starting: NSColor(calibratedRed: 1.00, green: 0.45, blue: 0.20, alpha: 1),
               ending: NSColor(calibratedRed: 0.82, green: 0.10, blue: 0.16, alpha: 1))?
        .draw(in: path, angle: -90)
    if let sym = NSImage(systemSymbolName: "thermometer.medium", accessibilityDescription: nil) {
        let cfg = NSImage.SymbolConfiguration(pointSize: size * 0.60, weight: .semibold)
            .applying(NSImage.SymbolConfiguration(paletteColors: [.white]))
        let s = sym.withSymbolConfiguration(cfg) ?? sym
        let sz = s.size
        s.draw(in: NSRect(x: (size - sz.width) / 2, y: (size - sz.height) / 2,
                          width: sz.width, height: sz.height))
    }
    img.unlockFocus()
    return img
}

/// Wlasne logo uzytkownika: ~/.coffee-paladin/logo.png (czarny znak na przezroczystym tle).
/// isTemplate sprawia, ze macOS sam przebarwia je na kolor motywu (jasny/ciemny).
func customLogo() -> NSImage? {
    guard let img = NSImage(contentsOfFile: base + "/logo.png") else { return nil }
    img.isTemplate = true
    return img
}


// MARK: - powitanie paladyna (pierwsze uruchomienie)

let PALADIN_FRAMES: [String] = [
    "            \u{2584}\u{2584}                \n          \u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}              \n         \u{2588}\u{2593}\u{2593}\u{2593}\u{2593}\u{2593}\u{2593}\u{2588}             \n         \u{2588}\u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}\u{2588}             \n         \u{2588}\u{2580}\u{2580}\u{2580}\u{2580}\u{2580}\u{2580}\u{2588}      \u{2591}      \n       \u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584} \u{2591}       \n  \u{2584}\u{2584}\u{2584}\u{2584}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2593}\u{2588}          \n  \u{2588}\u{2593}\u{2593}\u{2588}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2593}\u{2588} \u{258C}\u{2584}\u{2584}\u{2590}     \n  \u{2588}\u{2593}\u{2593}\u{2588} \u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}  \u{2588}     \n  \u{2588}\u{2593}\u{2593}\u{2588}  \u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}   \u{2580}\u{2580}\u{2580}\u{2580}     \n   \u{2580}\u{2580}    \u{2588}\u{2588}\u{2588}  \u{2588}\u{2588}\u{2588}             \n         \u{2588}\u{2588}\u{2588}  \u{2588}\u{2588}\u{2588}             \n        \u{2588}\u{2588}\u{2588}\u{2588} \u{2588}\u{2588}\u{2588}\u{2588}             \n                              \n                              \n                              ",
    "            \u{2584}\u{2584}                \n          \u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}              \n         \u{2588}\u{2593}\u{2593}\u{2593}\u{2593}\u{2593}\u{2593}\u{2588}             \n         \u{2588}\u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}\u{2588}      \u{2591}      \n         \u{2588}\u{2580}\u{2580}\u{2580}\u{2580}\u{2580}\u{2580}\u{2588}     \u{2591}       \n       \u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}  \u{2591}      \n  \u{2584}\u{2584}\u{2584}\u{2584}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2593}\u{2588}          \n  \u{2588}\u{2593}\u{2593}\u{2588}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2593}\u{2588} \u{258C}\u{2584}\u{2584}\u{2590}     \n  \u{2588}\u{2593}\u{2593}\u{2588} \u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}  \u{2588}     \n  \u{2588}\u{2593}\u{2593}\u{2588}  \u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}   \u{2580}\u{2580}\u{2580}\u{2580}     \n   \u{2580}\u{2580}    \u{2588}\u{2588}\u{2588}  \u{2588}\u{2588}\u{2588}             \n         \u{2588}\u{2588}\u{2588}  \u{2588}\u{2588}\u{2588}             \n        \u{2588}\u{2588}\u{2588}\u{2588} \u{2588}\u{2588}\u{2588}\u{2588}             \n                              \n                              \n                              ",
    "            \u{2584}\u{2584}                \n          \u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}              \n         \u{2588}\u{2593}\u{2593}\u{2593}\u{2593}\u{2593}\u{2593}\u{2588}     \u{2591}       \n         \u{2588}\u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}\u{2588}      \u{2591}      \n         \u{2588}\u{2580}\u{2580}\u{2580}\u{2580}\u{2580}\u{2580}\u{2588}     \u{2591}       \n       \u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}         \n  \u{2584}\u{2584}\u{2584}\u{2584}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2593}\u{2588} \u{258C}\u{2584}\u{2584}\u{2590}     \n  \u{2588}\u{2593}\u{2593}\u{2588}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}  \u{2588}     \n  \u{2588}\u{2593}\u{2593}\u{2588} \u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}  \u{2580}\u{2580}\u{2580}\u{2580}     \n  \u{2588}\u{2593}\u{2593}\u{2588}  \u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}            \n   \u{2580}\u{2580}    \u{2588}\u{2588}\u{2588}  \u{2588}\u{2588}\u{2588}             \n         \u{2588}\u{2588}\u{2588}  \u{2588}\u{2588}\u{2588}             \n        \u{2588}\u{2588}\u{2588}\u{2588} \u{2588}\u{2588}\u{2588}\u{2588}             \n                              \n                              \n                              ",
    "            \u{2584}\u{2584}                \n          \u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}              \n         \u{2588}\u{2593}\u{2593}\u{2593}\u{2593}\u{2593}\u{2593}\u{2588}      \u{2591}      \n         \u{2588}\u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}\u{2588}     \u{2591}       \n         \u{2588}\u{2580}\u{2580}\u{2580}\u{2580}\u{2580}\u{2580}\u{2588}             \n       \u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}\u{258C}\u{2584}\u{2584}\u{2590}     \n  \u{2584}\u{2584}\u{2584}\u{2584}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}  \u{2588}     \n  \u{2588}\u{2593}\u{2593}\u{2588}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2593}\u{2588} \u{2580}\u{2580}\u{2580}\u{2580}     \n  \u{2588}\u{2593}\u{2593}\u{2588} \u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}           \n  \u{2588}\u{2593}\u{2593}\u{2588}  \u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}            \n   \u{2580}\u{2580}    \u{2588}\u{2588}\u{2588}  \u{2588}\u{2588}\u{2588}             \n         \u{2588}\u{2588}\u{2588}  \u{2588}\u{2588}\u{2588}             \n        \u{2588}\u{2588}\u{2588}\u{2588} \u{2588}\u{2588}\u{2588}\u{2588}             \n                              \n                              \n                              ",
    "            \u{2584}\u{2584}         \u{2591}      \n          \u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}      \u{2591}       \n         \u{2588}\u{2593}\u{2593}\u{2593}\u{2593}\u{2593}\u{2593}\u{2588}      \u{2591}      \n         \u{2588} \u{2588}\u{2588}\u{2588}\u{2588} \u{2588}             \n         \u{2588}\u{2580}\u{2580}\u{2580}\u{2580}\u{2580}\u{2580}\u{2588}    \u{258C}\u{2584}\u{2584}\u{2590}     \n       \u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}  \u{2588}     \n  \u{2584}\u{2584}\u{2584}\u{2584}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2593}\u{2588} \u{2580}\u{2580}\u{2580}\u{2580}     \n  \u{2588}\u{2593}\u{2593}\u{2588}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2593}\u{2588}          \n  \u{2588}\u{2593}\u{2593}\u{2588} \u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}           \n  \u{2588}\u{2593}\u{2593}\u{2588}  \u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}            \n   \u{2580}\u{2580}    \u{2588}\u{2588}\u{2588}  \u{2588}\u{2588}\u{2588}             \n         \u{2588}\u{2588}\u{2588}  \u{2588}\u{2588}\u{2588}             \n        \u{2588}\u{2588}\u{2588}\u{2588} \u{2588}\u{2588}\u{2588}\u{2588}             \n                              \n                              \n                              ",
    "            \u{2584}\u{2584}        \u{2591}       \n          \u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}       \u{2591}      \n         \u{2588}\u{2593}\u{2593}\u{2593}\u{2593}\u{2593}\u{2593}\u{2588}     \u{2591}       \n         \u{2588} \u{2588}\u{2588}\u{2588}\u{2588} \u{2588}             \n         \u{2588}\u{2580}\u{2580}\u{2580}\u{2580}\u{2580}\u{2580}\u{2588}    \u{258C}\u{2584}\u{2584}\u{2590}     \n       \u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}  \u{2588}     \n  \u{2584}\u{2584}\u{2584}\u{2584}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2593}\u{2588} \u{2580}\u{2580}\u{2580}\u{2580}     \n  \u{2588}\u{2593}\u{2593}\u{2588}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2593}\u{2588}          \n  \u{2588}\u{2593}\u{2593}\u{2588} \u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}           \n  \u{2588}\u{2593}\u{2593}\u{2588}  \u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}            \n   \u{2580}\u{2580}    \u{2588}\u{2588}\u{2588}  \u{2588}\u{2588}\u{2588}             \n         \u{2588}\u{2588}\u{2588}  \u{2588}\u{2588}\u{2588}             \n        \u{2588}\u{2588}\u{2588}\u{2588} \u{2588}\u{2588}\u{2588}\u{2588}             \n                              \n                              \n                              ",
    "            \u{2584}\u{2584}                \n          \u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}              \n         \u{2588}\u{2593}\u{2593}\u{2593}\u{2593}\u{2593}\u{2593}\u{2588}             \n         \u{2588}\u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}\u{2588}      \u{2591}      \n         \u{2588}\u{2580}\u{2580}\u{2580}\u{2580}\u{2580}\u{2580}\u{2588}     \u{2591}       \n       \u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}         \n  \u{2584}\u{2584}\u{2584}\u{2584}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2593}\u{2588} \u{258C}\u{2584}\u{2584}\u{2590}     \n  \u{2588}\u{2593}\u{2593}\u{2588}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}  \u{2588}     \n  \u{2588}\u{2593}\u{2593}\u{2588} \u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}  \u{2580}\u{2580}\u{2580}\u{2580}     \n  \u{2588}\u{2593}\u{2593}\u{2588}  \u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}            \n   \u{2580}\u{2580}    \u{2588}\u{2588}\u{2588}  \u{2588}\u{2588}\u{2588}             \n         \u{2588}\u{2588}\u{2588}  \u{2588}\u{2588}\u{2588}             \n        \u{2588}\u{2588}\u{2588}\u{2588} \u{2588}\u{2588}\u{2588}\u{2588}             \n                              \n                              \n                              ",
    "            \u{2584}\u{2584}                \n          \u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}              \n         \u{2588}\u{2593}\u{2593}\u{2593}\u{2593}\u{2593}\u{2593}\u{2588}             \n         \u{2588}\u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}\u{2588}      \u{2591}      \n         \u{2588}\u{2580}\u{2580}\u{2580}\u{2580}\u{2580}\u{2580}\u{2588}     \u{2591}       \n       \u{2584}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2584}  \u{2591}      \n  \u{2584}\u{2584}\u{2584}\u{2584}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2593}\u{2588}          \n  \u{2588}\u{2593}\u{2593}\u{2588}\u{2588}\u{2593}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2593}\u{2588} \u{258C}\u{2584}\u{2584}\u{2590}     \n  \u{2588}\u{2593}\u{2593}\u{2588} \u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}  \u{2588}     \n  \u{2588}\u{2593}\u{2593}\u{2588}  \u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}\u{2588}   \u{2580}\u{2580}\u{2580}\u{2580}     \n   \u{2580}\u{2580}    \u{2588}\u{2588}\u{2588}  \u{2588}\u{2588}\u{2588}             \n         \u{2588}\u{2588}\u{2588}  \u{2588}\u{2588}\u{2588}             \n        \u{2588}\u{2588}\u{2588}\u{2588} \u{2588}\u{2588}\u{2588}\u{2588}             \n                              \n                              \n                              ",
]

let MOTTO = "Shield the Process, Sip the Coffee"

/// Okno powitalne: raz, przy pierwszym uruchomieniu paska. Monochromatyczny paladyn
/// (labelColor - sam gra z jasnym/ciemnym motywem), vibrancy, wybor trybu na start.
final class Welcome: NSObject {
    static let shared = Welcome()
    private var window: NSWindow?
    private var art: NSTextField?
    private var timer: Timer?
    private var frame = 0
    private var usesSprite = false
    private let flagPath = base + "/welcomed"

    func maybeShow() {
        guard !FileManager.default.fileExists(atPath: flagPath) else { return }
        grajPaladyna()
        let W: CGFloat = 440, H: CGFloat = 470
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: W, height: H),
                           styleMask: [.titled, .fullSizeContentView], backing: .buffered, defer: false)
        win.titlebarAppearsTransparent = true
        win.titleVisibility = .hidden
        win.isMovableByWindowBackground = true
        win.level = .normal
        win.center()
        let fx = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: W, height: H))
        fx.material = .sidebar
        fx.state = .active
        win.contentView = fx

        // Grafika paladyna. Trzy poziomy, od najlepszego:
        //   1. paladin_welcome.gif  - oficjalna animacja (NSImageView odtwarza GIF sam),
        //   2. paladin_welcome.png  - ta sama postac, klatka statyczna,
        //   3. PALADIN_FRAMES       - klatki ASCII, gdy branding w ogole nie dojechal.
        // Dzieki trzeciemu poziomowi okno nigdy nie jest puste.
        let a = NSTextField(labelWithString: PALADIN_FRAMES[0])
        a.font = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
        a.maximumNumberOfLines = 0
        a.cell?.wraps = false
        let sprite = NSImage(contentsOfFile: base + "/paladin_welcome.gif")
            ?? NSImage(contentsOfFile: base + "/paladin_welcome.png")
        if let sprite = sprite {
            let ratio = sprite.size.width / max(sprite.size.height, 1)
            let ih: CGFloat = 236, iw = ih * ratio
            let iv = NSImageView(frame: NSRect(x: (W - iw)/2, y: 206, width: iw, height: ih))
            iv.image = sprite
            iv.imageScaling = .scaleProportionallyUpOrDown
            iv.animates = true          // dziala tylko dla GIF-a; dla PNG bez efektu
            fx.addSubview(iv)
            usesSprite = true
        }
        a.textColor = .labelColor
        a.alignment = .center
        a.frame = NSRect(x: 0, y: 208, width: W, height: 240)
        fx.addSubview(a)
        art = a

        let name = NSTextField(labelWithString: APPNAME)
        name.font = .systemFont(ofSize: 22, weight: .bold)
        name.alignment = .center
        name.frame = NSRect(x: 0, y: 172, width: W, height: 30)
        fx.addSubview(name)

        let motto = NSTextField(labelWithString: MOTTO)
        motto.font = .systemFont(ofSize: 12, weight: .medium)
        motto.textColor = .labelColor
        motto.alignment = .center
        motto.frame = NSRect(x: 20, y: 148, width: W - 40, height: 18)
        fx.addSubview(motto)

        let sub = NSTextField(labelWithString: T("The paladin stands guard. Choose how to begin:"))
        sub.font = .systemFont(ofSize: 12)
        sub.textColor = .secondaryLabelColor
        sub.alignment = .center
        sub.frame = NSRect(x: 20, y: 124, width: W - 40, height: 20)
        fx.addSubview(sub)

        let enable = NSButton(title: T("Enable protection"), target: self, action: #selector(pickEnable))
        enable.bezelStyle = .rounded
        enable.keyEquivalent = "\r"
        enable.frame = NSRect(x: W/2 - 150, y: 74, width: 300, height: 34)
        fx.addSubview(enable)

        let watch = NSButton(title: T("Watch only for now"), target: self, action: #selector(pickWatch))
        watch.bezelStyle = .rounded
        watch.frame = NSRect(x: W/2 - 150, y: 36, width: 300, height: 32)
        fx.addSubview(watch)

        // Link do przewodnika: otwiera okno obok, NIE zamyka powitania i NIE
        // ustawia flagi welcomed - uzytkownik i tak musi wybrac tryb powyzej.
        let guideBtn = NSButton(title: T("First steps…"), target: self, action: #selector(openGuideLink))
        guideBtn.isBordered = false
        guideBtn.attributedTitle = NSAttributedString(string: T("First steps…"),
            attributes: [.font: NSFont.systemFont(ofSize: 11),
                         .foregroundColor: NSColor.linkColor])
        guideBtn.frame = NSRect(x: W/2 - 150, y: 8, width: 300, height: 20)
        fx.addSubview(guideBtn)

        // Timer chodzi WYLACZNIE w trybie ASCII. Przy sprite'cie animacje niesie sam
        // NSImageView, a budzenie CPU 11x/s bez powodu jest ostatnim, czego chce
        // bezwentylatorowy Mac (uwaga z przegladu Neo).
        if usesSprite {
            a.isHidden = true
        } else {
            timer = Timer.scheduledTimer(withTimeInterval: 0.09, repeats: true) { [weak self] _ in
                guard let s = self else { return }
                s.frame = (s.frame + 1) % PALADIN_FRAMES.count
                s.art?.stringValue = PALADIN_FRAMES[s.frame]
            }
        }
        window = win
        NSApp.activate(ignoringOtherApps: true)
        win.makeKeyAndOrderFront(nil)
    }

    @objc private func openGuideLink() { Guide.shared.show() }

    @objc private func pickEnable() { finish(dry: false) }
    @objc private func pickWatch() { finish(dry: true) }

    private func finish(dry: Bool) {
        GuardCfg.set(["dry_run": dry])
        FileManager.default.createFile(atPath: flagPath, contents: Data())
        timer?.invalidate()
        window?.orderOut(nil)
        window = nil
    }
}

// MARK: - fleet (wspolny folder, te same pliki co CLI `fleet`)

struct FleetHost {
    let name: String
    var model: String = ""
    var serial: String = ""
    let age: TimeInterval
    let chip: Double?
    let fans: Int?
    let watts: Double?
    let ramPct: Int?
    let level: Int
    let paused: [String]
    let onAC: Bool
    let battPct: Int?
    var battC: Double? = nil
}

/// Migawki hostow z folderu floty. nil = folder nieskonfigurowany/nieczytelny;
/// pusta lista = folder jest, ale nikt jeszcze nie publikuje.
func fleetHosts() -> [FleetHost]? {
    let raw = GuardCfg.string("fleet_dir", "")
    guard !raw.isEmpty else { return nil }
    let dir = NSString(string: raw).expandingTildeInPath
    guard let items = try? FileManager.default.contentsOfDirectory(atPath: dir) else { return nil }
    var out: [FleetHost] = []
    for fname in items.sorted() {
        // plik zewinkowany przez iCloud (".<host>.json.icloud") — host ISTNIEJE, ale danych
        // nie ma pod reka: pokazujemy go jako nieraportujacego zamiast po cichu ukrywac
        if fname.hasSuffix(".json.icloud") {
            var base = fname
            if base.hasPrefix(".") { base.removeFirst() }
            base = String(base.dropLast(".json.icloud".count))
            out.append(FleetHost(name: base, model: "", serial: "", age: 1e9, chip: nil, fans: nil, watts: nil,
                                 ramPct: nil, level: 0, paused: [], onAC: true, battPct: nil))
            continue
        }
        guard fname.hasSuffix(".json"), !fname.hasPrefix(".") else { continue }
        let path = dir + "/" + fname
        guard let d = FileManager.default.contents(atPath: path),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { continue }
        let mtime = (try? FileManager.default.attributesOfItem(atPath: path)[.modificationDate]) as? Date
        let ru = num(j["ram_used_gb"])
        let rt = num(j["ram_total_gb"])
        out.append(FleetHost(
            name: (j["host"] as? String) ?? String(fname.dropLast(5)),
            model: (j["model"] as? String) ?? "",
            serial: (j["serial"] as? String) ?? "",
            // max(0,...): mtime z przyszlosci (rozjazd zegarow na SMB) nie moze dawac
            // ujemnego wieku — host wygladalby na wiecznie swiezy
            age: mtime.map { max(0, Date().timeIntervalSince($0)) } ?? 1e9,
            chip: num(j["chip_c"]),
            fans: (j["fans"] as? [Any])?.compactMap { numInt($0) }.max(),
            watts: num(j["watts"]),
            ramPct: (ru != nil && (rt ?? 0) > 0) ? Int(100 * ru! / rt!) : nil,
            level: numInt(j["level"]) ?? 0,
            paused: (j["paused"] as? [String]) ?? [],
            onAC: (j["on_ac"] as? Bool) ?? true,
            battPct: numInt(j["battery_pct"]),
            battC: num(j["battery_c"])))
    }
    return out
}

func fleetAge(_ s: TimeInterval) -> String {
    // podloga, nie zaokraglenie: 95 s to "1 min temu", nie "2 min temu"
    if s < 60 { return T("now") }
    if s < 7200 { return String(format: T("%d min ago"), max(1, Int(s / 60))) }
    return String(format: T("%d h ago"), Int(s / 3600))
}

/// Stopka: kolorowe logo z ~/.coffee-paladin/logo_footer.png (w ciemnym motywie wariant
/// logo_footer_dark.png z jasnym tekstem, jesli istnieje). Brak plikow = brak wiersza.
final class FooterLogoRow: NSView {
    static func make() -> FooterLogoRow? {
        let dark = NSApp.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        let candidates = dark ? ["/logo_footer_dark.png", "/logo_footer.png"] : ["/logo_footer.png"]
        for c in candidates {
            if let img = NSImage(contentsOfFile: base + c) { return FooterLogoRow(img: img) }
        }
        return nil
    }

    private init(img: NSImage) {
        super.init(frame: NSRect(x: 0, y: 0, width: 400, height: 26))
        let ratio = img.size.width / max(img.size.height, 1)
        let h: CGFloat = 13
        let w = min(h * ratio, 280)
        // logo jest przyciskiem: klik otwiera strone z config.json (footer_logo_url)
        let b = NSButton(frame: NSRect(x: (400 - w) / 2, y: 6, width: w, height: h))
        b.image = img
        b.isBordered = false
        b.imagePosition = .imageOnly
        b.imageScaling = .scaleProportionallyUpOrDown
        b.target = self
        b.action = #selector(openSite)
        b.toolTip = GuardCfg.string("footer_logo_url", "")
        addSubview(b)
    }

    @objc private func openSite() {
        let raw = GuardCfg.string("footer_logo_url", "")
        if !raw.isEmpty, let url = URL(string: raw) {
            NSWorkspace.shared.open(zUTM(url.absoluteString) ?? url)
        }
    }

    required init?(coder: NSCoder) { fatalError() }
}

/// Naglowek menu: logo + nazwa + wersja, wszystko WYSRODKOWANE. Gdy w ~/.coffee-paladin
/// lezy logo.png (u Pawla: znak AIrON), pokazujemy je; bez pliku rysujemy wlasny squircle.
/// Kazdy link WYCHODZACY z aplikacji niesie UTM (decyzja Pawla 01.08) - w statystykach
/// widac wtedy, ze ruch przyszedl z paska, a nie z README czy z posta.
func zUTM(_ s: String, medium: String = "app") -> URL? {
    guard var c = URLComponents(string: s) else { return URL(string: s) }
    var q = c.queryItems ?? []
    q.append(contentsOf: [URLQueryItem(name: "utm_source", value: "coffee-paladin"),
                          URLQueryItem(name: "utm_medium", value: medium),
                          URLQueryItem(name: "utm_campaign", value: "panbookovsky")])
    c.queryItems = q
    return c.url ?? URL(string: s)
}

/// Link do repo z UTM "share" - to wkleja sie w posty i maile z "Podaj dalej".
func linkPodajDalej() -> String {
    zUTM("https://github.com/pawelkwaczynski/coffee-paladin", medium: "share")?.absoluteString
        ?? "https://github.com/pawelkwaczynski/coffee-paladin"
}


/// Dzwiek paladyna (zbroja) przy pokazaniu paladyna - plik z wyborow Pawla (CC0),
/// pod tym samym przelacznikiem Dzwieki co reszta; brak pliku = cisza, zero bledow.
func grajPaladyna() {
    guard GuardCfg.bool("sound", true) else { return }
    let p = base + "/sounds/paladin.wav"
    guard FileManager.default.fileExists(atPath: p) else { return }
    let pr = Process()
    pr.executableURL = URL(fileURLWithPath: "/usr/bin/afplay")
    pr.arguments = [p]
    try? pr.run()
}



/// Okno "Pierwsze kroki": tresc przewodnika w jezyku menu, dostepne z menu
/// i z okna powitalnego. Singleton - drugie klikniecie tylko podnosi okno.
final class Guide {
    static let shared = Guide()
    private var win: NSWindow?

    func show() {
        if let w = win { w.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true); return }
        let W: CGFloat = 480, H: CGFloat = 600
        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: W, height: H),
                         styleMask: [.titled, .closable, .fullSizeContentView],
                         backing: .buffered, defer: false)
        w.titlebarAppearsTransparent = true
        w.titleVisibility = .hidden
        w.isMovableByWindowBackground = true
        w.level = .normal
        w.isReleasedWhenClosed = false
        w.center()
        let fx = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: W, height: H))
        fx.material = .sidebar
        fx.state = .active
        w.contentView = fx

        let ikona = NSImageView(frame: NSRect(x: (W - 40) / 2, y: H - 58, width: 40, height: 40))
        if let img = NSImage(contentsOfFile: base + "/paladin_welcome.png") { ikona.image = img }
        ikona.imageScaling = .scaleProportionallyUpOrDown
        fx.addSubview(ikona)
        let tytul = NSTextField(labelWithString: T("First steps with the paladin"))
        tytul.font = .boldSystemFont(ofSize: 14)
        tytul.alignment = .center
        tytul.frame = NSRect(x: 0, y: H - 84, width: W, height: 20)
        fx.addSubview(tytul)

        let tekst = NSMutableAttributedString()
        let sekcje = [T(GUIDE_CAN), T(GUIDE_WILL), T(GUIDE_SET), T(GUIDE_NTFY)]
        for s in sekcje {
            let linie = s.split(separator: "\n", maxSplits: 1, omittingEmptySubsequences: false)
            // Dwukropek i pusta linijka pod naglowkiem sekcji. Robione TU, przy skladaniu
            // tekstu, a nie w slownikach: inaczej trzeba by ruszyc te same cztery naglowki
            // w pieciu jezykach, czyli dwadziescia wpisow, i pilnowac ich przy kazdej zmianie.
            var naglowek = String(linie[0]).trimmingCharacters(in: .whitespaces)
            if !naglowek.hasSuffix(":") { naglowek += ":" }
            tekst.append(NSAttributedString(string: naglowek + "\n\n",
                attributes: [.font: NSFont.boldSystemFont(ofSize: 12), .foregroundColor: NSColor.labelColor]))
            if linie.count > 1 {
                tekst.append(NSAttributedString(string: String(linie[1]),
                    attributes: [.font: NSFont.systemFont(ofSize: 12), .foregroundColor: NSColor.secondaryLabelColor]))
            }
            tekst.append(NSAttributedString(string: "\n\n"))
        }
        tekst.append(NSAttributedString(string: T(GUIDE_BYE),
            attributes: [.font: NSFont.systemFont(ofSize: 12, weight: .medium), .foregroundColor: NSColor.labelColor]))

        let scroll = NSScrollView(frame: NSRect(x: 16, y: 14, width: W - 32, height: H - 108))
        scroll.hasVerticalScroller = true
        scroll.drawsBackground = false
        let tv = NSTextView(frame: NSRect(x: 0, y: 0, width: W - 48, height: 10))
        tv.isEditable = false
        tv.drawsBackground = false
        tv.textContainerInset = NSSize(width: 0, height: 4)
        tv.textStorage?.setAttributedString(tekst)
        tv.isVerticallyResizable = true
        tv.autoresizingMask = [.width]
        scroll.documentView = tv
        fx.addSubview(scroll)

        win = w
        w.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}

// klucze tresci przewodnika (EN = klucz slownika tlumaczen)
let GUIDE_CAN = "WHAT IT CAN DO\n• The paladin watches the chip, the battery, the fans and the power source - by default a reading every 15 seconds.\n• When things get too hot, it FREEZES heavy processes instead of letting the Mac cook itself. The pause destroys nothing: the process stops mid-instruction and continues once the chip cools. Example? Measured: 89 °C → 60 °C in 19 seconds, no loss.\n• It finds the real culprit: CPU is counted across the whole process tree, so it also sees a script that spawns hundreds of short jobs while using almost nothing itself.\n• On battery below 10% it pauses long jobs - they resume when you plug in.\n• It keeps a black box: after a hard failure the last 8 readings survive. One click turns them into a report for a repair shop (should you ever need it).\n• Keep-awake - works like the well-known Caffeine or Amphetamine, but unlike them it comes with a fuse: the sleep lock is released the moment things run hot. Sleep is the fastest cooling there is."
let GUIDE_WILL = "WHAT WILL HAPPEN\n• Your choice in the welcome window decides how you start.\n\n\"Watch only\" mode: the paladin measures, logs and alerts, but PAUSES NOTHING.\n\n\"Enable protection\" mode: it pauses at the defined thresholds.\n\nSwitching is easy - one switch at the top of the menu.\n\n• Default thresholds: pause at 85 °C, resume at 76 °C, gentle closing of processes at 90 °C - and only after 4 critical readings in a row. Above 90 °C for over a minute is an emergency: despite the pauses the chip still holds critical (something we could not pause is heating, or pausing was not enough to cool the chip). The process is then woken up and gets SIGTERM - a polite \"shut down\": it has a chance to save its state, close its files, clean up. That is why we call this termination \"gentle\".\n\nA fanless Mac (e.g. an Air or Neo) gets more careful parameters. The thresholds are always picked for YOUR machine: see menu > \"About my Mac\".\n\n• Notifications: on. Sounds: off (enable them in Settings). At the critical level a system banner breaks through everything - Focus and full-screen included.\n• The system, Finder, your terminal and your AI agent are on the never-touch list. The guard will not freeze the session working next to it."
let GUIDE_SET = "WHAT YOU CAN SET\n• Chip pause threshold - a slider; resume and terminate recalculate themselves.\n• Measurement interval 5-30 s: more often = faster reaction, but costlier in CPU use.\n• Heavy jobs (safe-run): all cores (fast) or efficiency cores only (cool and quiet), plus a CPU limit of 50-100%.\n• Battery gate, signals, keep-awake, this Mac's name in the fleet."
let GUIDE_NTFY = "PHONE PUSH (ntfy)\n• Settings → \"Phone push (ntfy.sh)...\". The topic name is the ONLY protection: anyone who knows or guesses it can read your alerts and send fake ones. Click \"Generate\" - you get a random, unguessable one.\n• On your phone install the ntfy app from ntfy.sh - mind the lookalike apps - and subscribe to the same topic.\n• No account, no server of ours. It works over the internet, not WiFi: the 90 °C pause reaches your phone on a train, over LTE."
let GUIDE_BYE = "Enjoy your work!\nPaweł"


final class HeaderRow: NSView {
    private var logoView: NSImageView?
    private var appLabel: NSTextField?
    private var srodkowane: [NSTextField] = []

    init() {
        // 360, nie 400: nagłówek nie moze byc tym, co rozpycha cale menu.
        // Realna szerokosc i tak przychodzi od NSMenu - centrujemy w setFrameSize.
        super.init(frame: NSRect(x: 0, y: 0, width: 400, height: 88))
        autoresizingMask = [.width]
        if let logo = customLogo() {
            // znak poziomy (wordmark): srodek, wysokosc 22, szerokosc wg proporcji
            let ratio = logo.size.width / max(logo.size.height, 1)
            let h: CGFloat = 24
            let w = min(h * ratio, 330)
            let iv = NSImageView(frame: NSRect(x: 0, y: 58, width: w, height: h))
            iv.image = logo
            iv.imageScaling = .scaleProportionallyUpOrDown
            iv.contentTintColor = .labelColor
            addSubview(iv)
            logoView = iv
        } else {
            let iv = NSImageView(frame: NSRect(x: 0, y: 58, width: 22, height: 22))
            iv.image = makeLogo(22)
            addSubview(iv)
            logoView = iv
        }
        // Nazwa produktu i motto: to jest "twarz" narzedzia, musi byc na gorze menu,
        // nie dopiero w stopce (luke wykryl wzmocniony test 6).
        // CELOWO bez miniatury paladyna obok: w 30 px szczegolowa grafika robi sie
        // kolorowa naklejka i kloci sie z monochromatycznym wordmarkiem nad nia.
        // Paladyna oglada sie w panelu (klikniecie nazwy) i w oknie powitalnym.
        let app = NSTextField(labelWithString: "\(APPNAME)  ·  v\(VERSION)")
        app.font = .systemFont(ofSize: 13, weight: .semibold)
        app.textColor = .labelColor
        app.alignment = .center
        app.frame = NSRect(x: 0, y: 38, width: 360, height: 18)
        addSubview(app)
        appLabel = app
        srodkowane.append(app)

        let motto = NSTextField(labelWithString: MOTTO)
        motto.font = .systemFont(ofSize: 11, weight: .regular)
        motto.textColor = .labelColor
        motto.alignment = .center
        motto.frame = NSRect(x: 0, y: 22, width: 360, height: 14)
        addSubview(motto)
        srodkowane.append(motto)

        let name = NSTextField(labelWithString: T("A project of the AIrON student research club."))
        name.font = .systemFont(ofSize: 11)
        name.textColor = .secondaryLabelColor
        name.alignment = .center
        name.frame = NSRect(x: 0, y: 6, width: 360, height: 14)
        addSubview(name)
        srodkowane.append(name)

        // .inVisibleRect: obszar sledzenia podaza za KAZDA zmiana rozmiaru wiersza,
        // wiec kursor-dlon dziala tez po tym, jak NSMenu rozciagnie widok
        addTrackingArea(NSTrackingArea(rect: .zero,
                                       options: [.mouseEnteredAndExited, .activeAlways,
                                                 .cursorUpdate, .inVisibleRect],
                                       owner: self, userInfo: nil))
        rozmiesc()
    }
    required init?(coder: NSCoder) { fatalError() }

    // Nagłówek byl centrowany w sztywnych 400 pt, a menu bywa szersze - cala sekcja
    // wygladala na zle wysrodkowana (Pawel, 01.08). Teraz srodek liczy sie z bounds.
    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        rozmiesc()
    }

    private func rozmiesc() {
        if let iv = logoView {
            iv.frame.origin.x = (bounds.width - iv.frame.width) / 2
        }
        for l in srodkowane { l.frame.size.width = bounds.width }
    }

    private func naLogo(_ p: NSPoint) -> Bool { logoView?.frame.contains(p) ?? false }
    private func naNazwie(_ p: NSPoint) -> Bool { appLabel?.frame.contains(p) ?? false }

    override func cursorUpdate(with event: NSEvent) {
        let p = convert(event.locationInWindow, from: nil)
        if naLogo(p) || naNazwie(p) { NSCursor.pointingHand.set() } else { NSCursor.arrow.set() }
    }

    override func mouseUp(with event: NSEvent) {
        let p = convert(event.locationInWindow, from: nil)
        if naLogo(p) {
            // logo AIrON prowadzi do kola naukowego: informatyka po angielsku na AHE
            enclosingMenuItem?.menu?.cancelTracking()
            if let u = zUTM("https://www.ahe.lodz.pl/study-in-english/eng-in-computer-science") {
                NSWorkspace.shared.open(u)
            }
            return
        }
        guard naNazwie(p) else { return }
        // Najpierw zamykamy menu, dopiero potem pokazujemy panel - inaczej menu
        // przechwytuje zdarzenia myszy i panelu nie da sie zamknac klikiem.
        enclosingMenuItem?.menu?.cancelTracking()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.12) { PaladinPanel.shared.toggle() }
    }
}


/// Paladyn "na sztywno z paska": maly panel przyklejony pod ikona w pasku menu,
/// z oficjalna animacja. Nie jest oknem aplikacji - nie zabiera fokusu, nie wchodzi
/// do Dock/Cmd-Tab i znika przy pierwszym klikniecu obok albo po Esc.
final class PaladinPanel: NSObject {
    static let shared = PaladinPanel()
    private var panel: NSPanel?
    private var monitorLokalny: Any?
    private var monitorGlobalny: Any?

    func toggle() {
        if panel != nil { close(); return }
        guard let sprite = NSImage(contentsOfFile: base + "/paladin_welcome.gif")
            ?? NSImage(contentsOfFile: base + "/paladin_welcome.png") else { return }
        grajPaladyna()   // zbroja takze przy panelu (Pawel przywrocil, 01.08 wieczorem)

        let ratio = sprite.size.width / max(sprite.size.height, 1)
        let ih: CGFloat = 210
        let W = max(210, ih * ratio + 40), H = ih + 66
        let p = NSPanel(contentRect: NSRect(x: 0, y: 0, width: W, height: H),
                        styleMask: [.borderless, .nonactivatingPanel],
                        backing: .buffered, defer: false)
        p.level = .statusBar
        p.isOpaque = false
        p.backgroundColor = .clear
        p.hasShadow = true
        p.hidesOnDeactivate = false
        p.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]

        let fx = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: W, height: H))
        fx.material = .popover
        fx.state = .active
        fx.wantsLayer = true
        fx.layer?.cornerRadius = 12
        fx.layer?.masksToBounds = true
        p.contentView = fx

        let iw = ih * ratio
        let iv = NSImageView(frame: NSRect(x: (W - iw)/2, y: 50, width: iw, height: ih))
        iv.image = sprite
        iv.imageScaling = .scaleProportionallyUpOrDown
        iv.animates = true
        fx.addSubview(iv)

        let nazwa = NSTextField(labelWithString: APPNAME)
        nazwa.font = .systemFont(ofSize: 13, weight: .semibold)
        nazwa.alignment = .center
        nazwa.frame = NSRect(x: 0, y: 28, width: W, height: 18)
        fx.addSubview(nazwa)

        let motto = NSTextField(labelWithString: MOTTO)
        motto.font = .systemFont(ofSize: 11)
        motto.textColor = .secondaryLabelColor
        motto.alignment = .center
        motto.frame = NSRect(x: 8, y: 10, width: W - 16, height: 14)
        fx.addSubview(motto)

        ustawPod(p, szerokosc: W, wysokosc: H)
        p.orderFrontRegardless()
        panel = p

        // Zamkniecie: klik gdziekolwiek (tez w sam panel) albo Esc.
        monitorGlobalny = NSEvent.addGlobalMonitorForEvents(
            matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in self?.close() }
        monitorLokalny = NSEvent.addLocalMonitorForEvents(
            matching: [.leftMouseDown, .rightMouseDown, .keyDown]) { [weak self] e in
                if e.type == .keyDown && e.keyCode != 53 { return e }   // 53 = Esc
                self?.close(); return e
            }
    }

    /// Kotwiczy panel pod ikona w pasku menu. Gdy ikony nie da sie zlokalizowac
    /// (inny ekran, ukryta w Bartenderze), ladujemy w prawym gornym rogu ekranu.
    private func ustawPod(_ p: NSPanel, szerokosc W: CGFloat, wysokosc H: CGFloat) {
        if let b = Bar.shared?.item.button, let okno = b.window {
            let ekranowa = okno.convertToScreen(b.convert(b.bounds, to: nil))
            var x = ekranowa.midX - W/2
            let y = ekranowa.minY - H - 6
            if let vis = (okno.screen ?? NSScreen.main)?.visibleFrame {
                x = min(max(x, vis.minX + 8), vis.maxX - W - 8)
            }
            p.setFrameOrigin(NSPoint(x: x, y: y))
            return
        }
        if let vis = NSScreen.main?.visibleFrame {
            p.setFrameOrigin(NSPoint(x: vis.maxX - W - 12, y: vis.maxY - H - 12))
        }
    }

    func close() {
        if let m = monitorGlobalny { NSEvent.removeMonitor(m); monitorGlobalny = nil }
        if let m = monitorLokalny { NSEvent.removeMonitor(m); monitorLokalny = nil }
        panel?.orderOut(nil)
        panel = nil
    }
}


/// Przelacznik rysowany samodzielnie. NSSwitch dziedziczy kolor akcentu systemu,
/// a chcemy jednoznaczna informacje: zielony = pilnuje, szary = nie pilnuje.
/// Kolory sa systemowe (systemGreen / tertiaryLabel), wiec graja z motywem jasnym i ciemnym.
final class Przelacznik: NSControl {
    var wlaczony: Bool { didSet { needsDisplay = true } }
    var kolor: NSColor = .systemGreen
    init(on: Bool, target: AnyObject, action: Selector) {
        self.wlaczony = on
        super.init(frame: NSRect(x: 0, y: 0, width: 38, height: 22))
        self.target = target
        self.action = action
    }
    required init?(coder: NSCoder) { fatalError() }

    override func draw(_ r: NSRect) {
        let tor = NSRect(x: 0, y: 2, width: bounds.width, height: bounds.height - 4)
        let sciezka = NSBezierPath(roundedRect: tor, xRadius: tor.height / 2, yRadius: tor.height / 2)
        (wlaczony ? kolor : NSColor.tertiaryLabelColor).setFill()
        sciezka.fill()
        let d = tor.height - 4
        let x = wlaczony ? tor.maxX - d - 2 : tor.minX + 2
        let knob = NSBezierPath(ovalIn: NSRect(x: x, y: tor.minY + 2, width: d, height: d))
        NSColor.white.setFill()
        NSGraphicsContext.saveGraphicsState()
        let cien = NSShadow()
        cien.shadowColor = NSColor.black.withAlphaComponent(0.25)
        cien.shadowBlurRadius = 1.5
        cien.shadowOffset = NSSize(width: 0, height: -0.5)
        cien.set()
        knob.fill()
        NSGraphicsContext.restoreGraphicsState()
    }

    override func mouseDown(with event: NSEvent) {
        przelacz()
    }

    func przelacz() {
        wlaczony.toggle()
        if let a = action { NSApp.sendAction(a, to: target, from: self) }
    }

    // DOSTEPNOSC. Ten przelacznik decyduje o tym, czy Mac jest chroniony - a rysowal
    // sie sam i nie mowil o sobie nic. VoiceOver czytal w tym wierszu sama etykiete,
    // wiec osoba niewidzaca nie dowiadywala sie ani ze to przelacznik, ani w jakim
    // jest stanie. Z klawiatury nie dalo sie go ruszyc w ogole.
    override func isAccessibilityElement() -> Bool { true }
    override func accessibilityRole() -> NSAccessibility.Role? { .checkBox }
    override func accessibilityValue() -> Any? { wlaczony }
    override func isAccessibilityEnabled() -> Bool { true }
    override func accessibilityPerformPress() -> Bool { przelacz(); return true }

    override var acceptsFirstResponder: Bool { true }
    override func keyDown(with event: NSEvent) {
        // spacja i Enter jak w kazdej systemowej kontrolce
        if event.keyCode == 49 || event.keyCode == 36 { przelacz() } else { super.keyDown(with: event) }
    }
}


/// Wiersz menu z przelacznikiem: etykieta po lewej, przelacznik po prawej.
/// Dwie rzeczy wlaczane najczesciej - pauzowanie przy przegrzaniu i autostart -
/// zasluguja na element, ktorego stan widac bez czytania.
final class SwitchRow: NSView {
    /// Podpis pod etykieta zmienia sie NA ZYWO po przelaczeniu. Wczesniej byl budowany raz,
    /// przy otwarciu menu - wiec klikniecie przelacznika zmienialo config, ale napis zostawal
    /// stary az do zamkniecia i ponownego otwarcia menu. Wyglada to jak zepsuty przelacznik.
    private var podpis: NSTextField?
    private var etykieta: NSTextField?
    private var przelacznik: Przelacznik?
    private var xTekst: CGFloat = 21
    private let opisGdyWylaczone: String?
    private weak var celZewnetrzny: AnyObject?
    private let akcjaZewnetrzna: Selector

    init(_ tytul: String, on: Bool, target: AnyObject, action: Selector,
         opisGdyWylaczone: String? = nil, ikona: String? = nil,
         podpisStaly: String? = nil, kolor: NSColor = .systemGreen) {
        self.opisGdyWylaczone = opisGdyWylaczone
        self.celZewnetrzny = target
        self.akcjaZewnetrzna = action
        // Wysokosc jest STALA, nawet gdy podpisu chwilowo nie ma - inaczej wiersz
        // skakalby przy kazdym przelaczeniu i rozpychal menu.
        // Miejsce na czerwony podpis rezerwujemy TYLKO gdy ochrona jest wylaczona
        // przy otwarciu menu - wlaczona rezerwowala pusta linie i dwa przelaczniki
        // wygladaly na dziwnie oddalone (Pawel, 01.08 x2). Przy przelaczeniu OFF
        // w otwartym menu czerwonego podpisu nie ma gdzie pokazac - stan mowi
        // wtedy sam przelacznik plus powiadomienie guarda "watch-only".
        let W: CGFloat = 360
        let H: CGFloat = (podpisStaly != nil || (opisGdyWylaczone != nil && !on)) ? 40 : 26
        super.init(frame: NSRect(x: 0, y: 0, width: W, height: H))
        // przelacznik trzyma sie PRAWEJ krawedzi realnego menu, nie sztywnych 400 pt
        autoresizingMask = [.width]

        // Ikona po lewej, jak w zwyklych pozycjach menu - wiersz z przelacznikiem
        // nie moze wygladac na urwany obok wierszy, ktore ikony maja.
        if let ikona = ikona,
           let sym = NSImage(systemSymbolName: ikona, accessibilityDescription: nil) {
            sym.isTemplate = true
            let iv = NSImageView(image: sym)
            iv.contentTintColor = .secondaryLabelColor
            iv.frame = NSRect(x: 20, y: H - 21, width: 16, height: 16)
            addSubview(iv)
            xTekst = 44
        }

        let et = NSTextField(labelWithString: tytul)
        et.font = .menuFont(ofSize: 0)
        et.textColor = .labelColor
        et.frame = NSRect(x: xTekst, y: H - 20, width: W - 69 - xTekst, height: 17)
        addSubview(et)
        etykieta = et

        if opisGdyWylaczone != nil && !on {
            let pod = NSTextField(labelWithString: "")
            pod.font = .systemFont(ofSize: 11, weight: .medium)
            pod.textColor = .systemRed
            pod.frame = NSRect(x: xTekst, y: 3, width: W - 69 - xTekst, height: 14)
            addSubview(pod)
            podpis = pod
        } else if let staly = podpisStaly {
            // podpis informacyjny na stale (np. liczba ciezkich procesow) - neutralny kolor
            let pod = NSTextField(labelWithString: staly)
            pod.font = .systemFont(ofSize: 11)
            pod.textColor = .secondaryLabelColor
            pod.frame = NSRect(x: xTekst, y: 3, width: W - 69 - xTekst, height: 14)
            addSubview(pod)
        }

        // Przelacznik NA ROWNI z etykieta (srodek w srodek), nie ze srodkiem calego
        // wiersza - w wierszu z podpisem (H=44) etykieta jest u gory i switch
        // centrowany na wierszu wygladal na obsuniety (uwaga Pawla, 01.08).
        let sw = Przelacznik(on: on, target: self, action: #selector(przelaczono(_:)))
        sw.kolor = kolor
        sw.frame = NSRect(x: W - 62, y: H - 22.5, width: 38, height: 22)
        addSubview(sw)
        przelacznik = sw
        pokazPodpis(on: on)
    }
    required init?(coder: NSCoder) { fatalError() }

    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        przelacznik?.frame.origin.x = bounds.width - 62
        etykieta?.frame.size.width = bounds.width - 69 - xTekst
        podpis?.frame.size.width = bounds.width - 69 - xTekst
    }

    private func pokazPodpis(on: Bool) {
        podpis?.stringValue = on ? "" : (opisGdyWylaczone ?? "")
    }

    @objc private func przelaczono(_ s: Przelacznik) {
        pokazPodpis(on: s.wlaczony)
        if let cel = celZewnetrzny { NSApp.sendAction(akcjaZewnetrzna, to: cel, from: self) }
    }
}


/// Losowa, niezgadywalna nazwa tematu ntfy — bo nazwa jest jedynym zabezpieczeniem.
func randomTopic() -> String {
    let chars = Array("abcdefghjkmnpqrstuvwxyz23456789")
    let suffix = String((0..<10).map { _ in chars[Int(arc4random_uniform(UInt32(chars.count)))] })
    return "mac-guard-" + suffix
}

/// Ikony na pasku to SF Symbols, nie emoji. Powody sa praktyczne: emoji maja wlasny, staly kolor
/// (wiec w ciemnym motywie odcinaja sie jak naklejki), roznia sie szerokoscia miedzy wersjami
/// systemu i psuja rownanie tekstu. Symbol szablonowy przyjmuje kolor paska i wyglada jak czesc
/// systemu. Gdy symbol nie istnieje na danym macOS, wracamy do krotkiego napisu.
func icon(_ name: String, fallback: String, size: CGFloat = 12) -> NSAttributedString {
    guard let raw = NSImage(systemSymbolName: name, accessibilityDescription: nil) else {
        return NSAttributedString(string: fallback)
    }
    let cfg = NSImage.SymbolConfiguration(pointSize: size, weight: .regular)
    let img = raw.withSymbolConfiguration(cfg) ?? raw
    img.isTemplate = true
    let att = NSTextAttachment()
    att.image = img
    att.bounds = CGRect(x: 0, y: -2, width: img.size.width, height: img.size.height)
    return NSAttributedString(attachment: att)
}

// MARK: - what to show in the bar

/// Every bar element can be switched on and off: the menu bar is scarce space and everyone
/// wants something different there. The choice lives in heatbar.json, so it survives a restart.
enum Item: String, CaseIterable {
    case chip, gpu, battery, fans, watts, ram, disk, throttle, paused, flame

    var label: String {
        switch self {
        case .chip: return T("Chip temperature")
        case .gpu: return T("GPU temperature")
        case .battery: return T("Battery temperature")
        case .fans: return T("Fan rpm")
        case .watts: return T("Power draw (W)")
        case .ram: return T("RAM used")
        case .disk: return T("Disk used")
        case .throttle: return T("Throttling marker")
        case .paused: return T("Pause marker")
        case .flame: return T("Flame at critical")
        }
    }

    /// Domyslnie WSZYSTKO widoczne (Pawel, 01.08) - kto chce mniej, odznaczy.
    var byDefault: Bool { true }
}

final class Prefs {
    private var on: [String: Bool] = [:]
    init() { load() }
    func load() {
        guard let d = FileManager.default.contents(atPath: prefsPath),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
              let s = j["show"] as? [String: Bool] else { return }
        on = s
    }
    func save() {
        if let d = try? JSONSerialization.data(withJSONObject: ["show": on], options: [.prettyPrinted]) {
            try? d.write(to: URL(fileURLWithPath: prefsPath), options: .atomic)
        }
    }
    func enabled(_ i: Item) -> Bool { on[i.rawValue] ?? i.byDefault }
    func toggle(_ i: Item) { on[i.rawValue] = !enabled(i); save() }
}

let prefs = Prefs()

// MARK: - guard configuration (thresholds live in config.json, the daemon re-reads it every cycle)

/// Odczyt i zapis config.json guarda. Zawsze scalamy z istniejaca trescia — plik nalezy do
/// demona i zawiera znacznie wiecej niz to, co pokazuje pasek.
enum GuardCfg {
    /// Zwraca nil, gdy configu NIE DA SIE przeczytac. To nie to samo co pusty config:
    /// `set()` musi wtedy odmowic zapisu, inaczej jeden nieudany odczyt kasuje
    /// wszystkie 30 kluczy - a brak `dry_run` demon czyta jako tryb obserwacji,
    /// czyli ruszenie suwaka po cichu wylacza ochrone.
    static func czytaj() -> [String: Any]? {
        guard let d = FileManager.default.contents(atPath: configPath) else {
            return FileManager.default.fileExists(atPath: configPath) ? nil : [:]
        }
        guard let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return nil }
        return j
    }

    /// Cache na czas budowy JEDNEGO menu. Bez niego jedno otwarcie menu to ~17
    /// pelnych odczytow i parsowan config.json, a przy otwartym podmenu floty jeszcze
    /// wiecej. Uniewazniany jawnie w menuNeedsUpdate i po kazdym zapisie.
    private static var cache: [String: Any]?
    /// Cache jest STATYCZNY i dotykany z DWOCH watkow: `menuNeedsUpdate` ustawia go
    /// na watku glownym, a `refreshFleet` -> `fleetHosts()` -> `GuardCfg.string`
    /// czyta go z watku w tle (DispatchQueue.global). Slownik Swifta nie jest
    /// bezpieczny watkowo - rownoczesny odczyt i zapis to niezdefiniowane zachowanie,
    /// od smieciowej wartosci po wywalenie paska. Caly dostep idzie przez ten zamek.
    private static let zamek = NSLock()

    static func zacznijCache() {
        let swieze = czytaj() ?? [:]
        zamek.lock(); cache = swieze; zamek.unlock()
    }

    static func zakonczCache() { zamek.lock(); cache = nil; zamek.unlock() }

    static func all() -> [String: Any] {
        zamek.lock()
        let biezacy = cache
        zamek.unlock()
        // czytamy z dysku POZA zamkiem: I/O pod blokada zatrzymywaloby watek glowny
        return biezacy ?? (czytaj() ?? [:])
    }

    /// Jeden odczyt na wywolanie zamiast dwoch. Menu pytalo o config ~25 razy przy
    /// kazdym otwarciu; polowa z tego brala sie stad, ze `double` czytalo plik dwa razy.
    static func double(_ key: String, _ fallback: Double) -> Double {
        let c = all()
        if let d = c[key] as? Double { return d }
        if let i = c[key] as? Int { return Double(i) }
        return fallback
    }

    static func bool(_ key: String, _ fallback: Bool) -> Bool { (all()[key] as? Bool) ?? fallback }
    static func string(_ key: String, _ fallback: String) -> String { (all()[key] as? String) ?? fallback }

    static func set(_ values: [String: Any]) {
        // Ten sam flock co demon (config.lock): czytaj-zmien-zapisz z dwoch procesow
        // nie moze sie krzyzowac, bo przegrany zapis znika bez sladu (B5).
        let fd = open(base + "/config.lock", O_CREAT | O_WRONLY, 0o644)
        if fd >= 0 { flock(fd, LOCK_EX) }
        defer { if fd >= 0 { flock(fd, LOCK_UN); close(fd) } }
        guard var j = czytaj() else {
            // Config jest, ale nieczytelny. Zapis oznaczalby skasowanie reszty kluczy,
            // wiec nie ruszamy pliku - lepiej, zeby przelacznik nie zadzialal, niz
            // zeby cicho wylaczyl ochrone.
            NSLog("coffee-paladin: config.json nieczytelny - zapis wstrzymany")
            return
        }
        for (k, v) in values { j[k] = v }
        if let d = try? JSONSerialization.data(withJSONObject: j, options: [.prettyPrinted, .sortedKeys]) {
            // .atomic: plik dzieli z nami demon Pythona — uciety zapis = config na DEFAULTS
            try? d.write(to: URL(fileURLWithPath: configPath), options: .atomic)
            cache = j                     // zapis jest zrodlem prawdy do konca cyklu
        }
    }
}


let awakePath = base + "/awake.json"
let hwPath = base + "/hardware.json"

@discardableResult
func shell(_ args: [String]) -> String {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: args[0])
    p.arguments = Array(args.dropFirst())
    let pipe = Pipe()
    p.standardOutput = pipe
    p.standardError = Pipe()
    do { try p.run() } catch { return "" }
    p.waitUntilExit()
    return String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
}

/// Reczny keep-awake: pasek tylko ZAPISUJE zyczenie do awake.json, wykonuje je demon
/// (caffeinate) — z nadrzednym bezpiecznikiem termicznym. Jedna instancja decyduje.
enum Awake {
    static func read() -> [String: Any] {
        guard let d = FileManager.default.contents(atPath: awakePath),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return [:] }
        return j
    }
    static func set(_ v: [String: Any]?) {
        guard let v = v else {
            try? FileManager.default.removeItem(atPath: awakePath)
            return
        }
        if let d = try? JSONSerialization.data(withJSONObject: v, options: [.prettyPrinted]) {
            try? d.write(to: URL(fileURLWithPath: awakePath), options: .atomic)
        }
    }
}

/// Sprzet wykryty przez guarda przy starcie (hardware.json) — zrodlo zakladki About my Mac.
func hardwareInfo() -> [String: Any] {
    guard let d = FileManager.default.contents(atPath: hwPath),
          let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return [:] }
    return j
}

/// Autostart przy logowaniu: sterujemy stanem enable/disable obu LaunchAgentow.
/// `launchctl disable` nie zabija dzialajacej instancji — wylacza tylko start przy logowaniu,
/// dokladnie tak, jak obiecuje przelacznik.
enum Autostart {
    static let services = ["pl.pawel.coffee-paladin", "pl.pawel.coffee-paladin-bar"]
    static func enabled() -> Bool {
        let out = shell(["/bin/launchctl", "print-disabled", "gui/\(getuid())"])
        // brak wpisu = wlaczone; KTORAKOLWIEK usluga wylaczona = przelacznik OFF
        for svc in services {
            for line in out.split(separator: "\n") where line.contains(svc) {
                if line.contains("disabled") || line.contains("true") { return false }
            }
        }
        return true
    }
    static func set(_ on: Bool) {
        for s in services {
            shell(["/bin/launchctl", on ? "enable" : "disable", "gui/\(getuid())/\(s)"])
        }
    }
}

/// Ostrzezenie dobrane do wartosci suwaka. Sens: uzytkownik ma zobaczyc konsekwencje ZANIM
/// ustawi absurd. Najczestszy blad to przenoszenie progu baterii (45 C) na chip — przy 45 C
/// bezpiecznik pauzowalby wszystko bez przerwy, bo bezczynny chip ma juz 40-55 C.
/// Drugi element pary to nazwa SF Symbol — zadnych emoji: maja wlasny staly kolor
/// i w menu wygladaja jak naklejki, symbol szablonowy przyjmuje kolor tekstu.
func thresholdWarning(_ v: Double) -> (String, String) {
    if v < 60 { return (T("TOO LOW - an idle M-series chip already sits at 40-55 C, the guard would pause constantly"), "nosign") }
    if v < 70 { return (T("very conservative - a quiet, cool Mac, but long jobs will crawl"), "exclamationmark.triangle") }
    if v < 80 { return (T("conservative - good for a fanless Mac (Air, 12-inch)"), "lightbulb") }
    if v <= 92 { return (T("recommended - well below Apple's own throttling point (~100-108 C)"), "checkmark.circle") }
    return (T("aggressive - close to the temperature at which macOS throttles by itself"), "exclamationmark.triangle")
}

/// Wiersz menu z suwakiem. NSMenuItem.view pozwala wstawic dowolny widok, wiec suwak
/// z opisem siedzi wprost w menu, bez osobnego okna preferencji.
///
/// Trzy rzeczy, ktore musialy byc poprawione po pierwszej wersji: opis nie moze byc obcinany
/// (dlatego zawija sie na dwie linie), kolor musi byc czytelny na tle menu (dlatego tekst jest
/// w labelColor, a nasilenie ostrzezenia nosi symbol, nie kolor), a linia z wartosciami
/// pochodnymi musi odswiezac sie W TRAKCIE przesuwania — wczesniej pokazywala stan z chwili
/// otwarcia menu, wiec przy suwaku na 65 C nadal twierdzila "wznowienie przy 76 C".
final class SliderRow: NSView {
    let slider = NSSlider()
    private let value = NSTextField(labelWithString: "")
    private let note = NSTextField(labelWithString: "")
    private let derived = NSTextField(labelWithString: "")
    private let onChange: (Double) -> Void
    private let unit: String
    private let describe: (Double) -> (String, String)
    private let derive: ((Double) -> String)?

    init(title: String, min: Double, max: Double, current: Double, unit: String,
         describe: @escaping (Double) -> (String, String),
         derive: ((Double) -> String)? = nil,
         onChange: @escaping (Double) -> Void) {
        self.onChange = onChange
        self.unit = unit
        self.describe = describe
        self.derive = derive
        let height: CGFloat = derive == nil ? 82 : 100
        super.init(frame: NSRect(x: 0, y: 0, width: 400, height: height))
        // jako jedyny widok w menu nie podazal za jego szerokoscia: przy szerszym
        // podmenu suwaki wisialy przy lewej krawedzi z martwym polem po prawej
        autoresizingMask = [.width]

        var y = height - 26

        let label = NSTextField(labelWithString: title)
        label.font = .menuFont(ofSize: 0)
        label.textColor = .labelColor
        label.frame = NSRect(x: 16, y: y, width: 250, height: 18)
        addSubview(label)

        value.font = .monospacedDigitSystemFont(ofSize: 13, weight: .bold)
        value.alignment = .right
        value.textColor = .labelColor
        value.frame = NSRect(x: 270, y: y, width: 114, height: 18)
        addSubview(value)

        y -= 26
        slider.minValue = min
        slider.maxValue = max
        slider.doubleValue = current
        slider.isContinuous = true
        slider.numberOfTickMarks = Int((max - min) / 5) + 1
        slider.allowsTickMarkValuesOnly = true
        slider.target = self
        slider.action = #selector(moved)
        slider.frame = NSRect(x: 16, y: y, width: 368, height: 20)
        addSubview(slider)

        y -= 32
        note.font = .systemFont(ofSize: 11)
        note.textColor = .labelColor
        note.maximumNumberOfLines = 2
        note.lineBreakMode = .byWordWrapping
        note.cell?.wraps = true
        note.cell?.isScrollable = false
        note.frame = NSRect(x: 16, y: y, width: 368, height: 30)
        addSubview(note)

        if derive != nil {
            y -= 20
            derived.font = .monospacedDigitSystemFont(ofSize: 11, weight: .regular)
            derived.textColor = .secondaryLabelColor
            derived.frame = NSRect(x: 16, y: y, width: 368, height: 16)
            addSubview(derived)
        }

        render()
    }

    required init?(coder: NSCoder) { fatalError() }

    private func render() {
        value.stringValue = String(format: "%.0f %@", slider.doubleValue, unit)
        let (text, mark) = describe(slider.doubleValue)
        let out = NSMutableAttributedString()
        if !mark.isEmpty {
            out.append(icon(mark, fallback: "", size: 11))
            out.append(NSAttributedString(string: " "))
        }
        out.append(NSAttributedString(string: text))
        out.addAttributes([.font: NSFont.systemFont(ofSize: 11),
                           .foregroundColor: NSColor.labelColor],
                          range: NSRange(location: 0, length: out.length))
        note.attributedStringValue = out
        if let d = derive { derived.stringValue = d(slider.doubleValue) }
    }

    @objc private func moved() {
        render()
        onChange(slider.doubleValue)
    }
}

// MARK: - snapshot

/// JSON z Pythona raz niesie 90, raz 90.0 — pasek musi przyjac oba (uwaga z recenzji Codex).
func num(_ v: Any?) -> Double? {
    if let d = v as? Double { return d }
    if let i = v as? Int { return Double(i) }
    return (v as? NSNumber)?.doubleValue
}

func numInt(_ v: Any?) -> Int? { num(v).map { Int($0) } }

struct Job { let name: String; let minutes: Int }
struct TopCPU { let name: String; let cpu: Int }
struct TopRAM { let name: String; let gb: Double }

struct Kandydat {
    let pid: Int
    let name: String
    let cpu: Int
}

struct Snap {
    var chip: Double?, gpu: Double?, batt: Double?, watts: Double?
    var fans: [Int] = []
    var ramUsed: Double?, ramTotal: Double?, swap: Double?
    var diskUsed: Int?, diskTotal: Int?, diskPct: Int?
    var pct: Int?, onAC = true, level = 0, load = 0.0, cpuLimit = 100
    var reason = "", topProc: String?, topCPU: Int?
    var paused: [String] = []
    var manualPause = false
    var dryRun = false
    var keepAwake = false
    var trend: Double?, eta: Double?
    var jobs: [Job] = []
    var topCpuList: [TopCPU] = []
    /// Dokladnie to, co dostanie SIGSTOP przy recznym zamrozeniu. Publikuje to demon,
    /// bo tylko on zna listy nietykalnych. Wczesniej pasek pokazywal tu top CPU -
    /// czyli WindowServer i agenta AI, ktorych straznik nigdy by nie ruszyl.
    var freezeCandidates: [Kandydat] = []
    var heavyCount: Int = 0
    var topRamList: [TopRAM] = []
    var pausesToday = 0, killsToday = 0
    var lastCrash: String?
    var thrPause: Double?, thrKill: Double?
    var stamp = ""
    var stale = true
}

func readSnap() -> Snap? {
    guard let data = FileManager.default.contents(atPath: statusPath),
          let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
    var s = Snap()
    s.chip = num(j["chip_c"])
    s.gpu = num(j["gpu_c"])
    s.batt = num(j["battery_c"])
    s.watts = num(j["watts"])
    s.fans = (j["fans"] as? [Any])?.compactMap { numInt($0) } ?? []
    s.ramUsed = num(j["ram_used_gb"])
    s.ramTotal = num(j["ram_total_gb"])
    s.swap = num(j["swap_used_gb"])
    s.diskUsed = numInt(j["disk_used_gb"])
    s.diskTotal = numInt(j["disk_total_gb"])
    s.diskPct = numInt(j["disk_used_pct"])
    s.pct = numInt(j["battery_pct"])
    s.onAC = (j["on_ac"] as? Bool) ?? true
    s.level = numInt(j["level"]) ?? 0
    s.load = num(j["load1"]) ?? 0
    s.cpuLimit = numInt(j["cpu_limit"]) ?? 100
    s.heavyCount = numInt(j["heavy_count"]) ?? 0
    s.reason = (j["reason"] as? String) ?? ""
    s.topProc = j["top_proc"] as? String
    s.topCPU = numInt(j["top_cpu"])
    s.paused = (j["paused"] as? [String]) ?? []
    s.manualPause = (j["manual_pause"] as? Bool) ?? false
    s.dryRun = (j["dry_run"] as? Bool) ?? false
    s.keepAwake = (j["keep_awake"] as? Bool) ?? false
    s.trend = num(j["trend_c_min"])
    s.eta = num(j["eta_pause_min"])
    s.stamp = (j["time"] as? String) ?? ""
    if let z = j["jobs"] as? [[String: Any]] {
        s.jobs = z.map { Job(name: ($0["name"] as? String) ?? "?", minutes: numInt($0["minutes"]) ?? 0) }
    }
    if let z = j["top_cpu_list"] as? [[String: Any]] {
        if let fc = j["freeze_candidates"] as? [[String: Any]] {
            s.freezeCandidates = fc.compactMap {
                guard let pid = numInt($0["pid"]) else { return nil }
                return Kandydat(pid: pid, name: ($0["name"] as? String) ?? "?",
                                cpu: numInt($0["cpu"]) ?? 0)
            }
        }
        s.topCpuList = z.map { TopCPU(name: ($0["name"] as? String) ?? "?",
                                      cpu: numInt($0["cpu"]) ?? 0) }
    }
    if let z = j["top_ram_list"] as? [[String: Any]] {
        s.topRamList = z.map { TopRAM(name: ($0["name"] as? String) ?? "?",
                                      gb: num($0["gb"]) ?? 0) }
    }
    if let st = j["stats"] as? [String: Any] {
        s.pausesToday = (st["pauses"] as? Int) ?? 0
        s.killsToday = (st["kills"] as? Int) ?? 0
    }
    if let p = j["last_hard_shutdown"] as? [String: Any] { s.lastCrash = p["time"] as? String }
    if let t = j["thresholds"] as? [String: Any] {
        s.thrPause = num(t["pause"])
        s.thrKill = num(t["kill"])
    }
    if let m = try? FileManager.default.attributesOfItem(atPath: statusPath)[.modificationDate] as? Date {
        s.stale = Date().timeIntervalSince(m) > 90
    }
    return s
}

/// Rysowany wykres temperatury chipu z history.csv (A10, decyzje Pawla 01.08):
/// slupki kolorowane progami (zielony/zolty/czerwony), linia progu pauzy,
/// znaczniki pauz (poziom >= 2) i podpisy min/max przy krancach - zamiast
/// czarnych slupkow tekstowych bez skali. Rysuje sie RAZ przy otwarciu menu,
/// zadnych timerow - wykres nie moze grzac Maca, ktorego pilnuje.
final class WykresRow: NSView {
    private let wartosci: [Double]
    private let pauzy: [Bool]
    private let czasy: [String]
    private let procesy: [String]
    private let progPauza: Double
    private let progWznow: Double
    /// Slupek pod kursorem. nil = mysz poza wykresem.
    private var podKursorem: Int?
    private var obszar: NSTrackingArea?

    static func make() -> WykresRow? {
        guard let text = try? String(contentsOfFile: historyPath, encoding: .utf8) else { return nil }
        var vals: [Double] = []
        var pau: [Bool] = []
        var czasy: [String] = []
        var proc: [String] = []
        for line in text.split(separator: "\n").suffix(61) {
            let c = line.split(separator: ",", omittingEmptySubsequences: false)
            if c.count > 11, let v = Double(c[2]) {
                vals.append(v)
                pau.append((Int(c[11]) ?? 0) >= 2)
                // "YYYY-MM-DD HH:MM:SS" -> "HH:MM" (podpisy osi czasu pod wykresem)
                let t = String(c[0])
                czasy.append(t.count >= 16 ? String(t.dropFirst(11).prefix(5)) : "")
                // kto wtedy grzal najmocniej - do podpowiedzi pod kursorem
                let nazwa = c.count > 12 ? String(c[12]).trimmingCharacters(in: .whitespaces) : ""
                let cpu = c.count > 13 ? String(c[13]).trimmingCharacters(in: .whitespaces) : ""
                proc.append(nazwa.isEmpty ? "" : (cpu.isEmpty ? nazwa : "\(nazwa) \(cpu)%"))
            }
        }
        guard vals.count >= 3 else { return nil }
        return WykresRow(vals, pau, czasy, proc)
    }

    init(_ v: [Double], _ p: [Bool], _ t: [String], _ pr: [String]) {
        wartosci = v
        pauzy = p
        czasy = t
        procesy = pr
        progPauza = GuardCfg.double("soc_pause_c", 90)
        progWznow = GuardCfg.double("soc_resume_c", 82)
        // +12 pt na os czasu pod slupkami
        super.init(frame: NSRect(x: 0, y: 0, width: 400, height: 76))
        autoresizingMask = [.width]
    }
    required init?(coder: NSCoder) { fatalError() }

    // Sledzenie myszy nad wykresem. Zadnego timera - przerysowujemy sie wylacznie
    // wtedy, gdy kursor naprawde zmienil slupek.
    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let o = obszar { removeTrackingArea(o) }
        let o = NSTrackingArea(rect: bounds,
                               options: [.mouseEnteredAndExited, .mouseMoved, .activeAlways, .inVisibleRect],
                               owner: self, userInfo: nil)
        addTrackingArea(o)
        obszar = o
    }

    override func mouseMoved(with event: NSEvent) {
        let p = convert(event.locationInWindow, from: nil)
        let lewy: CGFloat = 44, prawy: CGFloat = 16
        let W = bounds.width - lewy - prawy
        guard W > 0, !wartosci.isEmpty else { return }
        let krok = W / CGFloat(wartosci.count)
        let i = Int((p.x - lewy) / krok)
        let nowy = (p.x >= lewy && i >= 0 && i < wartosci.count) ? i : nil
        if nowy != podKursorem { podKursorem = nowy; needsDisplay = true }
    }

    override func mouseExited(with event: NSEvent) {
        if podKursorem != nil { podKursorem = nil; needsDisplay = true }
    }

    override func draw(_ dirtyRect: NSRect) {
        let lewy: CGFloat = 44, prawy: CGFloat = 16, dol: CGFloat = 18, gora: CGFloat = 8
        let W = bounds.width - lewy - prawy, H = bounds.height - dol - gora
        guard W > 40, H > 20, !wartosci.isEmpty else { return }
        let lo = wartosci.min()!, hi = wartosci.max()!
        // skala obejmuje prog pauzy tylko, gdy maszyna chodzi w jego poblizu -
        // inaczej zimne odczyty zgniata sie w plaska kreske przy dole
        let top = hi >= progPauza - 15 ? Swift.max(hi, progPauza) : hi
        let span = Swift.max(top - lo, 1.0)
        func y(_ v: Double) -> CGFloat { dol + CGFloat((v - lo) / span) * H }

        let n = wartosci.count
        let krok = W / CGFloat(n)
        let szer = Swift.max(krok - 1.5, 1.0)
        for (i, v) in wartosci.enumerated() {
            let kolor: NSColor = v >= progPauza ? .systemRed
                               : v > progWznow ? .systemYellow : .systemGreen
            kolor.withAlphaComponent(0.85).setFill()
            let x = lewy + CGFloat(i) * krok
            NSBezierPath(roundedRect:
                NSRect(x: x, y: dol, width: szer, height: Swift.max(y(v) - dol, 1.5)),
                xRadius: 0.5, yRadius: 0.5).fill()
            if pauzy[i] {
                // znacznik pauzy: czerwona kropka NAD slupkiem - interwencja guarda
                NSColor.systemRed.setFill()
                NSBezierPath(ovalIn: NSRect(x: x + szer / 2 - 1.5,
                                            y: bounds.height - 6, width: 3, height: 3)).fill()
            }
        }

        // slupek pod kursorem: obwodka, zeby bylo widac ktory odczyt czytamy
        if let k = podKursorem, wartosci.indices.contains(k) {
            let x = lewy + CGFloat(k) * krok
            NSColor.labelColor.withAlphaComponent(0.55).setStroke()
            let ramka = NSBezierPath(rect: NSRect(x: x - 0.5, y: dol - 0.5,
                                                  width: szer + 1,
                                                  height: Swift.max(y(wartosci[k]) - dol, 1.5) + 1))
            ramka.lineWidth = 1
            ramka.stroke()
        }

        // linia progu pauzy (przerywana), o ile miesci sie w skali
        if progPauza >= lo && progPauza <= top {
            let yp = y(progPauza)
            let path = NSBezierPath()
            path.move(to: NSPoint(x: lewy, y: yp))
            path.line(to: NSPoint(x: lewy + W, y: yp))
            path.setLineDash([3, 3], count: 2, phase: 0)
            path.lineWidth = 1
            NSColor.systemRed.withAlphaComponent(0.6).setStroke()
            path.stroke()
        }

        // podpisy skali przy krancach: max u gory, min u dolu (zamiast wiersza pod spodem)
        let atr: [NSAttributedString.Key: Any] = [
            .font: NSFont.monospacedDigitSystemFont(ofSize: 9, weight: .regular),
            .foregroundColor: NSColor.secondaryLabelColor]
        String(format: "%.0f°", top).draw(at: NSPoint(x: 14, y: bounds.height - gora - 8),
                                          withAttributes: atr)
        String(format: "%.0f°", lo).draw(at: NSPoint(x: 14, y: dol - 1), withAttributes: atr)

        // Podpowiedz pod kursorem: godzina odczytu, temperatura i kto wtedy grzal
        // najmocniej. Rysowana w widoku, nie przez NSToolTip - w menu tooltipy
        // pojawiaja sie z opoznieniem i gubia sie przy przesuwaniu myszy.
        if let k = podKursorem, wartosci.indices.contains(k) {
            var opis = czasy.indices.contains(k) && !czasy[k].isEmpty ? czasy[k] + "   " : ""
            opis += String(format: "%.1f°C", wartosci[k])
            if procesy.indices.contains(k), !procesy[k].isEmpty { opis += "   " + procesy[k] }
            let atrP: [NSAttributedString.Key: Any] = [
                .font: NSFont.monospacedDigitSystemFont(ofSize: 9, weight: .medium),
                .foregroundColor: NSColor.labelColor]
            let rozmiar = (opis as NSString).size(withAttributes: atrP)
            // trzymamy chmurke w granicach wykresu, zeby nie uciekala poza menu
            let xSrodek = lewy + CGFloat(k) * krok + szer / 2
            let x = Swift.min(Swift.max(xSrodek - rozmiar.width / 2, lewy),
                              lewy + W - rozmiar.width)
            let yT = bounds.height - rozmiar.height - 1
            NSColor.windowBackgroundColor.withAlphaComponent(0.92).setFill()
            NSBezierPath(roundedRect: NSRect(x: x - 4, y: yT - 2,
                                             width: rozmiar.width + 8, height: rozmiar.height + 3),
                         xRadius: 3, yRadius: 3).fill()
            (opis as NSString).draw(at: NSPoint(x: x, y: yT), withAttributes: atrP)
        }

        // os czasu: poczatek, srodek i koniec zakresu pomiarow (HH:MM z history.csv)
        if podKursorem == nil,
           let pierwszy = czasy.first(where: { !$0.isEmpty }),
           let ostatni = czasy.last(where: { !$0.isEmpty }) {
            pierwszy.draw(at: NSPoint(x: lewy, y: 2), withAttributes: atr)
            let wOst = (ostatni as NSString).size(withAttributes: atr).width
            ostatni.draw(at: NSPoint(x: lewy + W - wOst, y: 2), withAttributes: atr)
            let i = czasy.count / 2
            if czasy.indices.contains(i), !czasy[i].isEmpty, czasy.count > 6 {
                let wSr = (czasy[i] as NSString).size(withAttributes: atr).width
                czasy[i].draw(at: NSPoint(x: lewy + W / 2 - wSr / 2, y: 2), withAttributes: atr)
            }
        }
    }
}

/// "1 h 23 min" z liczby minut — do wiersza pozostalego czasu czuwania.
func fmtDur(_ minutes: Int) -> String {
    if minutes >= 60 {
        let h = minutes / 60, m = minutes % 60
        return m == 0 ? String(format: T("%d h"), h)
                      : String(format: T("%d h"), h) + " " + String(format: T("%d min"), m)
    }
    return String(format: T("%d min"), max(minutes, 1))
}

/// Wiersz wyboru jezyka na glownej karcie menu — piec przyciskow zamiast podmenu
/// zakopanego w Ustawieniach. Klik = zapis "lang" do config.json i restart paska
/// (launchd podnosi go z powrotem dzieki KeepAlive.SuccessfulExit=false).
final class LangRow: NSView {
    private let codes = ["en", "pl", "ru", "zh", "es"]
    private let labels = ["EN", "PL", "RU", "中文", "ES"]

    private var przyciski: [NSButton] = []

    init() {
        super.init(frame: NSRect(x: 0, y: 0, width: 400, height: 30))
        // Menu bywa SZERSZE niz baza (najdluzszy wiersz tekstowy je rozpycha), a NSMenu
        // rozciaga widok pozycji na cala szerokosc. Dlatego srodek liczymy z bounds
        // w layout(), nie ze stalej 400 - inaczej rzad wisi przy lewej krawedzi.
        autoresizingMask = [.width]
        for (i, code) in codes.enumerated() {
            let b = NSButton(title: labels[i], target: self, action: #selector(pick(_:)))
            b.bezelStyle = .rounded
            b.controlSize = .small
            b.font = .systemFont(ofSize: 11, weight: code == lang ? .bold : .regular)
            b.tag = i
            if code == lang {
                b.bezelColor = .controlAccentColor
                b.contentTintColor = .white
            }
            addSubview(b)
            przyciski.append(b)
        }
        rozmiesc()
    }

    required init?(coder: NSCoder) { fatalError() }

    // setFrameSize, nie layout(): NSMenu rozciaga widok pozycji przez zmiane ramki,
    // a layout() bez warstwy potrafi nie przyjsc wcale.
    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        rozmiesc()
    }

    private func rozmiesc() {
        let w: CGFloat = 66, gap: CGFloat = 6
        var x: CGFloat = (bounds.width - (CGFloat(przyciski.count) * w
                                          + CGFloat(przyciski.count - 1) * gap)) / 2
        for b in przyciski {
            b.frame = NSRect(x: x, y: 3, width: w, height: 22)
            x += w + gap
        }
    }

    @objc private func pick(_ sender: NSButton) {
        let code = codes[sender.tag]
        guard code != lang else { return }
        GuardCfg.set(["lang": code])
        exit(1)
    }
}

final class Bar: NSObject, NSMenuDelegate {
    /// Jedyna instancja paska. Panel paladyna potrzebuje jej, zeby wiedziec,
    /// pod ktora ikona sie zaczepic.
    static weak var shared: Bar?
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    let menu = NSMenu()
    var timer: Timer?
    // cache floty: I/O po folderze wspolnym (iCloud/SMB) NIE moze biec w watku glownym
    // przy otwieraniu menu — czkawka sieci blokowalaby cale menu (uwaga z recenzji Codex)
    var fleetCache: [FleetHost]?
    var fleetCacheAt = Date.distantPast
    private var tick = 0
    /// Zabezpieczenie przed przewodnikiem wracajacym co 5 s, gdy pliku-sygnalu
    /// nie da sie usunac.
    private var pokazanyGuideZSygnalu = false
    /// Zyja tylko na czas trwania okna potwierdzenia zamrozenia.
    private var wszystkieCheckbox: NSButton?
    private var checkboxyProcesow: [NSButton] = []

    override init() {
        super.init()
        Bar.shared = self
        // macOS domyslnie wygasza pozycje menu bez akcji — a u nas wiekszosc wierszy to
        // informacje, nie polecenia. Bez tej flagi caly odczyt byl szary i nieczytelny.
        menu.autoenablesItems = false
        menu.delegate = self
        item.menu = menu
        refresh()
        refreshFleet()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { Welcome.shared.maybeShow() }
        // .common, nie .default: w trybie .default timer NIE tyka, gdy menu jest otwarte
        // albo gdy stoi okno modalne (raport, ntfy, nazwa floty). Odczyt na pasku zamieral
        // wtedy razem z animacjami i z dyspozytorem pliku-sygnalu - czyli dokladnie wtedy,
        // gdy czlowiek patrzy na temperature.
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in
            guard let self = self else { return }
            self.obsluzSygnaly()
            self.refresh()
            self.tick += 1
            if self.tick % 6 == 0 { self.refreshFleet() }   // flota co ~30 s, w tle
        }
        if let t = timer { RunLoop.main.add(t, forMode: .common) }
    }

    /// Pliki-sygnaly: `touch ~/.coffee-paladin/show_guide` albo
    /// `echo ntfy > ~/.coffee-paladin/show_window` (guide|ntfy|fleetname|observe).
    /// Sluza do zdalnego otwierania okien przy zrzutach ekranu i we wsparciu.
    ///
    /// To MUSI byc osobna metoda. Wczesniej dyspozytor siedzial w srodku domkniecia
    /// timera i jego `return` (przy pustym pliku) wychodzil z CALEGO taktu, pomijajac
    /// refresh(). Pusty plik-sygnal zatrzymywal wiec odswiezanie paska na 30 s, a plik
    /// z data modyfikacji w przyszlosci (rozjazd zegara, powrot z Time Machine, plik
    /// przyniesiony przez iCloud z maszyny z zegarem do przodu) - na zawsze.
    func obsluzSygnaly() {
        let fm = FileManager.default
        let sygnalGuide = base + "/show_guide"
        if fm.fileExists(atPath: sygnalGuide) {
            // Gdy pliku nie da sie usunac (katalog tylko do odczytu, flaga uchg), okno
            // wracaloby na wierzch co 5 s i nie dalo sie pracowac. Pokazujemy raz.
            let usuniety = (try? fm.removeItem(atPath: sygnalGuide)) != nil
            if usuniety || !pokazanyGuideZSygnalu {
                pokazanyGuideZSygnalu = true
                Guide.shared.show()
            }
        } else {
            pokazanyGuideZSygnalu = false
        }

        let sygnalOkno = base + "/show_window"
        guard let dane = try? String(contentsOfFile: sygnalOkno, encoding: .utf8) else { return }
        let tresc = dane.trimmingCharacters(in: .whitespacesAndNewlines)
        // `echo ntfy > plik` najpierw OBCINA plik do zera, potem dopisuje tresc.
        // Trafienie timerem w to okno dawalo pusty string - i zamiast okna ntfy
        // otwieral sie Przewodnik. Pusty plik zostawiamy na nastepny cykl; jesli po
        // 30 s dalej jest pusty, sprzatamy go. abs(), bo data z przyszlosci tez sie liczy.
        if tresc.isEmpty {
            if let a = try? fm.attributesOfItem(atPath: sygnalOkno),
               let m = a[.modificationDate] as? Date,
               abs(Date().timeIntervalSince(m)) > 30 {
                try? fm.removeItem(atPath: sygnalOkno)
            }
            return
        }
        // NIE OTWIERAMY OKNA NA OKNIE. Ten dyspozytor biegnie z timera, wiec potrafil
        // wywolac `runModal` w chwili, gdy inny modal juz trwal (np. potwierdzenie
        // wyjscia albo dialog ntfy otwarty recznie). Zagniezdzony runModal to
        // zablokowany pasek: uzytkownik widzi dwa okna i zadnego nie da sie zamknac.
        // Sygnal zostawiamy na dysku - obsluzymy go, gdy pierwsze okno sie zamknie.
        if NSApp.modalWindow != nil {
            return
        }
        try? fm.removeItem(atPath: sygnalOkno)
        NSApp.activate(ignoringOtherApps: true)
        switch tresc {
        case "ntfy": ntfyDialog()
        case "fleetname": fleetNameDialog()
        case "observe": explainDry()
        default: Guide.shared.show()
        }
    }

    func refreshFleet() {
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let hosts = fleetHosts()
            DispatchQueue.main.async {
                self?.fleetCache = hosts
                self?.fleetCacheAt = Date()
            }
        }
    }

    /// Colour follows the guard's level, not a raw number - the bar must say the same thing
    /// the safety net says.
    func tint(_ s: Snap) -> NSColor {
        if s.stale { return .secondaryLabelColor }
        // Tryb obserwacji NIE moze wygladac jak dzialajaca ochrona. Dotad pasek robil
        // sie czerwony przy poziomie krytycznym tak samo w obu trybach, wiec alarm
        // sugerowal, ze paladyn zadzialal - a w tym trybie nie zatrzyma niczego.
        if s.dryRun { return .secondaryLabelColor }
        switch s.level {
        case 3: return .systemRed
        case 2: return .systemOrange
        case 1: return .systemYellow
        default: return .labelColor
        }
    }

    // PLONACY PASEK (A13.4, decyzja Pawla): przy poziomie krytycznym ikona pali sie
    // ~3 sekundy i GASNIE. Celowo krotko i z 60 s przerwy: animacja to timer budzacy
    // CPU, a nie bedziemy grzac Maca po to, zeby pokazac, ze jest goracy.
    private var plomienTimer: Timer?
    private var plomienKlatka = 0
    private var plomienOstatnio = Date.distantPast

    private func zapalPasek(_ s: Snap) {
        plomienOstatnio = Date()
        plomienKlatka = 0
        plomienTimer = Timer.scheduledTimer(withTimeInterval: 0.12, repeats: true) { [weak self] t in
            guard let self = self else { t.invalidate(); return }
            self.plomienKlatka += 1
            if self.plomienKlatka > 25 {
                t.invalidate()
                self.plomienTimer = nil
                self.refresh()
                return
            }
            let kolory: [NSColor] = [.systemRed, .systemOrange, .systemYellow]
            let out = NSMutableAttributedString()
            out.append(icon(self.plomienKlatka % 2 == 0 ? "flame.fill" : "flame",
                            fallback: "!", size: 13))
            if let c = s.chip { out.append(NSAttributedString(string: String(format: " %.0f°", c))) }
            out.addAttributes([.foregroundColor: kolory[self.plomienKlatka % 3],
                               .font: NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .bold)],
                              range: NSRange(location: 0, length: out.length))
            self.item.button?.attributedTitle = out
        }
        // Tryb .common, nie .default: przy otwartym menu (i przy kazdym oknie modalnym)
        // runloop przechodzi w tryb sledzenia, a timer w .default przestaje tykac.
        // Animacja stawala wtedy w polklatce i blokowala refresh() - pasek zamarzal
        // z nieaktualna temperatura dokladnie wtedy, gdy uzytkownik na niego patrzyl.
        if let t = plomienTimer { RunLoop.main.add(t, forMode: .common) }
    }

    // WENTYLATOR (zyczenie Pawla 02.08): gdy wiatraki ruszaja z zera, ikona kreci sie
    // na niebiesko ~3 s. Ta sama zasada oszczedzania CPU co przy plomieniu: krotko,
    // z 60 s przerwy.
    private var wentylOstatnio = Date.distantPast
    private var ostatnieObroty = -1

    private func zakrecPasek(_ s: Snap) {
        wentylOstatnio = Date()
        plomienKlatka = 0
        plomienTimer = Timer.scheduledTimer(withTimeInterval: 0.12, repeats: true) { [weak self] t in
            guard let self = self else { t.invalidate(); return }
            self.plomienKlatka += 1
            if self.plomienKlatka > 25 {
                t.invalidate()
                self.plomienTimer = nil
                self.refresh()
                return
            }
            let kolory: [NSColor] = [.systemBlue, .systemCyan, .systemTeal]
            let out = NSMutableAttributedString()
            out.append(icon(self.plomienKlatka % 2 == 0 ? "fan.fill" : "fan",
                            fallback: "fan", size: 13))
            if let f = s.fans.max(), f > 0 {
                out.append(NSAttributedString(string: " " + (f >= 1000 ? String(format: "%.1fk", Double(f) / 1000.0) : "\(f)")))
            }
            out.addAttributes([.foregroundColor: kolory[self.plomienKlatka % 3],
                               .font: NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .bold)],
                              range: NSRange(location: 0, length: out.length))
            self.item.button?.attributedTitle = out
        }
        // Tryb .common, nie .default: przy otwartym menu (i przy kazdym oknie modalnym)
        // runloop przechodzi w tryb sledzenia, a timer w .default przestaje tykac.
        // Animacja stawala wtedy w polklatce i blokowala refresh() - pasek zamarzal
        // z nieaktualna temperatura dokladnie wtedy, gdy uzytkownik na niego patrzyl.
        if let t = plomienTimer { RunLoop.main.add(t, forMode: .common) }
    }

    // FILIZANKA (zyczenie Pawla 02.08): gdy caffeinate wstaje, kubek mruga ~3 s.
    private var kubekOstatnio = Date.distantPast
    private var czuwanieBylo: Bool? = nil

    private func mrugnijKubkiem() {
        kubekOstatnio = Date()
        plomienKlatka = 0
        plomienTimer = Timer.scheduledTimer(withTimeInterval: 0.12, repeats: true) { [weak self] t in
            guard let self = self else { t.invalidate(); return }
            self.plomienKlatka += 1
            if self.plomienKlatka > 25 {
                t.invalidate()
                self.plomienTimer = nil
                self.refresh()
                return
            }
            let out = NSMutableAttributedString()
            out.append(icon(self.plomienKlatka % 2 == 0 ? MUG_FILL : MUG,
                            fallback: "cafe", size: 13))
            let kolor: NSColor = self.plomienKlatka % 2 == 0 ? .systemBrown : .labelColor
            out.addAttributes([.foregroundColor: kolor,
                               .font: NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .bold)],
                              range: NSRange(location: 0, length: out.length))
            self.item.button?.attributedTitle = out
        }
        // Tryb .common, nie .default: przy otwartym menu (i przy kazdym oknie modalnym)
        // runloop przechodzi w tryb sledzenia, a timer w .default przestaje tykac.
        // Animacja stawala wtedy w polklatce i blokowala refresh() - pasek zamarzal
        // z nieaktualna temperatura dokladnie wtedy, gdy uzytkownik na niego patrzyl.
        if let t = plomienTimer { RunLoop.main.add(t, forMode: .common) }
    }

    func refresh() {
        let bold = NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .regular)
        guard let s = readSnap() else {
            let out = NSMutableAttributedString()
            out.append(icon("thermometer.medium", fallback: "T"))
            out.append(NSAttributedString(string: " —"))
            out.addAttributes([.foregroundColor: NSColor.secondaryLabelColor, .font: bold],
                              range: NSRange(location: 0, length: out.length))
            item.button?.attributedTitle = out
            return
        }

        if prefs.enabled(.flame), s.level >= 3, plomienTimer == nil,
           Date().timeIntervalSince(plomienOstatnio) > 60 {
            zapalPasek(s)
        }
        if plomienTimer != nil { return }   // klatki ognia maja pierwszenstwo przez ~3 s

        // wentylatory ruszyly z zera -> niebieskie krecenie
        let maxObroty = s.fans.max() ?? 0
        if prefs.enabled(.flame), !s.stale, ostatnieObroty == 0, maxObroty > 0,
           Date().timeIntervalSince(wentylOstatnio) > 60 {
            ostatnieObroty = maxObroty
            zakrecPasek(s)
        } else {
            ostatnieObroty = maxObroty
        }
        // caffeinate wstal -> mrugajaca filizanka
        let czuwa = !Awake.read().isEmpty
        if plomienTimer == nil, prefs.enabled(.flame), !s.stale, czuwanieBylo == false, czuwa,
           Date().timeIntervalSince(kubekOstatnio) > 60 {
            mrugnijKubkiem()
        }
        czuwanieBylo = czuwa
        if plomienTimer != nil { return }

        let out = NSMutableAttributedString()
        func text(_ t: String) { out.append(NSAttributedString(string: t)) }
        func gap() { if out.length > 0 { text(" ") } }

        out.append(icon("thermometer.medium", fallback: "T"))
        var temps: [String] = []
        if prefs.enabled(.chip) { temps.append(s.chip.map { String(format: "%.0f°", $0) } ?? "—") }
        if prefs.enabled(.gpu), let g = s.gpu { temps.append(String(format: "%.0f°", g)) }
        if prefs.enabled(.battery), let b = s.batt { temps.append(String(format: "%.0f°", b)) }
        if !temps.isEmpty { text(" " + temps.joined(separator: "/")) }

        if prefs.enabled(.fans), let f = s.fans.max() {
            gap()
            if f == 0 && (s.chip ?? 0) >= 70 {
                out.append(icon("exclamationmark.triangle.fill", fallback: "!"))
                text(" 0")
            } else {
                out.append(icon("fan", fallback: "fan"))
                text(" " + (f >= 1000 ? String(format: "%.1fk", Double(f) / 1000.0) : "\(f)"))
            }
        }
        if prefs.enabled(.watts), let w = s.watts {
            // zaznaczone = widoczne, takze przy 0.4 W - ukrywanie ponizej 1 W wygladalo
            // jak zepsuty checkbox (Pawel, 01.08); ponizej 10 W z jednym miejscem po kropce
            gap(); out.append(icon("bolt.fill", fallback: "W"))
            text(w < 10 ? String(format: " %.1fW", w) : String(format: " %.0fW", w))
        }
        if prefs.enabled(.ram), let u = s.ramUsed, let t = s.ramTotal, t > 0 {
            gap(); out.append(icon("memorychip", fallback: "RAM"))
            text(String(format: " %.0f%%", 100 * u / t))
            // swap NIE dostaje ikony na pasku: macOS niemal zawsze trzyma troche swapu,
            // wiec znaczek wygladal na przypadkowy; szczegoly sa w wierszu RAM w menu
        }
        if prefs.enabled(.disk), let p = s.diskPct {
            gap(); out.append(icon("internaldrive", fallback: "SSD")); text(" \(p)%")
        }
        if prefs.enabled(.throttle), s.cpuLimit < 100 {
            gap(); out.append(icon("tortoise.fill", fallback: "slow"))
        }
        // W trybie obserwacji ikona OKA jest wiodaca, nie doklejona na koncu: pasek
        // robil sie czerwony i palil plomieniem identycznie jak w trybie chroniacym,
        // wiec alarm wygladal tak samo, mimo ze NIC nie zostanie wstrzymane.
        if s.dryRun { gap(); out.append(icon("eye", fallback: "obs")) }
        if s.keepAwake { gap(); out.append(icon(MUG_FILL, fallback: "awake")) }
        if prefs.enabled(.paused), !s.paused.isEmpty {
            gap(); out.append(icon("pause.circle.fill", fallback: "||"))
        }

        out.addAttributes([.foregroundColor: tint(s), .font: bold],
                          range: NSRange(location: 0, length: out.length))
        item.button?.attributedTitle = out

        var tip = s.reason.isEmpty ? "coffee-paladin: " + T("calm") : s.reason
        if let e = s.eta { tip += String(format: "\n%.0f min", e) }
        item.button?.toolTip = tip
    }

    func menuNeedsUpdate(_ m: NSMenu) {
        GuardCfg.zacznijCache()          // jeden odczyt configu na cale menu
        defer { GuardCfg.zakonczCache() }
        m.removeAllItems()
        // sekcja marki: logo + nazwa, nad nia nic — to jest "twarz" narzedzia
        let head = NSMenuItem()
        head.view = HeaderRow()
        m.addItem(head)
        m.addItem(.separator())
        // jezyk zaraz pod marka — osobna, elegancko odseparowana sekcja
        let langTop = NSMenuItem()
        langTop.view = LangRow()
        m.addItem(langTop)
        m.addItem(.separator())
        guard let s = readSnap() else {
            // To jest DOKLADNIE ta chwila, w ktorej czlowiek potrzebuje dziennika,
            // raportu i przewodnika - a dotad wszystkie trzy znikaly, bo sa budowane
            // ponizej. Zostawala jedna pozycja: "Wylacz coffee-paladin". Slepy zaulek.
            m.addItem(NSMenuItem(title: T("no data - is coffee-paladin running?"), action: nil, keyEquivalent: ""))
            let restart = m.addItem(withTitle: T("Start the guard again"),
                                    action: #selector(restartGuarda), keyEquivalent: "")
            restart.target = self
            restart.image = img("arrow.clockwise")
            m.addItem(.separator())
            let logIt2 = m.addItem(withTitle: T("Show the guard log"), action: #selector(openLog), keyEquivalent: "")
            logIt2.target = self
            logIt2.image = img("text.alignleft")
            let rep2 = m.addItem(withTitle: T("Export report"), action: #selector(reportDialog), keyEquivalent: "")
            rep2.target = self
            rep2.image = img("wrench.and.screwdriver")
            let gd2 = m.addItem(withTitle: T("First steps…"), action: #selector(openGuide), keyEquivalent: "")
            gd2.target = self
            gd2.image = img("book")
            addTail(m, paused: false); return
        }
        func row(_ t: String) { m.addItem(NSMenuItem(title: t, action: nil, keyEquivalent: "")) }
        func mono(_ t: String) {
            let it = NSMenuItem(title: "", action: nil, keyEquivalent: "")
            it.attributedTitle = NSAttributedString(
                string: t, attributes: [.font: NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)])
            m.addItem(it)
        }
        let na = T("n/a")

        if s.stale { row(T("!") + " " + String(format: T("data is stale (%@) - the guard may have died"), s.stamp)) }
        if let c = s.lastCrash { row(String(format: T("the Mac shut down without warning: %@"), c)) }

        // Odczyty scalone parami w jedna linie (decyzja Pawla 01.08): temperatury razem,
        // obciazenie z wentylatorami, zasilanie z poborem - karta krotsza, zero nowych
        // kluczy tlumaczen (skladamy z istniejacych fragmentow)
        // Ikony wiodace TE SAME co na pasku (thermometer/fan/bolt/memorychip/internaldrive),
        // wiec odczyt z paska i odczyt z karty to wizualnie ten sam jezyk (Pawel, 01.08).
        // Ikony w srodku linii (wentylator, piorun) ida jako NSTextAttachment przez icon().
        func rowI(_ symbol: String, _ tresc: NSAttributedString) {
            let it = NSMenuItem(title: "", action: nil, keyEquivalent: "")
            it.image = img(symbol)
            let a = NSMutableAttributedString(attributedString: tresc)
            a.addAttribute(.font, value: NSFont.menuFont(ofSize: 0),
                           range: NSRange(location: 0, length: a.length))
            it.attributedTitle = a
            m.addItem(it)
        }
        func txt(_ s: String) -> NSAttributedString { NSAttributedString(string: s) }

        rowI("thermometer.medium",
             txt("Chip:  " + (s.chip.map { String(format: "%.1f °C", $0) } ?? na)
                 + (s.gpu != nil ? String(format: "     GPU: %.1f °C", s.gpu!) : "")
                 + "     " + String(format: T("Battery:  %@"),
                                    s.batt.map { String(format: "%.1f °C", $0) } ?? na)))
        // Obciazenie i wentylatory MUSZA byc w osobnych wierszach, a jednostka nie moze
        // sie powtarzac przy kazdym wentylatorze. Razem w jednej linii ten wiersz mial
        // 328 pt przy stojacych wentylatorach i 446 pt przy krecacych - a widoki wlasne
        // (wykres, przelaczniki, jezyki) trzymaja 360 pt, wiec wszystko powyzej rozpycha
        // menu. Efekt: menu robilo sie o 118 pt szersze, gdy tylko ruszyly wentylatory,
        // i wracalo, gdy stanely. Po rosyjsku bylo jeszcze gorzej (439 pt).
        // Rozdzielone i bez powtorzonej jednostki wszystkie wiersze mieszcza sie
        // w 150-213 pt we wszystkich pieciu jezykach, wiec szerokosc menu jest STALA.
        rowI("gauge", txt(String(format: T("Load:  %.2f / %d cores"),
                                 s.load, ProcessInfo.processInfo.processorCount)))
        if !s.fans.isEmpty {
            // Jednostka RAZ na koncu, ale wartosci WSZYSTKIE. Filtrowanie zer ukrywaloby
            // wentylator, ktory stanal, podczas gdy drugi pracuje - a to jest dokladnie
            // ten objaw, dla ktorego istnieje alarm awarii chlodzenia. Zero ma byc widoczne.
            let fanTxt = s.fans.allSatisfy { $0 == 0 }
                ? T("stopped")
                : String(format: T("%@ rpm"), s.fans.map(String.init).joined(separator: ", "))
            // Ikona wentylatora jest teraz WIODACA. Wczesniej siedziala w srodku linii
            // jako separator miedzy obciazeniem a wentylatorami; po rozdzieleniu wierszy
            // zostala tam, gdzie byla, i wiersz mial dwie ikony naraz - "gauge" z przodu
            // i wentylator w tekscie.
            rowI("fan", txt(String(format: T("Fans:  %@"), fanTxt)))
        }
        if let u = s.ramUsed, let t = s.ramTotal, t > 0 {
            var line = String(format: T("RAM:  %.1f / %.1f GB (%d%%)"), u, t, Int(100 * u / t))
            if let sw = s.swap, sw > 0.01 { line += "     " + String(format: T("swap %.2f GB"), sw) }
            rowI("memorychip", txt(line))
        }
        if let du = s.diskUsed, let dt = s.diskTotal, let dp = s.diskPct {
            rowI("internaldrive", txt(String(format: T("Disk:  %d / %d GB used (%d%%)"), du, dt, dp)))
        }
        // Bez procentu baterii - ten widac na pasku systemowym macOS. Sam fakt
        // zasilacz/bateria zostaje, bo zmienia zachowanie guarda (bramka baterii).
        // Procent zostal we flocie, gdzie patrzysz na cudza maszyne bez jej paska.
        // Ikona mowi szybciej niz slowo: wtyczka = zasilacz, bateria = bateria.
        let pw = NSMutableAttributedString()
        pw.append(txt(String(format: T("Power:  %@"), s.onAC ? T("AC adapter") : T("Battery"))))
        if let w = s.watts {
            pw.append(txt("     "))
            pw.append(icon("bolt.fill", fallback: ""))
            pw.append(txt(" " + String(format: T("Draw:  %.1f W"), w)))
        }
        rowI(s.onAC ? "powerplug" : "battery.100", pw)
        // "CPU available: 100%" mylilo: to CPU_Speed_Limit z pmset (dlawienie zegarow),
        // nie wolne moce. Wiersz pokazujemy TYLKO gdy dlawienie realnie wystepuje -
        // przy 100% to szum, a nazwa mowi teraz wprost, o co chodzi (B7).
        if s.cpuLimit < 100 {
            row(String(format: T("Throttling: CPU capped at %d%% speed"), s.cpuLimit))
        }
        if s.keepAwake {
            let a = Awake.read()
            switch a["mode"] as? String {
            case "timer":
                let left = max(0, (a["until"] as? Double ?? 0) - Date().timeIntervalSince1970)
                // zegar + jezyk wprost: to caffeinate (wbudowane w macOS) trzyma czuwanie;
                // licznik maleje przy kazdym odswiezeniu karty (otwarte menu nie tyka
                // co sekunde - staly timer w menu grzalby CPU, ktorego pilnujemy)
                rowI("clock", txt(String(format: T("caffeinate holds for another %@"),
                                         fmtDur(Int(left / 60)))))
            case "forever":
                row(T("Keep-awake: indefinitely"))
            case "app":
                row(String(format: T("Keep-awake: while %@ is running"), (a["app"] as? String) ?? "?"))
            case "download":
                row(T("Keep-awake: while downloading"))
            default:
                row(T("Keeping the Mac awake (heavy job running)"))
            }
        }

        if let wykres = WykresRow.make() {
            m.addItem(.separator())
            let it = NSMenuItem()
            it.view = wykres
            m.addItem(it)
        }
        // Prognoza "do pauzy ok. N min" usunieta z karty: ekstrapolacja liniowa klamie
        // przy plateau 88-90 C (Apple tnie zegary). Pola trend_c_min/eta_pause_min
        // zostaja w status.json - agent moze z nich korzystac, czlowieka nie oklamujemy.

        // akcja zamrozenia TUZ POD odczytami i wykresem — tam, gdzie patrzysz, gdy jest goraco
        m.addItem(.separator())
        // WLACZNIK OCHRONY - najwazniejsza decyzja w calej aplikacji, wiec nie chowamy jej
        // w Ustawieniach. Przelacznik ON = ochrona dziala (dry_run = false).
        let obserwuje = GuardCfg.bool("dry_run", true)
        let ochrona = NSMenuItem()
        ochrona.view = SwitchRow(T("Pause jobs when the Mac overheats"),
                                 on: !obserwuje,
                                 target: self, action: #selector(toggleDry),
                                 opisGdyWylaczone: T("OFF - the Mac is only being watched"),
                                 ikona: "pause")
        m.addItem(ochrona)
        // autostart ZARAZ POD ochrona (decyzja Pawla 01.08): dwa przelaczniki obok siebie,
        // jedna sekcja "wlacz/wylacz"; ikona petli = "co logowanie od nowa"
        let auto = NSMenuItem()
        auto.view = SwitchRow(T("Start at login"), on: Autostart.enabled(),
                              target: self, action: #selector(toggleAutostart),
                              ikona: "arrow.triangle.2.circlepath")
        m.addItem(auto)
        // przelacznik zamiast klikanej pozycji (Pawel, pkt 3): ON = zamrozone recznie;
        // niebieski, zeby nie mylil sie z zielona OCHRONA; obok liczba ciezkich procesow
        let zamrozone = !s.paused.isEmpty
        let mrozek = NSMenuItem()
        let mrozView = SwitchRow(T("Freeze all heavy jobs now"),
                                 on: zamrozone,
                                 target: self, action: #selector(toggleFreeze(_:)),
                                 // ikona opisuje FUNKCJE wiersza, stan niesie przelacznik: "play" przy
                                 // przelaczniku w pozycji ON przeczylo samo sobie
                                 ikona: "pause.circle",
                                 podpisStaly: String(format: T("Heavy processes right now: %d"),
                                                    s.heavyCount),
                                 kolor: .systemBlue)
        // tooltip mowi JAKIE procesy sa na celowniku (top 3 wg CPU)
        if !s.topCpuList.isEmpty {
            mrozView.toolTip = s.topCpuList.map { "\($0.name) (\($0.cpu)%)" }.joined(separator: ", ")
        }
        mrozek.view = mrozView
        m.addItem(mrozek)
        m.addItem(.separator())

        // eksport: uzytkownik wybiera format, nie my
        let rep = NSMenuItem(title: T("Export report for a repair shop"), action: nil, keyEquivalent: "")
        rep.image = img("wrench.and.screwdriver")
        rep.action = #selector(reportDialog)
        rep.target = self
        m.addItem(rep)
        let logIt = m.addItem(withTitle: T("Show the guard log"), action: #selector(openLog), keyEquivalent: "")
        logIt.target = self
        logIt.image = img("text.alignleft")

        // Przewodnik siedzi tuz pod dziennikiem, bo okno powitalne pokazuje sie raz
        // i po jego zamknieciu nie bylo skad go otworzyc.
        let guideIt = m.addItem(withTitle: T("First steps…"), action: #selector(openGuide), keyEquivalent: "")
        guideIt.target = self
        guideIt.image = img("book")

        addTail(m, paused: !s.paused.isEmpty)
    }

    /// Ikona SF Symbol dla pozycji menu — szablonowa, wiec przyjmuje kolor systemu.
    func img(_ name: String) -> NSImage? {
        let i = NSImage(systemSymbolName: name, accessibilityDescription: nil)
        i?.isTemplate = true
        return i
    }

    func addTail(_ m: NSMenu, paused: Bool) {
        m.addItem(.separator())
        // KEEP AWAKE jak w Amphetamine — tyle ze kazdy z tych trybow ma nadrzedny
        // bezpiecznik termiczny: przy przegrzaniu demon i tak zwalnia blokade snu.
        let ka = NSMenuItem(title: T("Keep awake"), action: nil, keyEquivalent: "")
        ka.image = img(MUG)
        let km = NSMenu()
        km.autoenablesItems = false
        let cur = Awake.read()
        let curMode = cur["mode"] as? String

        let off = NSMenuItem(title: T("Off"), action: #selector(awakeOff), keyEquivalent: "")
        off.target = self
        off.state = curMode == nil ? .on : .off
        km.addItem(off)
        km.addItem(.separator())
        for min in [15, 30, 45, 60, 120, 180, 300, 480, 720] {
            let it = NSMenuItem(title: fmtDur(min), action: #selector(awakeTimer(_:)), keyEquivalent: "")
            it.target = self
            it.representedObject = min
            if curMode == "timer", let until = cur["until"] as? Double,
               abs(until - (cur["set_at"] as? Double ?? 0) - Double(min * 60)) < 1 {
                it.state = .on
            }
            km.addItem(it)
        }
        let forever = NSMenuItem(title: T("Indefinitely"), action: #selector(awakeForever), keyEquivalent: "")
        forever.target = self
        forever.state = curMode == "forever" ? .on : .off
        km.addItem(forever)
        km.addItem(.separator())

        // "dopoki dziala aplikacja": lista realnie uruchomionych aplikacji okienkowych
        let appItem = NSMenuItem(title: T("While an app is running"), action: nil, keyEquivalent: "")
        let am = NSMenu()
        am.autoenablesItems = false
        let running = NSWorkspace.shared.runningApplications
            .filter { $0.activationPolicy == .regular }
            .compactMap { $0.localizedName }
            .sorted { $0.lowercased() < $1.lowercased() }
        for name in running.prefix(20) {
            let it = NSMenuItem(title: name, action: #selector(awakeApp(_:)), keyEquivalent: "")
            it.target = self
            it.representedObject = name
            it.state = (curMode == "app" && (cur["app"] as? String) == name) ? .on : .off
            am.addItem(it)
        }
        appItem.submenu = am
        appItem.state = curMode == "app" ? .on : .off
        km.addItem(appItem)

        let dl = NSMenuItem(title: T("While downloading (network active)"),
                            action: #selector(awakeDownload), keyEquivalent: "")
        dl.target = self
        dl.state = curMode == "download" ? .on : .off
        km.addItem(dl)
        km.addItem(.separator())
        let note = NSMenuItem(title: T("released automatically when the Mac gets hot"),
                              action: nil, keyEquivalent: "")
        note.isEnabled = false
        km.addItem(note)
        km.addItem(.separator())
        let kaAuto = NSMenuItem()
        kaAuto.view = SwitchRow(T("Keep the Mac awake while heavy jobs run"),
                                on: GuardCfg.bool("keep_awake_auto", false),
                                target: self, action: #selector(toggleAwake), kolor: .systemGray)
        km.addItem(kaAuto)
        ka.submenu = km
        m.addItem(ka)

        // checkboxes deciding what appears in the bar; state kept in heatbar.json
        let showItem = NSMenuItem(title: T("Show in the bar"), action: nil, keyEquivalent: "")
        showItem.image = img("eye")
        let sub = NSMenu()
        sub.autoenablesItems = false
        for (i, it) in Item.allCases.enumerated() {
            let mi = NSMenuItem(title: it.label, action: #selector(toggleItem(_:)), keyEquivalent: "")
            mi.target = self
            mi.tag = i
            mi.state = prefs.enabled(it) ? .on : .off
            sub.addItem(mi)
        }
        showItem.submenu = sub
        m.addItem(showItem)

        // panel ustawien: progi suwakiem + przelaczniki. Demon czyta config.json w kazdym
        // przebiegu, wiec zmiana dziala od razu, bez restartu czegokolwiek.
        let setItem = NSMenuItem(title: T("Settings"), action: nil, keyEquivalent: "")
        setItem.image = img("gearshape")
        let ss = NSMenu()
        ss.autoenablesItems = false

        let pauseNow = GuardCfg.double("soc_pause_c", 85)
        let jobsHdr = NSMenuItem(title: T("Heavy jobs (safe-run)"), action: nil, keyEquivalent: "")
        jobsHdr.isEnabled = false
        ss.addItem(jobsHdr)
        let mode = GuardCfg.string("job_cores_mode", "efficiency")
        let eff = NSMenuItem(title: T("Efficiency cores only (cool and quiet)"),
                             action: #selector(coresEfficiency), keyEquivalent: "")
        eff.target = self
        eff.state = mode == "all" ? .off : .on
        ss.addItem(eff)
        let allc = NSMenuItem(title: T("All cores (fast - the paladin still watches the temperature)"),
                              action: #selector(coresAll), keyEquivalent: "")
        allc.target = self
        allc.state = mode == "all" ? .on : .off
        ss.addItem(allc)
        ss.addItem(.separator())
        let cpuRow = NSMenuItem()
        cpuRow.view = SliderRow(
            title: T("CPU limit for heavy jobs"), min: 50, max: 100,
            current: GuardCfg.double("job_cpu_percent", 95), unit: "%",
            describe: { _ in (T("below 100% the whole job gets tiny micro-pauses (works for any program)"), "") }) { v in
            GuardCfg.set(["job_cpu_percent": Int(v)])
        }
        ss.addItem(cpuRow)
        ss.addItem(.separator())
        let chipRow = NSMenuItem()
        chipRow.view = SliderRow(
            title: T("Chip pause threshold"), min: 55, max: 100, current: pauseNow, unit: "°C",
            describe: thresholdWarning,
            derive: { v in String(format: T("resume at %.0f °C, terminate at %.0f C"),
                                  v - 9, Swift.min(v + 5, 100)) }) { v in
            // pochodne trzymamy spojne: histereza 9 C w dol, ubicie 5 C w gore (nie wyzej niz 100)
            GuardCfg.set(["soc_pause_c": v,
                          "soc_resume_c": v - 9,
                          "soc_kill_c": Swift.min(v + 5, 100)])
        }
        ss.addItem(chipRow)
        ss.addItem(.separator())

        let battRow = NSMenuItem()
        battRow.view = SliderRow(title: T("Battery gate"), min: 5, max: 50,
                                 current: GuardCfg.double("batt_pct_pause", 10), unit: "%",
                                 describe: { _ in (T("pause below this charge when unplugged"), "") }) { v in
            GuardCfg.set(["batt_pct_pause": Int(v), "batt_pct_resume": Int(v) + 15])
        }
        ss.addItem(battRow)
        ss.addItem(.separator())

        // CIEZKIE ZADANIA: typ rdzeni + limit CPU (defaulty dla safe-run; zapis do config.json)
        // interwal pomiarow (Pawel, 01.08): rzadziej = oszczedniej, czesciej = szybsza
        // automatyczna reakcja; reczne akcje i tak reaguja w ~1 s niezaleznie od tego
        let pollRow = NSMenuItem()
        pollRow.view = SliderRow(
            title: T("Measurement interval"), min: 5, max: 30,
            current: GuardCfg.double("poll_seconds", 15), unit: " s",
            describe: { v in
                switch v {
                case ..<7.5:  return (T("fastest reaction - the guard itself burns ~3.5% of one core all the time"), "")
                case ..<12.5: return (T("reacts up to 5 s sooner than default, costs ~1.8% of one core"), "")
                case ..<17.5: return (T("default: good reaction at ~1.2% of one core"), "")
                default:      return (T("frugal - an automatic pause may come tens of seconds after the threshold"), "")
                }
            }) { v in
            GuardCfg.set(["poll_seconds": Int(v)])
        }
        ss.addItem(pollRow)
        ss.addItem(.separator())

        let notif = NSMenuItem()
        notif.view = SwitchRow(T("Notifications"), on: GuardCfg.bool("notify", true),
                               target: self, action: #selector(toggleNotify), kolor: .systemBlue)
        ss.addItem(notif)
        func infoLinia(_ tekst: String) {
            let it = NSMenuItem(title: "", action: nil, keyEquivalent: "")
            it.attributedTitle = NSAttributedString(
                string: tekst,
                attributes: [.font: NSFont.systemFont(ofSize: 11),
                             .foregroundColor: NSColor.secondaryLabelColor])
            it.isEnabled = false
            ss.addItem(it)
        }
        infoLinia(T("Turns off banners, their sounds and phone push - one gate for all."))
        // pomoc o trybie obserwacji zyje w popupie przy WYLACZANIU ochrony;
        // Powiadomienia / Dzwieki / Push = jedna zwarta sekcja (Pawel, 01.08)

        let snd = NSMenuItem()
        snd.view = SwitchRow(T("Sounds"), on: GuardCfg.bool("sound", true),
                             target: self, action: #selector(toggleSound), kolor: .systemBlue)
        ss.addItem(snd)
        infoLinia(T("Exception: the critical banner shouts regardless."))

        // "Nie usypiaj przy ciezkich zadaniach" mieszka teraz w podmenu Nie usypiaj Maca

        let ntfy = NSMenuItem()
        ntfy.view = SwitchRow(T("Phone push (ntfy.sh)…"),
                              on: !GuardCfg.string("ntfy_topic", "").isEmpty,
                              target: self, action: #selector(toggleNtfy), kolor: .systemBlue)
        ss.addItem(ntfy)

        ss.addItem(.separator())
        let flabel = NSMenuItem(title: "", action: #selector(fleetNameDialog), keyEquivalent: "")
        // po "|" aktualna nazwa (szara) - widac od razu, jak ten Mac nazywa sie we flocie
        let nazwaFloty = GuardCfg.string("fleet_label", "")
        let pokazNazwe = nazwaFloty.isEmpty
            ? (Host.current().localizedName ?? "Mac")
            : nazwaFloty
        let ft = NSMutableAttributedString(string: T("Name this Mac in the fleet…") + "  |  ",
                                           attributes: [.font: NSFont.menuFont(ofSize: 0)])
        ft.append(NSAttributedString(string: pokazNazwe,
                                     attributes: [.font: NSFont.menuFont(ofSize: 0),
                                                  .foregroundColor: NSColor.secondaryLabelColor]))
        flabel.attributedTitle = ft
        flabel.target = self
        flabel.state = GuardCfg.string("fleet_label", "").isEmpty ? .off : .on
        ss.addItem(flabel)

        setItem.submenu = ss
        m.addItem(setItem)

        // ABOUT MY MAC: sprzet wykryty przez guarda + zdrowie baterii + progi
        let about = NSMenuItem(title: T("About my Mac"), action: nil, keyEquivalent: "")
        about.image = img("info.circle")
        let abm = NSMenu()
        abm.autoenablesItems = false
        let hw = hardwareInfo()
        func arow(_ t: String) {
            let it = NSMenuItem(title: t, action: nil, keyEquivalent: "")
            abm.addItem(it)
        }
        if hw.isEmpty {
            arow(T("no data - is coffee-paladin running?"))
        } else {
            // pary w liniach (Pawel, pkt 6): model+chip / rdzenie+NE / RAM+dysk /
            // macOS+data konfiguracji / wentylatory+cykle baterii
            let chipNazwa = (hw["chip"] as? String) ?? "?"
            arow(((hw["model_name"] as? String) ?? "?") + "  ·  " + chipNazwa)
            // Neural Engine nie ma publicznego API do odczytu - liczba rdzeni ANE
            // wynika z modelu chipa (Ultra = 2x die = 32, kazdy inny M = 16)
            let ane = chipNazwa.contains("Ultra") ? 32 : 16
            arow(String(format: T("Cores:  %d performance + %d efficiency  ·  Neural Engine: %d"),
                        (hw["p_cores"] as? Int) ?? 0, (hw["e_cores"] as? Int) ?? 0, ane))
            var ramLinia = String(format: T("RAM:  %d GB"), (hw["ram_gb"] as? Int) ?? 0)
            let snapDysk = readSnap()
            if let dt = snapDysk?.diskTotal, let dp = snapDysk?.diskPct {
                ramLinia += "  ·  " + String(format: T("Disk: %d GB (%d%% free)"), dt, 100 - dp)
            }
            arow(ramLinia)
            // marketingowa nazwa systemu jak w "About This Mac" (Tahoe/Sequoia/...)
            let wersjaOS = (hw["macos"] as? String) ?? "?"
            let nazwaOS: String
            switch Int(wersjaOS.split(separator: ".").first.map(String.init) ?? "") ?? 0 {
            case 26: nazwaOS = "macOS Tahoe"
            case 15: nazwaOS = "macOS Sequoia"
            case 14: nazwaOS = "macOS Sonoma"
            case 13: nazwaOS = "macOS Ventura"
            case 12: nazwaOS = "macOS Monterey"
            case 11: nazwaOS = "macOS Big Sur"
            default: nazwaOS = "macOS"
            }
            var osLinia = nazwaOS + " " + wersjaOS
            var dataSetup: Date?
            if let atr = try? FileManager.default.attributesOfItem(atPath: "/var/db/.AppleSetupDone"),
               let data = (atr[.creationDate] ?? atr[.modificationDate]) as? Date {
                dataSetup = data
                let f = DateFormatter()
                f.dateFormat = "dd.MM.yyyy"
        f.locale = Locale(identifier: "en_US_POSIX")
        f.calendar = Calendar(identifier: .gregorian)
                osLinia += "  ·  " + String(format: T("set up: %@"), f.string(from: data))
            }
            arow(osLinia)
            var wentLinia = String(format: T("Fans:  %d"), (hw["fan_count"] as? Int) ?? 0)
            if let cyc = hw["battery_cycles"] as? Int {
                let warn = (hw["battery_failure"] as? Bool) == true ? " (!)" : ""
                wentLinia += "  ·  " + String(format: T("Battery cycles:  %@"), "\(cyc)\(warn)")
            }
            if let poj = hw["battery_max_capacity_pct"] as? Int {
                wentLinia += "  ·  " + String(format: T("max capacity: %d%%"), poj)
            }
            arow(wentLinia)
            if let ser = hw["serial"] as? String, !ser.isEmpty {
                var serLinia = String(format: T("Serial:  %@"), ser)
                // gwarancja: macOS nie zdradza jej programowo - szacujemy rok od
                // pierwszej konfiguracji systemu i mowimy wprost, ze to szacunek
                if let ds = dataSetup {
                    let f = DateFormatter()
                    f.dateFormat = "dd.MM.yyyy"
        f.locale = Locale(identifier: "en_US_POSIX")
        f.calendar = Calendar(identifier: .gregorian)
                    let koniec = ds.addingTimeInterval(365 * 86400)
                    serLinia += "  ·  " + String(format: T("limited warranty (est.): until %@"),
                                                 f.string(from: koniec))
                }
                arow(serLinia)
            }
            // wszystkie zrodla pomiaru, nie tylko macmon (Pawel, 01.08): gdy jedno
            // padnie, widac od razu, co jeszcze pilnuje maszyny
            let ok = T("yes"), nie = T("no")
            let mac = (hw["chip_sensor"] as? Bool) == true
            let stanOK = FileManager.default.isExecutableFile(atPath:
                NSHomeDirectory() + "/.local/bin/thermalstate")
            let snapZ = readSnap()
            let battOK = snapZ?.batt != nil
            let thrOK = (snapZ?.cpuLimit ?? 0) > 0
            arow(T("Sensors:"))
            arow("   - " + String(format: T("chip and GPU (macmon/IOReport):  %@"), mac ? ok : nie))
            arow("   - " + String(format: T("thermal state (Apple API):  %@"), stanOK ? ok : nie))
            arow("   - " + String(format: T("battery (ioreg):  %@"), battOK ? ok : nie))
            arow("   - " + String(format: T("CPU throttling (pmset):  %@"), thrOK ? ok : nie))
            let sp = GuardCfg.double("soc_pause_c", 85), sk = GuardCfg.double("soc_kill_c", 90)
            arow(String(format: T("Chip thresholds:  pause %.0f C, kill %.0f C"), sp, sk))
        }
        about.submenu = abm
        m.addItem(about)
        if let sn = readSnap() {
            // "Informacje o obciazeniu": zadania, top CPU/RAM, stan, progi, licznik dnia —
            // wszystko w rozwijanym podmenu, zeby glowna karta zostala zwarta
            let loadIt = NSMenuItem(title: T("Load info"), action: nil, keyEquivalent: "")
            loadIt.image = img("chart.bar")
            let lo = NSMenu()
            lo.autoenablesItems = false
            func lrow(_ t: String) { lo.addItem(NSMenuItem(title: t, action: nil, keyEquivalent: "")) }
            if !sn.jobs.isEmpty {
                lrow(T("Supervised jobs (safe-run):"))
                for j in sn.jobs { lrow("   - \(j.name) — \(j.minutes) min") }
            }
            // listy "co grzeje / co zjada RAM": CPU jest przyblizeniem ciepla (per-proces
            // temperatur nie ma) i tak to opisujemy. Gdy guard jeszcze nie opublikowal list
            // (stara wersja demona), zostaje dawny pojedynczy wiersz Top CPU.
            if !sn.topCpuList.isEmpty {
                lrow(T("Heating the most now (CPU ≈ heat):"))
                for t in sn.topCpuList { lrow("   - \(t.name) — \(t.cpu)% CPU") }
            } else if let p = sn.topProc, let c = sn.topCPU {
                lrow(String(format: T("Top CPU:  %@ (%d%%)"), p, c))
            }
            if !sn.topRamList.isEmpty {
                lrow(T("Eating the most RAM:"))
                for t in sn.topRamList { lrow(String(format: "   - %@ — %.1f GB", t.name, t.gb)) }
            }
            if !sn.paused.isEmpty {
                lrow(String(format: T("Paused: %@"), sn.paused.joined(separator: ", "))
                     + (sn.manualPause ? T("  (manual)") : ""))
            } else {
                let names = [T("calm"), T("warm"), T("HOT - paused"), T("CRITICAL")]
                lrow(String(format: T("State: %@"), names[min(max(sn.level, 0), 3)])
                     + (sn.reason.isEmpty ? "" : " — \(sn.reason)"))
            }
            if let pp = sn.thrPause, let pk = sn.thrKill {
                lrow(String(format: T("Chip thresholds:  pause %.0f C, kill %.0f C"), pp, pk))
            }
            if sn.pausesToday > 0 || sn.killsToday > 0 {
                lrow(String(format: T("Today: %d x pause"), sn.pausesToday)
                     + (sn.killsToday > 0 ? String(format: T(", %d x kill"), sn.killsToday) : ""))
            }
            loadIt.submenu = lo
            m.addItem(loadIt)
        }


        // FLOTA APPLE: wszystkie Maki publikujace do wspolnego folderu — te same pliki,
        // ktore czyta CLI `fleet`. "Live" w rytmie ~1 min (takt agenta + sync folderu).
        let fleetIt = NSMenuItem(title: T("Apple fleet"), action: nil, keyEquivalent: "")
        fleetIt.image = img("laptopcomputer")
        let fmenu = NSMenu()
        fmenu.autoenablesItems = false
        func frow(_ t: String) { fmenu.addItem(NSMenuItem(title: t, action: nil, keyEquivalent: "")) }
        // menu czyta MIGAWKE z cache (zero I/O w watku glownym); wiek dolicza od chwili odczytu
        let cacheDrift = max(0, Date().timeIntervalSince(fleetCacheAt))
        if let hosts = fleetCache {
            if hosts.isEmpty {
                frow(T("no agent snapshots yet (agents publish about once a minute)"))
            }
            // Wlasny serial czytany RAZ, nie raz na host: hardwareInfo() to pelny odczyt
            // pliku z dysku, a lecial w petli przy kazdym otwarciu menu.
            let mojSerial = (hardwareInfo()["serial"] as? String) ?? ""
            for h0 in hosts {
                let h = FleetHost(name: h0.name, model: h0.model, serial: h0.serial,
                                  age: h0.age + cacheDrift, chip: h0.chip,
                                  fans: h0.fans, watts: h0.watts, ramPct: h0.ramPct,
                                  level: h0.level, paused: h0.paused, onAC: h0.onAC,
                                  battPct: h0.battPct, battC: h0.battC)
                if h.age > 300 {
                    // symbol systemowy, nie emoji: emoji ma wlasny kolor i wlasna szerokosc,
                    // wiec w ciemnym motywie odcina sie jak naklejka i rozjezdza kolumny
                    let a = NSMutableAttributedString()
                    a.append(icon("exclamationmark.triangle", fallback: "!"))
                    a.append(NSAttributedString(string: "  \(h.name) — " + T("STALE - not reporting")
                                                + "  (" + fleetAge(h.age) + ")"))
                    let it = NSMenuItem(title: "", action: nil, keyEquivalent: "")
                    it.attributedTitle = a
                    fmenu.addItem(it)
                    continue
                }
                // ZWARTY wiersz (Pawel, pkt 9): znacznik + nazwa + najwyzsza temperatura
                // + temperatura baterii; komplet szczegolow wyskakuje po KLIKNIECIU
                var bits: [String] = []
                if let c = h.chip { bits.append(String(format: "%.0f °C", c)) }
                if let b = h.battC { bits.append(T("Battery") + String(format: " %.0f °C", b)) }
                let a = NSMutableAttributedString()
                a.append(icon(h.level >= 3 ? "flame.fill"
                              : h.level >= 2 ? "exclamationmark.triangle.fill"
                              : "laptopcomputer", fallback: ">"))
                let toJa = !mojSerial.isEmpty && h.serial == mojSerial
                a.append(NSAttributedString(
                    string: "  " + h.name,
                    attributes: [.font: toJa ? NSFont.boldSystemFont(ofSize: 13)
                                             : NSFont.menuFont(ofSize: 0)]))
                a.append(NSAttributedString(string: "   " + bits.joined(separator: "  ·  "),
                                            attributes: [.font: NSFont.menuFont(ofSize: 0)]))
                let it = NSMenuItem(title: "", action: #selector(fleetDetails(_:)), keyEquivalent: "")
                it.target = self
                it.attributedTitle = a
                it.representedObject = [
                    "name": h.name, "model": h.model, "serial": h.serial,
                    "age": fleetAge(h.age),
                    "chip": h.chip.map { String(format: "%.1f °C", $0) } ?? "-",
                    "batt": h.battC.map { String(format: "%.1f °C", $0) } ?? "-",
                    "fans": h.fans.map { "\($0) rpm" } ?? "-",
                    "watts": h.watts.map { String(format: "%.1f W", $0) } ?? "-",
                    "ram": h.ramPct.map { "\($0)%" } ?? "-",
                    "power": h.onAC ? T("AC adapter")
                                    : T("Battery") + (h.battPct.map { " \($0)%" } ?? ""),
                    "state": [T("calm"), T("warm"), T("HOT - paused"), T("CRITICAL")][min(max(h.level, 0), 3)],
                    "paused": h.paused.joined(separator: ", "),
                ] as [String: String]
                fmenu.addItem(it)
            }
        } else {
            frow(T("no fleet folder - run: fleet --setup"))
        }
        fleetIt.submenu = fmenu
        m.addItem(fleetIt)

        m.addItem(.separator())
        let issuesIt = m.addItem(withTitle: T("Report a problem (GitHub)…"), action: #selector(openIssues), keyEquivalent: "")
        issuesIt.target = self
        issuesIt.image = img("lightbulb")
        // gwiazdka WYCIAGNIETA z podmenu (Pawel, pkt 14): najtansza waluta open source
        // ma byc na wierzchu, nie schowana pod rozwijanym menu
        let pg = m.addItem(withTitle: T("Star it on GitHub…"), action: #selector(shareStar), keyEquivalent: "")
        pg.target = self
        pg.image = img("star")
        // suppi.pl dziala tylko po polsku (BLIK/przelewy, brak wersji EN - research
        // 01.08): espresso przy polskim menu, reszta swiata -> GitHub Sponsors
        if lang == "pl" {
            let coffee = m.addItem(withTitle: T("Buy me a double espresso…"),
                                   action: #selector(buyCoffee), keyEquivalent: "")
            coffee.target = self
            coffee.image = img(MUG_FILL)
        } else {
            let sponsor = m.addItem(withTitle: T("Sponsor on GitHub…"),
                                    action: #selector(sponsorGithub), keyEquivalent: "")
            sponsor.target = self
            sponsor.image = img("heart")
        }

        // "Podaj dalej" (A14): notka w JEZYKU WYBRANYM W MENU + link z UTM share.
        // Bez Facebooka (decyzja Pawla: sharer ucina tekst i wymaga logowania).
        let podaj = NSMenuItem(title: T("Like the paladin? Pass it on!"), action: nil, keyEquivalent: "")
        podaj.image = img("square.and.arrow.up")
        let pd = NSMenu()
        let px = pd.addItem(withTitle: T("Share on X…"), action: #selector(shareX), keyEquivalent: "")
        px.target = self
        px.image = img("at")
        let pm = pd.addItem(withTitle: T("Share by e-mail…"), action: #selector(shareMail), keyEquivalent: "")
        pm.target = self
        pm.image = img("envelope")
        let pc = pd.addItem(withTitle: T("Copy link with note"), action: #selector(shareCopy), keyEquivalent: "")
        pc.target = self
        pc.image = img("doc.on.doc")
        podaj.submenu = pd
        m.addItem(podaj)

        m.addItem(.separator())

        // STOPKA: kolorowe logo firmowe, sygnatura i wysrodkowane Zamknij
        // (autostart przeniesiony na gore, pod wlacznik ochrony - decyzja Pawla 01.08)
        if let footer = FooterLogoRow.make() {
            let fi = NSMenuItem()
            fi.view = footer
            m.addItem(fi)
        }
        let center = NSMutableParagraphStyle()
        center.alignment = .center
        let sig = NSMenuItem(title: "", action: nil, keyEquivalent: "")
        sig.attributedTitle = NSAttributedString(
            string: SIGNATURE,
            attributes: [.paragraphStyle: center, .font: NSFont.systemFont(ofSize: 11),
                         .foregroundColor: NSColor.secondaryLabelColor])
        sig.isEnabled = false
        m.addItem(sig)

        // kreska oddziela creditsy od akcji wyjscia (decyzja Pawla 01.08)
        m.addItem(.separator())
        // do lewej jak kazda inna pozycja (Pawel, pkt 15) - koniec centrowania
        let quitIt = NSMenuItem(title: T("Quit coffee-paladin (protection stops)"),
                                action: #selector(quit), keyEquivalent: "q")
        quitIt.target = self
        quitIt.image = img("power")
        m.addItem(quitIt)
    }

    // --- keep awake (zapis zyczenia; wykonuje demon, bezpiecznik termiczny nadrzedny)

    @objc func awakeOff() { Awake.set(nil) }

    @objc func awakeTimer(_ sender: NSMenuItem) {
        guard let min = sender.representedObject as? Int else { return }
        let t = Date().timeIntervalSince1970
        Awake.set(["mode": "timer", "until": t + Double(min * 60), "set_at": t])
    }

    @objc func awakeForever() { Awake.set(["mode": "forever"]) }

    @objc func awakeApp(_ sender: NSMenuItem) {
        guard let app = sender.representedObject as? String else { return }
        Awake.set(["mode": "app", "app": app])
    }

    @objc func awakeDownload() { Awake.set(["mode": "download"]) }

    // --- ciezkie zadania

    @objc func coresEfficiency() { GuardCfg.set(["job_cores_mode": "efficiency"]) }
    @objc func coresAll() { GuardCfg.set(["job_cores_mode": "all"]) }

    // --- push na telefon

    private var ntfyField: NSTextField?

    @objc func ntfyGenerate() { ntfyField?.stringValue = randomTopic() }

    @objc func toggleNtfy() {
        // switch ON = trzeba wpisac temat (dialog); OFF = czyscimy temat i push milknie
        if GuardCfg.string("ntfy_topic", "").isEmpty {
            pokazModalnie { self.ntfyDialog() }
        } else {
            GuardCfg.set(["ntfy_topic": ""])
        }
    }

    /// Okno modalne odpalane z pozycji menu, ktora jest custom view (SwitchRow):
    /// menu wtedy NIE zamyka sie samo i dalej sledzi mysz, wiec runModal wchodzi
    /// w konflikt z jego petla zdarzen. Ta sama sztuczka co w HeaderRow.mouseUp.
    /// Okno z paladynem NA SRODKU: ikona, tytul, tresc, opcjonalny widok wlasny
    /// (pole tekstowe, lista) i rzad przyciskow. Zwraca indeks klikanego przycisku.
    ///
    /// Dlaczego nie NSAlert: gola binarka bez pakietu .app nie ma wlasnej ikony, wiec
    /// alert siega po systemowa, ktora wyglada jak pusta teczka - a nawet po podmianie
    /// na paladyna NSAlert trzyma ikone przyklejona do lewej krawedzi i nie pozwala jej
    /// wysrodkowac. Skoro paladyn ma stac posrodku wszedzie, wszystkie te okna sa wlasne.
    ///
    /// Tytul i tresc sa ZAWIJANE i maja marginesy, a ich wysokosc jest mierzona
    /// i wliczana w wysokosc okna: jednoliniowy tytul na cala szerokosc ucinal ogon
    /// zdania (polskie "...tego Maca?" potrzebowalo 338 pt przy 300 dostepnych).
    func oknoPaladyna(tytul: String, tresc: String, przyciski: [String],
                      domyslny: Int = 0, dodatek: NSView? = nil,
                      szerokosc SZER: CGFloat = 380) -> Int {
        let MARG: CGFloat = 22

        func zawijana(_ t: String, _ rozmiar: CGFloat, _ bold: Bool,
                      _ kolor: NSColor) -> (NSTextField, CGFloat) {
            // Spacja nierozdzielajaca przed mysnikiem: bez tego zawijanie potrafilo
            // zlamac wiersz DOKLADNIE przed " - " i nastepna linia zaczynala sie od
            // samej kreski ("WYLACZONA" / "- coffee-paladin przeszedl w tryb…").
            let zwiazany = t.replacingOccurrences(of: " - ", with: "\u{00A0}- ")
            let p = NSTextField(wrappingLabelWithString: zwiazany)
            p.font = bold ? .boldSystemFont(ofSize: rozmiar) : .systemFont(ofSize: rozmiar)
            p.textColor = kolor
            p.alignment = .center
            p.preferredMaxLayoutWidth = SZER - 2 * MARG
            return (p, p.sizeThatFits(NSSize(width: SZER - 2 * MARG, height: 600)).height)
        }

        let (etTytul, hTytulu) = zawijana(tytul, 13, true, .labelColor)
        let (etTresc, hTresci) = zawijana(tresc, 11, false, .secondaryLabelColor)
        let hDodatku: CGFloat = dodatek.map { $0.frame.height + 14 } ?? 0

        let hOkna = 18 + 44 + 8 + hTytulu + 10 + hTresci + hDodatku + 18 + 32 + 18
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: SZER, height: hOkna),
                           styleMask: [.titled, .fullSizeContentView],
                           backing: .buffered, defer: false)
        win.titlebarAppearsTransparent = true
        win.titleVisibility = .hidden
        win.isMovableByWindowBackground = true
        win.level = .modalPanel
        win.center()
        let tlo = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: SZER, height: hOkna))
        tlo.material = .popover
        tlo.state = .active
        win.contentView = tlo

        var y = hOkna - 18 - 44
        let ikonaV = NSImageView(frame: NSRect(x: (SZER - 44) / 2, y: y, width: 44, height: 44))
        if let img = NSImage(contentsOfFile: base + "/paladin_welcome.png") { ikonaV.image = img }
        ikonaV.imageScaling = .scaleProportionallyUpOrDown
        tlo.addSubview(ikonaV)

        y -= 8 + hTytulu
        etTytul.frame = NSRect(x: MARG, y: y, width: SZER - 2 * MARG, height: hTytulu)
        tlo.addSubview(etTytul)

        y -= 10 + hTresci
        etTresc.frame = NSRect(x: MARG, y: y, width: SZER - 2 * MARG, height: hTresci)
        tlo.addSubview(etTresc)

        if let d = dodatek {
            y -= 14 + d.frame.height
            d.frame = NSRect(x: (SZER - d.frame.width) / 2, y: y,
                             width: d.frame.width, height: d.frame.height)
            tlo.addSubview(d)
        }

        y -= 18 + 32
        let luka: CGFloat = 10
        // Szerokosc z TRESCI, nie ze stalej. Rosyjskie "Всё равно выключить" potrzebuje
        // 162 pt, a sztywne 130 pt ucinalo je w polowie - na przycisku wylaczajacym
        // ochrone termiczna, czyli przy najpowazniejszej decyzji w programie.
        let probne = przyciski.map { t -> CGFloat in
            let b = NSButton(title: t, target: nil, action: nil)
            b.bezelStyle = .rounded
            b.sizeToFit()
            return b.frame.width + 20
        }
        let szerB = min(max(probne.max() ?? 90, 90), 170)
        let xB = (SZER - (szerB * CGFloat(przyciski.count)
                          + luka * CGFloat(przyciski.count - 1))) / 2
        // KOLEJNOSC: macOS trzyma przycisk potwierdzajacy skrajnie po PRAWEJ, a czlowiek
        // klika odruchowo w prawy dolny rog. Wywolujacy podaje liste "najwazniejszy
        // pierwszy" (bo tak sie ja czyta w kodzie), a rysujemy ja odwrotnie.
        for (i, t) in przyciski.enumerated() {
            let b = NSButton(title: t, target: self, action: #selector(zamknijOknoPaladyna(_:)))
            b.bezelStyle = .rounded
            b.tag = i
            let poz = przyciski.count - 1 - i          // 0 = skrajnie po lewej
            b.frame = NSRect(x: xB + CGFloat(poz) * (szerB + luka), y: y,
                             width: szerB, height: 32)
            if i == domyslny { b.keyEquivalent = "\r" }
            // Escape zamyka oknem tak, jak przycisk anulujacy (a przy jednym OK - jak OK).
            if przyciski.count == 1 || i == przyciski.count - 1 { b.keyEquivalent = "\u{1b}" }
            if i == domyslny { b.keyEquivalent = "\r" }
            tlo.addSubview(b)
        }

        NSApp.activate(ignoringOtherApps: true)
        let wynik = NSApp.runModal(for: win)
        win.orderOut(nil)
        return wynik.rawValue
    }

    /// Rzad przyciskow: szerokosc liczona z TRESCI (rosyjskie etykiety sa o polowe
    /// dluzsze od polskich), potwierdzajacy skrajnie po PRAWEJ zgodnie z macOS,
    /// Escape na anulujacym.
    func rzadPrzyciskow(_ tlo: NSView, _ SZER: CGFloat, _ y: CGFloat,
                        _ tytuly: [String], domyslny: Int, akcja: Selector) {
        let luka: CGFloat = 10
        let probne = tytuly.map { t -> CGFloat in
            let b = NSButton(title: t, target: nil, action: nil)
            b.bezelStyle = .rounded
            b.sizeToFit()
            return b.frame.width + 20
        }
        let szerB = min(max(probne.max() ?? 90, 90), 170)
        let xB = (SZER - (szerB * CGFloat(tytuly.count) + luka * CGFloat(tytuly.count - 1))) / 2
        for (i, t) in tytuly.enumerated() {
            let b = NSButton(title: t, target: self, action: akcja)
            b.bezelStyle = .rounded
            b.tag = i
            let poz = tytuly.count - 1 - i
            b.frame = NSRect(x: xB + CGFloat(poz) * (szerB + luka), y: y, width: szerB, height: 32)
            if i == tytuly.count - 1 { b.keyEquivalent = "\u{1b}" }
            if i == domyslny { b.keyEquivalent = "\r" }
            tlo.addSubview(b)
        }
    }

    @objc func zamknijOknoPaladyna(_ sender: NSButton) {
        NSApp.stopModal(withCode: NSApplication.ModalResponse(rawValue: sender.tag))
    }

    func pokazModalnie(_ akcja: @escaping () -> Void) {
        item.menu?.cancelTracking()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.12) { akcja() }
    }

    @objc func ntfyDialog() {
        let box = NSView(frame: NSRect(x: 0, y: 0, width: 320, height: 58))
        let field = NSTextField(frame: NSRect(x: 0, y: 32, width: 320, height: 24))
        let current = GuardCfg.string("ntfy_topic", "")
        field.stringValue = current.isEmpty ? randomTopic() : current
        box.addSubview(field)
        let gen = NSButton(title: T("Generate"), target: self, action: #selector(ntfyGenerate))
        gen.bezelStyle = .rounded
        gen.frame = NSRect(x: 320 - 110, y: 0, width: 110, height: 28)
        box.addSubview(gen)
        ntfyField = field
        let result = oknoPaladyna(
            tytul: T("Phone push (ntfy.sh)…"),
            tresc: T("The topic name is the ONLY protection: anyone who knows or guesses it can read your alerts and send fake ones. Click Generate for a random unguessable name. On your phone install the ntfy.sh app (from ntfy.sh - mind the lookalike apps) and subscribe to the same topic. Leave empty to disable."),
            przyciski: ["OK", T("Cancel")], dodatek: box)
        ntfyField = nil
        if result == 0 {
            // Temat idzie prosto do URL-a. Spacja albo nowa linia sprawiaja, ze curl
            // w ogole nic nie wysyla (i nikt sie o tym nie dowiaduje), a "#" i "?"
            // publikuja na KROTSZY temat, niz uzytkownik widzi w polu - czyli latwiejszy
            // do zgadniecia. Odrzucamy od razu, zamiast milczec przez tygodnie.
            let temat = field.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
            let dozwolone = CharacterSet(charactersIn:
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
            if !temat.isEmpty &&
                (temat.count > 64 || temat.rangeOfCharacter(from: dozwolone.inverted) != nil) {
                _ = oknoPaladyna(
                    tytul: T("This topic will not work"),
                    tresc: T("Use only letters, digits, _ and -, up to 64 characters. "
                        + "A space stops the push silently, and # or ? publish to a shorter topic "
                        + "than the one you typed."),
                    przyciski: ["OK"])
                return
            }
            GuardCfg.set(["ntfy_topic": temat])
        }
    }

    // --- nazwa we flocie

    @objc func fleetNameDialog() {
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 300, height: 24))
        field.stringValue = GuardCfg.string("fleet_label", "")
        field.placeholderString = T("e.g. render-01, studio-mini, mbp-14")
        if oknoPaladyna(tytul: T("Name this Mac in the fleet…"),
                        tresc: T("With five identical MacBooks the system hostname says nothing. This name shows in the fleet table and menu on every machine. Empty = system hostname."),
                        przyciski: ["OK", T("Cancel")], dodatek: field) == 0 {
            GuardCfg.set(["fleet_label": field.stringValue.trimmingCharacters(in: .whitespaces)])
        }
    }

    // --- autostart

    @objc func toggleAutostart() { Autostart.set(!Autostart.enabled()) }

    /// Tryb "tylko obserwuj" bywa niezrozumialy, a to najwazniejsza opcja dla kogos, kto boi sie
    /// oddac narzedziu wladze nad swoimi procesami — wiec tlumaczymy go wprost.
    @objc func explainDry() {
        let tresc = T("""
Protection is now OFF\n- coffee-paladin has entered watch-only mode.

It still measures everything (chip, GPU, battery, fans) and writes to the event log exactly \
what it WOULD do - "would pause ffmpeg (630% CPU)" - but it sends no signal and never touches \
a single process.

Use it to see whether the thresholds suit your machine before you let the paladin freeze real \
work. Open "Show the guard log" after a heavy job and you will know if it would have interfered \
too eagerly, or not soon enough.

Remember: while this switch is off, NOTHING protects the Mac.\nFlip it back on when you are done.
""")
        _ = oknoPaladyna(tytul: T("Watch only (dry run)"), tresc: tresc,
                         przyciski: ["OK"], szerokosc: 440)
    }

    @objc func enableProtection() { GuardCfg.set(["dry_run": false]) }

    @objc func toggleNotify() { GuardCfg.set(["notify": !GuardCfg.bool("notify", true)]) }
    @objc func toggleDry() {
        let obserwacjaTeraz = !GuardCfg.bool("dry_run", true)
        GuardCfg.set(["dry_run": obserwacjaTeraz])
        // wylaczenie ochrony = powazna decyzja - od razu mowimy, co to znaczy
        if obserwacjaTeraz { pokazModalnie { self.explainDry() } }
    }

    @objc func toggleSound() { GuardCfg.set(["sound": !GuardCfg.bool("sound", true)]) }
    @objc func toggleAwake() { GuardCfg.set(["keep_awake_auto": !GuardCfg.bool("keep_awake_auto", false)]) }

    /// Zmiana jezyka wymaga restartu paska (slownik jest wybierany raz, przy starcie).
    /// Wychodzimy z bledem — launchd (KeepAlive.SuccessfulExit=false) podnosi nas z powrotem.
    @objc func setLang(_ sender: NSMenuItem) {
        guard let code = sender.representedObject as? String, code != lang else { return }
        GuardCfg.set(["lang": code])
        exit(1)
    }

    @objc func toggleItem(_ sender: NSMenuItem) {
        let all = Item.allCases
        guard sender.tag >= 0 && sender.tag < all.count else { return }
        prefs.toggle(all[sender.tag])
        refresh()
    }

    /// Commands go through a file - the daemon executes and clears them.
    func send(_ command: String) {
        try? command.write(toFile: commandPath, atomically: true, encoding: .utf8)
    }

    @objc func freeze() { send("freeze") }
    @objc func toggleFreeze(_ sender: Any?) {
        // stan bierzemy z migawki, nie z klikniecia - guard wykonuje rozkaz w swoim
        // cyklu (do ~15 s), wiec przelacznik potwierdzi sie po nastepnym odswiezeniu
        let s = readSnap()
        if let s = s, !s.paused.isEmpty { send("resume"); return }
        // Reczne zamrozenie to jedyne miejsce, gdzie uzytkownik zatrzymuje SWOJA prace
        // swiadomie. Zanim to zrobi, ma zobaczyc CO konkretnie stanie i czego moze sie
        // po tym spodziewac - bez tego przelacznik jest strzalem w ciemno.
        pokazModalnie { [weak self] in
            guard let self = self else { return }
            guard let wybrane = self.potwierdzZamrozenie(s) else { return }   // anulowane
            if wybrane.isEmpty {
                self.send("freeze")                       // nie bylo z czego wybierac
            } else {
                self.send("freeze:" + wybrane.map(String.init).joined(separator: ","))
            }
        }
    }

    /// Okno potwierdzenia przed recznym zamrozeniem: co konkretnie stanie, z mozliwoscia
    /// odznaczenia pojedynczych procesow. Lista pochodzi z `freeze_candidates` w migawce,
    /// czyli z tego samego zbioru, na ktorym zadziala demon - nie z listy "top CPU".
    ///
    /// WLASNE okno, nie NSAlert: alert trzyma ikone przyklejona do lewej krawedzi
    /// i rezerwuje na nia pas naglowka. Paladyn ma stac na srodku, nad tytulem.
    /// Zwraca nil przy anulowaniu, albo liste PID-ow (pusta = zamroz wszystko, co sie kwalifikuje).
    func potwierdzZamrozenie(_ s: Snap?) -> [Int]? {
        let kandydaci = s?.freezeCandidates ?? []
        let SZER: CGFloat = 360
        let MARG: CGFloat = 20
        let WYS_WIERSZA: CGFloat = 20

        func akapit(_ tekst: String, _ rozmiar: CGFloat, _ kolor: NSColor) -> (NSTextField, CGFloat) {
            let p = NSTextField(wrappingLabelWithString: tekst)
            p.font = .systemFont(ofSize: rozmiar)
            p.textColor = kolor
            p.alignment = .left
            p.preferredMaxLayoutWidth = SZER - 2 * MARG
            return (p, p.sizeThatFits(NSSize(width: SZER - 2 * MARG, height: 400)).height)
        }

        let (a1, h1) = akapit(T("A freeze is not a kill. The process stops between two "
            + "instructions, keeps its memory and its open files, and carries on from the "
            + "same place when you switch this off. It is safe."), 11, .labelColor)
        let (a2, h2) = akapit(T("What a freeze does NOT protect: anything waiting on the "
            + "network or watching a clock will notice the gap. A download or an upload can "
            + "drop, a server can disconnect you, a video call freezes, a game stops "
            + "responding."), 11, .secondaryLabelColor)
        let (a3, h3) = akapit(T("The paladin will NEVER touch the system, Finder, your "
            + "terminal or your AI agent."), 11, .labelColor)

        let hLista: CGFloat = kandydaci.isEmpty ? 0
            : WYS_WIERSZA * CGFloat(kandydaci.count + 1) + 8
        let (pusty, hPusty) = akapit(T("Nothing heavy is running right now. Anything that "
            + "gets heavy will be frozen until you switch this back off."), 11, .secondaryLabelColor)
        let hPustego: CGFloat = kandydaci.isEmpty ? hPusty + 10 : 0

        let tytul = NSTextField(wrappingLabelWithString: T("Freeze heavy jobs now?"))
        tytul.font = .boldSystemFont(ofSize: 13)
        tytul.alignment = .center
        tytul.preferredMaxLayoutWidth = SZER - 2 * MARG
        let hTytulu = tytul.sizeThatFits(NSSize(width: SZER - 2 * MARG, height: 200)).height

        let hOkna = 18 + 44 + 8 + hTytulu + 12 + hLista + hPustego
                  + h1 + 10 + h2 + 10 + h3 + 16 + 32 + 18
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: SZER, height: hOkna),
                           styleMask: [.titled, .fullSizeContentView],
                           backing: .buffered, defer: false)
        win.titlebarAppearsTransparent = true
        win.titleVisibility = .hidden
        win.isMovableByWindowBackground = true
        win.level = .modalPanel
        win.center()
        let tlo = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: SZER, height: hOkna))
        tlo.material = .popover
        tlo.state = .active
        win.contentView = tlo

        var y = hOkna - 18 - 44
        let ikonaV = NSImageView(frame: NSRect(x: (SZER - 44) / 2, y: y, width: 44, height: 44))
        if let img = NSImage(contentsOfFile: base + "/paladin_welcome.png") { ikonaV.image = img }
        ikonaV.imageScaling = .scaleProportionallyUpOrDown
        tlo.addSubview(ikonaV)

        y -= 8 + hTytulu
        tytul.frame = NSRect(x: MARG, y: y, width: SZER - 2 * MARG, height: hTytulu)
        tlo.addSubview(tytul)

        var przelaczniki: [NSButton] = []
        y -= 12
        if kandydaci.isEmpty {
            y -= hPusty + 10
            pusty.frame = NSRect(x: MARG, y: y, width: SZER - 2 * MARG, height: hPusty)
            tlo.addSubview(pusty)
        } else {
            y -= WYS_WIERSZA
            let wszystkie = NSButton(checkboxWithTitle: T("Freeze all of them"),
                                     target: self, action: #selector(przelaczWszystkie(_:)))
            wszystkie.state = .on
            wszystkie.font = .systemFont(ofSize: 12, weight: .medium)
            wszystkie.frame = NSRect(x: MARG, y: y, width: SZER - 2 * MARG, height: WYS_WIERSZA)
            tlo.addSubview(wszystkie)
            for k in kandydaci {
                y -= WYS_WIERSZA
                let c = NSButton(checkboxWithTitle: "\(k.name)   \(k.cpu)% CPU   pid \(k.pid)",
                                 target: nil, action: nil)
                c.state = .on
                c.tag = k.pid
                c.font = .systemFont(ofSize: 11)
                // szary, zeby wybor procesow nie krzyczal mocniej niz sama decyzja
                c.contentTintColor = .secondaryLabelColor
                c.frame = NSRect(x: MARG + 16, y: y, width: SZER - 2 * MARG - 16, height: WYS_WIERSZA)
                tlo.addSubview(c)
                przelaczniki.append(c)
            }
            y -= 8
            checkboxyProcesow = przelaczniki
        }

        for (p, h) in [(a1, h1), (a2, h2), (a3, h3)] {
            y -= h
            p.frame = NSRect(x: MARG, y: y, width: SZER - 2 * MARG, height: h)
            tlo.addSubview(p)
            y -= 10
        }

        y -= 6 + 32
        rzadPrzyciskow(tlo, SZER, y, [T("Freeze"), T("Cancel")], domyslny: 0,
                       akcja: #selector(zamknijZamrozenie(_:)))

        NSApp.activate(ignoringOtherApps: true)
        let wynik = NSApp.runModal(for: win)
        win.orderOut(nil)
        defer { checkboxyProcesow = [] }
        guard wynik.rawValue == 0 else { return nil }
        if przelaczniki.isEmpty { return [] }
        return przelaczniki.filter { $0.state == .on }.map { $0.tag }
    }

    @objc func zamknijZamrozenie(_ sender: NSButton) {
        NSApp.stopModal(withCode: NSApplication.ModalResponse(rawValue: sender.tag))
    }

    @objc func przelaczWszystkie(_ sender: NSButton) {
        for c in checkboxyProcesow { c.state = sender.state }
    }
    @objc func resume() { send("resume") }

    @objc func reportDialog() {
        // WLASNE okno, nie NSAlert: alert rezerwuje pas na swoj naglowek nawet
        // przy pustych tekstach - zostawal wielki pusty prostokat u gory (Pawel x3).
        let SZER: CGFloat = 300
        let notka = NSTextField(wrappingLabelWithString:
            T("Included: hardware, battery, sudden shutdowns, interventions, measurement timeline."))
        notka.font = .systemFont(ofSize: 11)
        notka.textColor = .secondaryLabelColor
        notka.alignment = .center
        notka.preferredMaxLayoutWidth = SZER - 32
        let hNotki = notka.sizeThatFits(NSSize(width: SZER - 32, height: 200)).height

        let hOkna: CGFloat = 16 + 44 + 6 + 18 + 4 + 15 + 12 + 24 + 6 + 24 + 10 + 20
                            + 8 + hNotki + 14 + 32 + 16
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: SZER, height: hOkna),
                           styleMask: [.titled, .fullSizeContentView],
                           backing: .buffered, defer: false)
        win.titlebarAppearsTransparent = true
        win.titleVisibility = .hidden
        win.isMovableByWindowBackground = true
        win.level = .modalPanel
        win.center()
        let tlo = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: SZER, height: hOkna))
        tlo.material = .popover
        tlo.state = .active
        win.contentView = tlo

        var y = hOkna - 16 - 44
        let ikonaV = NSImageView(frame: NSRect(x: (SZER - 44) / 2, y: y, width: 44, height: 44))
        if let img = NSImage(contentsOfFile: base + "/paladin_welcome.png") { ikonaV.image = img }
        ikonaV.imageScaling = .scaleProportionallyUpOrDown
        tlo.addSubview(ikonaV)

        y -= 6 + 18
        let tytul = NSTextField(labelWithString: T("Export report for a repair shop"))
        tytul.font = .boldSystemFont(ofSize: 13)
        tytul.alignment = .center
        tytul.frame = NSRect(x: 0, y: y, width: SZER, height: 18)
        tlo.addSubview(tytul)

        y -= 4 + 15
        let podtytul = NSTextField(labelWithString: T("Pick the report period."))
        podtytul.font = .systemFont(ofSize: 11)
        podtytul.textColor = .secondaryLabelColor
        podtytul.alignment = .center
        podtytul.frame = NSRect(x: 0, y: y, width: SZER, height: 15)
        tlo.addSubview(podtytul)

        let szerPary: CGFloat = 42 + 4 + 118
        let x0 = (SZER - szerPary) / 2
        y -= 12 + 24
        let od = NSDatePicker(frame: NSRect(x: x0 + 46, y: y, width: 118, height: 24))
        od.datePickerStyle = .textFieldAndStepper
        od.datePickerElements = .yearMonthDay
        od.dateValue = Date().addingTimeInterval(-14 * 86400)
        tlo.addSubview(od)
        let odL = NSTextField(labelWithString: T("From:"))
        odL.frame = NSRect(x: x0, y: y + 4, width: 42, height: 16)
        odL.alignment = .right
        tlo.addSubview(odL)

        y -= 6 + 24
        let doP = NSDatePicker(frame: NSRect(x: x0 + 46, y: y, width: 118, height: 24))
        doP.datePickerStyle = .textFieldAndStepper
        doP.datePickerElements = .yearMonthDay
        doP.dateValue = Date()
        // bez tego odwrocony zakres szedl prosto do thermal-report i wracal pusty raport
        doP.maxDate = Date()
        od.maxDate = Date()
        tlo.addSubview(doP)
        let doL = NSTextField(labelWithString: T("To:"))
        doL.frame = NSRect(x: x0, y: y + 4, width: 42, height: 16)
        doL.alignment = .right
        tlo.addSubview(doL)

        y -= 10 + 20
        let calosc = NSButton(checkboxWithTitle: T("Everything on record"), target: nil, action: nil)
        calosc.sizeToFit()
        calosc.frame = NSRect(x: (SZER - calosc.frame.width) / 2, y: y,
                              width: calosc.frame.width, height: 20)
        tlo.addSubview(calosc)

        y -= 8 + hNotki
        notka.frame = NSRect(x: 16, y: y, width: SZER - 32, height: hNotki)
        tlo.addSubview(notka)

        y -= 14 + 32
        let szerB: CGFloat = 80, luka: CGFloat = 8
        let xB = (SZER - (3 * szerB + 2 * luka)) / 2
        for (i, tytulB) in ["PDF", "TXT", T("Cancel")].enumerated() {
            let b = NSButton(title: tytulB, target: self, action: #selector(zamknijRaport(_:)))
            b.bezelStyle = .rounded
            b.tag = i
            b.frame = NSRect(x: xB + CGFloat(i) * (szerB + luka), y: y, width: szerB, height: 32)
            if i == 0 { b.keyEquivalent = "\r" }
            tlo.addSubview(b)
        }

        NSApp.activate(ignoringOtherApps: true)
        let wynik = NSApp.runModal(for: win)
        win.orderOut(nil)
        guard wynik.rawValue != 2 else { return }
        let f = DateFormatter()
        // en_US_POSIX obowiazkowo: bez tego na regionie tajskim data wychodzi w kalendarzu
        // buddyjskim (2569-08-02), a na saudyjskim cyframi arabskimi - raport dostaje
        // zakres, ktorego nie rozumie, i wraca do domyslnych 7 dni albo jest pusty.
        f.locale = Locale(identifier: "en_US_POSIX")
        f.calendar = Calendar(identifier: .gregorian)
        f.timeZone = TimeZone.current
        f.dateFormat = "yyyy-MM-dd"
        let zakres: [String] = calosc.state == .on
            ? ["--all"]
            : ["--from", f.string(from: od.dateValue), "--to", f.string(from: doP.dateValue)]
        report(pdf: wynik.rawValue == 0, zakres: zakres)
    }

    @objc func fleetDetails(_ sender: NSMenuItem) {
        // wlasne okno zamiast NSAlert (Pawel): wszystko na osi, zero pustych rezerw
        guard let d = sender.representedObject as? [String: String] else { return }
        var linie: [String] = []
        if let m = d["model"], !m.isEmpty { linie.append(m) }
        if let s = d["serial"], !s.isEmpty { linie.append("SN " + s) }
        linie.append(T("Chip") + ": " + (d["chip"] ?? "-") + "   ·   "
                     + T("Battery") + ": " + (d["batt"] ?? "-"))
        linie.append(T("Fans") + ": " + (d["fans"] ?? "-") + "   ·   "
                     + T("draw") + ": " + (d["watts"] ?? "-"))
        linie.append("RAM: " + (d["ram"] ?? "-") + "   ·   " + (d["power"] ?? "-"))
        linie.append(T("State") + ": " + (d["state"] ?? "-"))
        if let p = d["paused"], !p.isEmpty { linie.append(T("paused") + ": " + p) }
        linie.append(T("Snapshot") + ": " + (d["age"] ?? "-"))

        let SZER: CGFloat = 240
        let tekst = NSTextField(wrappingLabelWithString: linie.joined(separator: "\n"))
        tekst.font = .systemFont(ofSize: 12)
        tekst.alignment = .center
        tekst.preferredMaxLayoutWidth = SZER - 24
        let hTekstu = tekst.sizeThatFits(NSSize(width: SZER - 24, height: 400)).height

        let hOkna: CGFloat = 16 + 44 + 6 + 18 + 8 + hTekstu + 14 + 32 + 16
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: SZER, height: hOkna),
                           styleMask: [.titled, .fullSizeContentView],
                           backing: .buffered, defer: false)
        win.titlebarAppearsTransparent = true
        win.titleVisibility = .hidden
        win.isMovableByWindowBackground = true
        win.level = .modalPanel
        win.center()
        let tlo = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: SZER, height: hOkna))
        tlo.material = .popover
        tlo.state = .active
        win.contentView = tlo

        var y = hOkna - 16 - 44
        let ikonaV = NSImageView(frame: NSRect(x: (SZER - 44) / 2, y: y, width: 44, height: 44))
        if let img = NSImage(contentsOfFile: base + "/paladin_welcome.png") { ikonaV.image = img }
        ikonaV.imageScaling = .scaleProportionallyUpOrDown
        tlo.addSubview(ikonaV)

        y -= 6 + 18
        let tytul = NSTextField(labelWithString: d["name"] ?? "?")
        tytul.font = .boldSystemFont(ofSize: 13)
        tytul.alignment = .center
        tytul.frame = NSRect(x: 0, y: y, width: SZER, height: 18)
        tlo.addSubview(tytul)

        y -= 8 + hTekstu
        tekst.frame = NSRect(x: 12, y: y, width: SZER - 24, height: hTekstu)
        tlo.addSubview(tekst)

        y -= 14 + 32
        let ok = NSButton(title: "OK", target: self, action: #selector(zamknijRaport(_:)))
        ok.bezelStyle = .rounded
        ok.tag = 0
        ok.keyEquivalent = "\r"
        ok.frame = NSRect(x: (SZER - 90) / 2, y: y, width: 90, height: 32)
        tlo.addSubview(ok)

        NSApp.activate(ignoringOtherApps: true)
        NSApp.runModal(for: win)
        win.orderOut(nil)
    }

    @objc func zamknijRaport(_ sender: NSButton) {
        NSApp.stopModal(withCode: NSApplication.ModalResponse(rawValue: sender.tag))
    }

    func report(pdf: Bool, zakres: [String] = ["--days", "14"]) {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: reportBin)
        p.arguments = zakres + (pdf ? ["--pdf"] : [])
        let pipe = Pipe()
        p.standardOutput = pipe
        do { try p.run() } catch { return }
        p.waitUntilExit()
        let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        let path = out.trimmingCharacters(in: .whitespacesAndNewlines)
        if !path.isEmpty {
            NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
        }
    }

    /// Pozycja ratunkowa z menu "brak danych": podnosi demona przez launchd.
    @objc func restartGuarda() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        p.arguments = ["kickstart", "-k", "gui/\(getuid())/pl.pawel.coffee-paladin"]
        try? p.run()
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self] in self?.refresh() }
    }

    @objc func openLog() { NSWorkspace.shared.open(URL(fileURLWithPath: logPath)) }

    // notka "Podaj dalej" w biezacym jezyku menu - jeden klucz, tlumaczenia w DICTS
    private var notkaPodajDalej: String {
        T("Is your Mac heating up with AI and renders? coffee-paladin watches the battery (temperature and charge), the chip (CPU) and the GPU. It pauses heavy jobs when the system overheats and resumes them by itself once the temperature drops, so you can sleep peacefully (literally!). Open source, free, for you:")
    }

    @objc func shareX() {
        // osobny, krotszy tekst pod X (limit 280 znakow; tresc Pawla, 01.08)
        var c = URLComponents(string: "https://x.com/intent/post")!
        // URLComponents sam robi percent-encoding - polskie znaki i emoji nie rozwala linku
        c.queryItems = [URLQueryItem(name: "text",
                                     value: String(format: T("Is your Mac heating up with AI and renders? coffee-paladin watches battery, chip and GPU temperatures. It pauses heavy jobs and resumes them by itself once the temperature drops.\n\nOpen source, free, for you:\n%@\n\n#panbookovsky #macbook #protect #temperature #guard"),
                                                   linkPodajDalej()))]
        if let u = c.url { NSWorkspace.shared.open(u) }
    }

    @objc func shareMail() {
        // osobisty ton "do kolegi" + GIF paladyna w zalaczniku; mailto nie umie
        // zalacznikow, wiec komponujemy wiadomosc przez Mail.app (osascript).
        // Argumenty ida przez argv - zero pieklarni z escapowaniem cudzyslowow.
        let temat = T("you have to see this: coffee-paladin")
        let tresc = String(format: T("Hey,\n\nI found something you need on your Mac: coffee-paladin. It watches the chip, GPU and battery temperatures, and when things get hot it pauses heavy jobs and resumes them by itself once the machine cools down.\n\nIt is damn good, because the pause is lossless (the process freezes and continues from the same spot), it sends nothing anywhere, and it is free, open source:\n%@\n\nThe knight with the coffee in the attachment is its mascot.\n\nCheers!"), linkPodajDalej())
            .replacingOccurrences(of: "\\n", with: "\n")
        let gif = base + "/paladin_welcome.gif"
        var skrypt = [
            "on run argv",
            "tell application \"Mail\"",
            "set msg to make new outgoing message with properties {subject:(item 1 of argv), content:(item 2 of argv), visible:true}",
        ]
        if FileManager.default.fileExists(atPath: gif) {
            skrypt.append("tell msg to make new attachment with properties {file name:(POSIX file (item 3 of argv))} at after the last paragraph of content")
        }
        skrypt += ["activate", "end tell", "end run"]
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        var argumenty: [String] = []
        for linia in skrypt { argumenty += ["-e", linia] }
        argumenty += [temat, tresc, gif]
        p.arguments = argumenty
        try? p.run()
    }

    @objc func shareCopy() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(notkaPodajDalej + "\n" + linkPodajDalej(), forType: .string)
    }

    @objc func sponsorGithub() {
        if let u = zUTM("https://github.com/sponsors/pawelkwaczynski") { NSWorkspace.shared.open(u) }
    }

    @objc func shareStar() {
        if let u = zUTM("https://github.com/pawelkwaczynski/coffee-paladin", medium: "share") {
            NSWorkspace.shared.open(u)
        }
    }

    @objc func openGuide() { Guide.shared.show() }

    @objc func openIssues() {
        if let u = zUTM("https://github.com/pawelkwaczynski/coffee-paladin/issues") { NSWorkspace.shared.open(u) }
    }

    @objc func buyCoffee() {
        if let u = zUTM("https://suppi.pl/panbookovsky") { NSWorkspace.shared.open(u) }
    }

    /// Wyjscie znaczy KONIEC PROGRAMU, nie tylko schowanie ikony: zatrzymujemy demona
    /// i pasek. Wczesniej "Zamknij pasek" zostawialo demona przy zyciu - to bylo mylace
    /// w druga strone (ludzie myśleli, ze wylaczyli ochronę, a ona dzialala).
    /// Teraz etykieta i skutek sa te same, a przed nieodwracalnym krokiem pytamy.
    @objc func quit() {
        // WLASNE okno, jak przy recznym wstrzymaniu: to najpowazniejsza decyzja
        // w calym menu, wiec paladyn stoi na srodku, a nie doklejony do lewej
        // krawedzi jak w NSAlert.
        let SZER: CGFloat = 340, MARG: CGFloat = 20
        let tresc = NSTextField(wrappingLabelWithString:
            T("The daemon and the menu bar both stop. Nothing will pause hot jobs until you start it again."))
        tresc.font = .systemFont(ofSize: 11)
        tresc.textColor = .secondaryLabelColor
        tresc.alignment = .center
        tresc.preferredMaxLayoutWidth = SZER - 2 * MARG
        let hTresci = tresc.sizeThatFits(NSSize(width: SZER - 2 * MARG, height: 300)).height

        // Tytul MUSI sie zawijac i miec marginesy. Jednoliniowa etykieta na cala
        // szerokosc okna ucinala ogon zdania (po polsku gubil sie znak zapytania),
        // a dluzsze tlumaczenia - rosyjskie i hiszpanskie - straciłyby wiecej.
        let tytul = NSTextField(wrappingLabelWithString:
            T("Turn off thermal protection for this Mac?"))
        tytul.font = .boldSystemFont(ofSize: 13)
        tytul.alignment = .center
        tytul.preferredMaxLayoutWidth = SZER - 2 * MARG
        let hTytulu = tytul.sizeThatFits(NSSize(width: SZER - 2 * MARG, height: 200)).height

        let hOkna = 18 + 44 + 8 + hTytulu + 10 + hTresci + 18 + 32 + 18
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: SZER, height: hOkna),
                           styleMask: [.titled, .fullSizeContentView],
                           backing: .buffered, defer: false)
        win.titlebarAppearsTransparent = true
        win.titleVisibility = .hidden
        win.isMovableByWindowBackground = true
        win.level = .modalPanel
        win.center()
        let tlo = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: SZER, height: hOkna))
        tlo.material = .popover
        tlo.state = .active
        win.contentView = tlo

        var y = hOkna - 18 - 44
        let ikonaV = NSImageView(frame: NSRect(x: (SZER - 44) / 2, y: y, width: 44, height: 44))
        if let img = NSImage(contentsOfFile: base + "/paladin_welcome.png") { ikonaV.image = img }
        ikonaV.imageScaling = .scaleProportionallyUpOrDown
        tlo.addSubview(ikonaV)

        y -= 8 + hTytulu
        tytul.frame = NSRect(x: MARG, y: y, width: SZER - 2 * MARG, height: hTytulu)
        tlo.addSubview(tytul)

        y -= 10 + hTresci
        tresc.frame = NSRect(x: MARG, y: y, width: SZER - 2 * MARG, height: hTresci)
        tlo.addSubview(tresc)

        y -= 18 + 32
        // domyslnym klawiszem jest ANULUJ - Enter nie moze wylaczac ochrony
        rzadPrzyciskow(tlo, SZER, y, [T("Quit anyway"), T("Cancel")], domyslny: 1,
                       akcja: #selector(zamknijZamrozenie(_:)))

        NSApp.activate(ignoringOtherApps: true)
        let wynik = NSApp.runModal(for: win)
        win.orderOut(nil)
        guard wynik.rawValue == 0 else { return }

        // Demon idzie pierwszy - gdyby pasek zginal wczesniej, uzytkownik zostalby
        // z dzialajaca ochrona i bez zadnego sposobu, zeby ja zobaczyc.
        let uid = String(getuid())
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        p.arguments = ["bootout", "gui/\(uid)/pl.pawel.coffee-paladin"]
        try? p.run()
        p.waitUntilExit()

        let b = Process()
        b.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        b.arguments = ["bootout", "gui/\(uid)/pl.pawel.coffee-paladin-bar"]
        try? b.run()          // nie czekamy: to polecenie ubija nas samych
        NSApp.terminate(nil)
    }
}

// Agenci i skrypty wolaja `heatbar --once`/`--json` odruchowo — bez tej obslugi apka
// paska wisi bez okna i blokuje automat do timeoutu (tamtej sesji: 2 minuty). Drukujemy
// migawke guarda (to samo, co pasek czyta co 5 s) i wychodzimy natychmiast (B6).
if CommandLine.arguments.contains("--once") || CommandLine.arguments.contains("--json") {
    if let d = FileManager.default.contents(atPath: statusPath),
       let s = String(data: d, encoding: .utf8) {
        print(s)
        exit(0)
    }
    FileHandle.standardError.write(
        "no status.json - the coffee-paladin daemon is not running\n".data(using: .utf8)!)
    exit(1)
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)   // no Dock icon, no window
let bar = Bar()
app.run()
