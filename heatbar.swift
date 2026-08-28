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

let VERSION = "3.3.0"
let APPNAME = "coffee-paladin"
let CODENAME = "Cold Brew"
let SIGNATURE = "\(APPNAME) v\(VERSION) \u{201E}\(CODENAME)\u{201D}  ·  by panbookovsky"

// Workspace directory. TG_BASE lets the menu bar run isolated (UI tests, demos)
// without a welcome-window click changing the live installation config.
// Note: expandingTildeInPath does NOT honor a substituted HOME, so this needs a
// separate variable instead of a home-directory trick.
let base = ProcessInfo.processInfo.environment["TG_BASE"].map {
    NSString(string: $0).expandingTildeInPath
} ?? NSString(string: "~/.coffee-paladin").expandingTildeInPath
let statusPath = base + "/status.json"
let historyPath = base + "/history.csv"
let logPath = base + "/guard.log"
let commandPath = base + "/command"
let configPath = base + "/config.json"
let prefsPath = base + "/heatbar.json"
let activityPath = base + "/agent_activity.json"
let agentEventsDir = base + "/agent_events"
let ccusageCachePath = base + "/ccusage_cache.json"
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
    "Sponsor on GitHub…": "Wesprzyj na GitHubie…",
    "!": "!",
    "no data - is coffee-paladin running?": "brak danych - czy coffee-paladin działa?",
    "data is stale (%@) - the guard may have died": "dane nieświeże (%@) - guard mógł paść",
    " (remembered)": " (zapamiętany)",
    "the Mac shut down without warning: %@": "Mac zgasł bez ostrzeżenia: %@",
    "Battery:  %@": "Bateria:  %@",
    "Memory used of total, load average over cores, fan speed": "Pamiec uzyta z calosci, srednie obciazenie na rdzenie, obroty wentylatorow",
    "stopped": "stoi", "%d rpm": "%d obr/min", "%@ rpm": "%@ obr/min", "n/a": "n/d",
    "Draw:  %.1f W": "Pobór:  %.1f W",
    "Disk:  %d / %d GB used (%d%%)": "Dysk:  %d / %d GB zajęte (%d%%)",
    "Power:  %@": "Zasilanie:  %@",
    "AC adapter": "zasilacz", "battery %@": "bateria %@",
    "Load:  %.2f / %d cores": "Obciążenie:  %.2f / %d rdzeni",
    "Throttling: CPU capped at %d%% speed": "Dławienie: CPU ścięte do %d%% prędkości",
    "   readings: %.0f-%.0f C": "   ostatnie pomiary: %.0f-%.0f C",
    "rising %.1f C/min - about %.0f min to pause": "rośnie %.1f C/min - do pauzy ok. %.0f min",
    "rising %.1f C/min": "rośnie %.1f C/min",
    "What is loading the Mac": "Co obciąża Maca",
    "Held: %d": "Wstrzymane: %d",
    "  (by hand)": "  (ręcznie)",
    "Calm": "Spokojnie",
    "Warming up": "Robi się ciepło",
    "Hot": "Gorąco",
    "Critical": "Krytycznie",
    "Under the guard (safe-run):": "Pod nadzorem (safe-run):",
    "Heating the most (CPU stands in for heat):": "Najbardziej grzeją (CPU zastępuje pomiar ciepła):",
    "cores": "rdzeni",
    "Chip thresholds:  pause %.0f °C, kill %.0f °C": "Progi chipa:  pauza %.0f °C, ubicie %.0f °C",
    "Eating the most RAM:": "Najwięcej RAM używają:",
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
    "OFF - the Mac is only being watched": "WYŁĄCZONE — Mac jest tylko obserwowany",
    "Show in the bar": "Pokaż na pasku",
    "Show all": "Pokaż wszystko",
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
    "careful - under ordinary heavy work the chip already sits here, so long jobs will be paused often": "ostrożnie - przy zwykłej ciężkiej pracy chip już tu siedzi, więc długie zadania będą często wstrzymywane",
    "recommended - the pause comes well before the chip's own limiter": "zalecane - pauza przychodzi na długo przed własnym ogranicznikiem chipa",
    "late - a job will run hot for a while before anything happens": "późno - zadanie pogrzeje przez chwilę, zanim cokolwiek się stanie",
    "almost never - the reading rarely goes higher than this, so the pause may not come at all": "prawie nigdy - odczyt rzadko bywa wyższy, więc pauza może w ogóle nie przyjść",
    "no limit: a job may use the whole machine": "bez limitu: zadanie może zająć całą maszynę",
    "about %d of %d cores; the job gets tiny micro-pauses (works for any program)": "około %d z %d rdzeni; zadanie dostaje malutkie mikropauzy (działa dla każdego programu)",
    "Battery gate": "Wstrzymuj na baterii poniżej",
    "pause below this charge when unplugged": "bez zasilacza ciężkie zadania poczekają na ładowarkę",
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
    "Agent activity": "Aktywność agentów AI",
    "Live (from hooks):": "Na żywo (z hooków):",
    "Agents today: %@ (ccusage)": "Agenci dzisiaj: %@ (ccusage)",
    "Per agent": "Na agenta",
    "Per model": "Na model",
    "Active block (counted by ccusage, not your account limit)": "Aktywny blok (liczy go ccusage, to nie limit konta)",
    "%@ tokens · %@/min · %.0f min left": "%@ tokenów · %@/min · zostało %.0f min",
    "%@ tokens · %.0f min left": "%@ tokenów · zostało %.0f min",
    "at this rate the guard pauses in ~%.0f min, before the block ends": "w tym tempie strażnik wstrzyma pracę za ~%.0f min, przed końcem bloku",
    "%@ tokens": "%@ tokenów",
    "Claude limits: %@": "Limity Claude: %@",
    "Thermal protection": "Ochrona termiczna",
    "%@: %d%%": "%@: %d%%",
    "(resets %@)": "(reset %@)",
    "5h limit": "limit 5 h",
    "7d limit": "limit 7 dni",
    "context": "kontekst",
    "%@  ·  idle": "%@  ·  bezczynna",
    "%@  ·  %.1f cores in its tree": "%@  ·  %.1f rdzeni w drzewie",
    "Chip": "Chip",
    "Battery": "Bateria",
    "Fans": "Wentylatory",
    "State": "Stan",
    "Snapshot": "Migawka",
    "Export report": "Zapisz raport",
    "Start the guard again": "Uruchom strażnika ponownie",
    "no AI session is running right now": "żadna sesja AI teraz nie działa",
    "… %d more": "… jeszcze %d",
    "AI session marker": "Znacznik sesji AI",
    "Battery temperature (from 40 °C)": "Temperatura baterii (od 40 °C)",
    "Fan rpm (when spinning)": "Obroty wentylatorów (gdy się kręcą)",
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
    "Keep awake": "Nie usypiaj Maca",
    "Off": "Wyłącz",
    "%d min": "%d min",
    "%d h": "%d h",
    "Indefinitely": "Bezterminowo",
    "While an app is running": "Dopóki działa aplikacja",
    "While downloading (network active)": "Dopóki trwa pobieranie (aktywna sieć)",
    "released automatically when the Mac gets hot": "zwalniane samo, gdy Mac się grzeje",
    "Keep-awake: %@ left": "Czuwanie: zostało %@",
    "Held right now: %d": "Wstrzymane teraz: %d",
    "Turn thermal protection off?": "Wyłączyć ochronę termiczną?",
    "The paladin will keep measuring and writing down what it would have paused, and will stop nothing at all, even above %.0f °C.": "Paladyn dalej będzie mierzył i zapisywał, co by wstrzymał, ale nie zatrzyma niczego, nawet powyżej %.0f °C.",
    "Turn protection off": "Wyłącz ochronę",
    "Keep it on": "Zostaw włączoną",
    "Watch only": "Tylko obserwuj",
    "The paladin keeps measuring and writes to the log what it would pause, but it stops nothing until you switch this back on.": "Paladyn dalej mierzy i zapisuje w logu, co by wstrzymał, ale niczego nie zatrzyma, dopóki nie włączysz ochrony z powrotem.",
    "Thermal protection is on": "Ochrona termiczna włączona",
    "Above %.0f °C the paladin pauses heavy jobs and starts them again by itself at %.0f °C.": "Powyżej %.0f °C paladyn wstrzymuje ciężkie zadania i sam je wznawia przy %.0f °C.",
    "Jobs resumed": "Zadania wznowione",
    "Held jobs (%d) are running again; if the chip is still hot the paladin pauses them again on its next reading.": "Wstrzymane zadania (%d) znów działają; jeśli chip nadal jest gorący, paladyn wstrzyma je ponownie przy następnym odczycie.",
    "Heavy processes right now: %d": "Ciężkie procesy teraz: %d",
    "Measurement interval": "Częstotliwość pomiarów",
    "Pick the report period.": "Wybierz okres raportu.",
    "Included: hardware, battery, sudden shutdowns, interventions, measurement timeline.":
        "W raporcie: sprzęt, bateria, nagłe wyłączenia, interwencje, oś pomiarów.",
    "From:": "Od:",
    "This topic will not work": "Ten temat nie zadziała",
    "Use only letters, digits, _ and -, up to 64 characters. A space stops the push silently, and # or ? publish to a shorter topic than the one you typed.": "Używaj tylko liter, cyfr, _ i -, do 64 znaków. Spacja cicho blokuje push, a # albo ? publikują na krótszy temat niż ten, który wpisałeś.",
    "First steps with the paladin": "Pierwsze kroki z paladynem",
    "Phone notifications…": "Powiadomienia na telefon…",
    "First steps…": "Pierwsze kroki...",
    "WHAT IT CAN DO\n• The paladin watches the chip, the battery, the fans and the power source - by default a reading every 15 seconds.\n• When things get too hot, it FREEZES heavy processes instead of letting the Mac cook itself. The pause destroys nothing: the process stops mid-instruction and continues once the chip cools. Example? Measured: 89 °C → 60 °C in 19 seconds, no loss.\n• It finds the real culprit: CPU is counted across the whole process tree, so it also sees a script that spawns hundreds of short jobs while using almost nothing itself.\n• On battery at 10% or less it pauses long jobs - they resume when you plug in, or once the charge is back above 25% (both figures are defaults; the Battery gate slider moves them together).\n• It keeps a black box: after a hard failure the last 8 readings survive. One click turns them into a report for a repair shop (should you ever need it).\n• Keep-awake - works like the well-known Caffeine or Amphetamine, but unlike them it comes with a fuse: the sleep lock is released the moment the Mac reaches pause level. Sleep is the fastest cooling there is.": "CO POTRAFI\n• Paladyn pilnuje chipa, baterii, wentylatorów i zasilania - domyślny pomiar co 15 sekund.\n• Gdy robi się za gorąco, ZAMRAŻA ciężkie procesy zamiast pozwolić Macowi się ugotować. Pauza niczego nie niszczy: proces staje w miejscu i rusza dalej, gdy chip ostygnie. Przykład? Zmierzone: 89 °C → 60 °C w 19 sekund, obliczenia bez strat.\n• Znajduje prawdziwego winowajcę: liczy CPU całego drzewa procesów, więc widzi też skrypt, który odpala setki krótkich zadań i sam prawie nic nie zużywa.\n• Na baterii 10% i mniej wstrzymuje długie obliczenia - wznowi po podpięciu ładowarki albo gdy naładujesz powyżej 25% (obie liczby to wartości domyślne, suwak „Bramka baterii” przesuwa je razem).\n• Prowadzi czarną skrzynkę: po twardej awarii zostaje 8 ostatnich pomiarów. Jednym kliknięciem złożysz z tego raport dla serwisu (w razie potrzeby).\n• „Nie usypiaj Maca” - działa jak znane programy Caffeine czy Amphetamine, ale w odróżnieniu od nich robi to z bezpiecznikiem: blokada snu puszcza w momencie, gdy Mac dochodzi do progu pauzy. Sen chłodzi najszybciej.",
    "WHAT WILL HAPPEN\n• Your choice in the welcome window decides how you start.\n\n\"Watch only\" mode: the paladin measures, logs and alerts, but PAUSES NOTHING.\n\n\"Enable protection\" mode: it pauses at the defined thresholds.\n\nSwitching is easy - one switch at the top of the menu.\n\n• Default thresholds on a Mac with fans: pause at 85 °C, resume at 76 °C, gentle closing of processes at 90 °C - and only after 4 critical readings in a row, which is about 45 seconds at the default 15-second interval and shorter if you speed the interval up. A fanless Mac (an Air, or Neo) gets 78/70/88 instead. The thresholds are always picked for YOUR machine: see menu > \"About my Mac\".\n\n• Termination is the last resort, for when the chip stays critical despite the pauses: something we could not pause is heating, or pausing was not enough. The process is woken up first and gets SIGTERM, a polite \"shut down\" - a chance to save its state, close its files, clean up. That is why we call it gentle. Twenty seconds later, anything still alive gets SIGKILL. A job left frozen for more than 45 minutes is closed the same gentle way; a pause caused only by a low battery gets 4 hours, because waiting for a charger is not a failure.\n\n• A pause is not the only remedy. The process that caused it comes back on efficiency cores instead of at full speed, and stays there until the Mac has been quiet for five minutes. A job you started with `safe-run --normal` keeps all its cores.\n\n• Notifications: on. Sounds: off (enable them in Settings). At the critical level a system banner breaks through everything - Focus and full-screen included.\n• The system, Finder, your terminal and your AI agent are never frozen. An app with a window that the guard does not know by name, a browser or a video app, is pushed to efficiency cores and named in the menu instead of being frozen - unless there is a real emergency: a cooling failure, the battery at its kill threshold, or macOS itself reporting critical. A heavy job it does know by name (python, ffmpeg, a compiler) is paused whether or not it sits inside an app bundle. The guard will not freeze the session working next to it.": "CO SIĘ BĘDZIE DZIAŁO\n• Twój wybór z okna powitalnego decyduje o starcie.\n\nTryb „Tylko obserwuj”: paladyn mierzy, loguje i alarmuje, ale NICZEGO NIE WSTRZYMUJE.\n\nTryb „Włącz ochronę”: pauzuje na zdefiniowanych progach.\n\nTryby przełączysz łatwo - to jeden switch na górze menu.\n\n• Domyślne progi na Macu z wentylatorami: pauza przy 85 °C, wznowienie przy 76 °C, łagodne zamknięcie procesów przy 90 °C - i to dopiero po 4 krytycznych odczytach z rzędu, czyli po jakichś 45 sekundach przy domyślnym interwale 15 s, a krócej, jeśli przyspieszysz pomiar. Mac bez wentylatora (Air albo Neo) dostaje 78/70/88. Progi zawsze są dobrane dla TWOJEJ maszyny: zobacz w menu > „O moim Macu”.\n\n• Zamknięcie procesu to ostateczność, na wypadek gdy mimo pauz chip dalej trzyma poziom krytyczny: grzeje coś, czego nie dało się zapauzować, albo pauza nie wystarczyła. Proces jest najpierw budzony i dostaje SIGTERM, grzeczne „zamknij się”, czyli szansę na zapisanie stanu, domknięcie plików, posprzątanie. Dlatego mówimy o łagodnym zamknięciu. Dwadzieścia sekund później to, co nadal żyje, dostaje SIGKILL. Zadanie zostawione w zamrożeniu dłużej niż 45 minut zamykamy tak samo łagodnie; pauza wywołana samą baterią dostaje 4 godziny, bo czekanie na ładowarkę to nie awaria.\n\n• Pauza to nie jedyny środek. Proces, który ją wywołał, wraca na rdzenie energooszczędne, a nie na pełną moc, i zostaje tam, dopóki nie zrobi się spokojnie przez pięć minut. Zadanie odpalone przez `safe-run --normal` zachowuje wszystkie rdzenie.\n\n• Powiadomienia: włączone. Dźwięki: wyłączone (włączysz w Ustawieniach). Przy poziomie krytycznym baner systemowy przebija się zawsze, nawet przez Skupienie i pełny ekran.\n• System, Finder, terminal i Twój agent AI nigdy nie są zamrażane. Aplikacja z oknem, której strażnik nie zna z nazwy, przeglądarka albo program do wideo, trafia na rdzenie energooszczędne i pokazuje się w menu, zamiast zostać zamrożona - chyba że mamy realną awarię: chłodzenie nie działa, bateria przy progu ubicia albo sam macOS zgłasza stan krytyczny. Ciężkie zadanie, które strażnik zna z nazwy (python, ffmpeg, kompilator), pauzuje niezależnie od tego, czy siedzi w pakiecie aplikacji. Strażnik nie zamrozi sesji, która przy nim pracuje.",
    "WHAT YOU CAN SET\n• Chip pause threshold - a slider; resume follows 9 °C lower, gentle closing 5 °C higher (never above 100).\n• Measurement interval 5-30 s: more often = faster reaction, but costlier in CPU use.\n• Heavy jobs (safe-run): all cores (fast) or efficiency cores only (cool and quiet), plus a CPU limit of 50-100%.\n• Battery gate, signals, keep-awake, this Mac's name in the fleet.": "CO MOŻESZ USTAWIĆ\n• Próg pauzy chipa - suwak; wznowienie idzie 9 °C niżej, łagodne zamknięcie 5 °C wyżej (nigdy powyżej 100).\n• Interwał pomiaru 5-30 s: częściej = szybsza reakcja, ale drożej w użyciu CPU.\n• Ciężkie zadania (safe-run): wszystkie rdzenie (szybko) albo tylko E-cores (chłodno i cicho), do tego limit CPU 50-100%.\n• Bramka baterii, sygnały, „Nie usypiaj”, nazwa tego Maca we flocie.",
    "Enjoy your work!\nPaweł": "Przyjemnej pracy!\nPaweł",
    "Is your Mac heating up with AI and renders? coffee-paladin watches battery, chip and GPU temperatures. It pauses heavy jobs and resumes them by itself once the temperature drops.\n\nOpen source, free, for you:\n%@\n\n#panbookovsky #macbook #protect #temperature #guard":
        "Twój Mac grzeje się przy AI i renderach? coffee-paladin pilnuje temperatur baterii, chipa i GPU. Pauzuje ciężkie zadania i sam je wznawia, gdy temperatura spadnie.\n\nOpen source, za darmo, dla Ciebie:\n%@\n\n#panbookovsky #macbook #protect #temperature #guard",
    "you have to see this: coffee-paladin": "musisz to zobaczyć: coffee-paladin",
    "Hey,\n\nI found something you need on your Mac: coffee-paladin. It watches the chip, GPU and battery temperatures, and when things get hot it pauses heavy jobs and resumes them by itself once the machine cools down.\n\nIt is damn good, because the pause is lossless (the process freezes and continues from the same spot), it sends nothing anywhere, and it is free, open source:\n%@\n\nThe knight with the coffee in the attachment is its mascot.\n\nCheers!":
        "Hej,\n\nznalazłem coś, co musisz mieć na Macu: coffee-paladin. Pilnuje temperatur chipa, GPU i baterii, a jak robi się gorąco, pauzuje ciężkie zadania i sam je wznawia, gdy maszyna ostygnie.\n\nJest zajebiste, bo pauza jest bezstratna (proces zamiera i rusza z tego samego miejsca), nic nigdzie nie wysyła i jest za darmo, open source:\n%@\n\nRycerz z kawą w załączniku to jego maskotka.\n\nPozdro!",
    "chip": "chip", "fans": "wentylatory", "draw": "pobór", "state": "stan", "snapshot": "migawka",
    "To:": "Do:",
    "Everything on record": "Całość, wszystkie zapisy",
    "max capacity: %d%%": "maks. pojemność: %d%%",
    "set up: %@": "skonfigurowany: %@",
    "Turns off banners, their sounds and phone push - one gate for all.":
        "Wyłącza dymki, dźwięki przy nich i push na telefon — jedna bramka dla wszystkich.",
    "Exception: the critical banner shouts regardless.":
        "Wyjątek: baner krytyczny krzyczy niezależnie.",
    "It is the ‹Thermal protection› switch: OFF = watch-only.":
        "To stan przełącznika ‹Ochrona termiczna›: wyłączony = tylko obserwacja.",
    "fastest reaction - the guard itself burns ~3.5% of one core all the time":
        "najszybsza reakcja, ale strażnik sam pali ~3,5% jednego rdzenia bez przerwy",
    "reacts up to 5 s sooner than default, costs ~1.8% of one core":
        "reaguje do 5 s szybciej niż domyślnie, kosztuje ~1,8% jednego rdzenia",
    "default: good reaction at ~1.2% of one core":
        "domyślnie: dobra reakcja przy ~1,2% jednego rdzenia",
    "frugal - an automatic pause may come tens of seconds after the threshold":
        "oszczędnie, ale automatyczna pauza może przyjść kilkadziesiąt sekund po progu",
    "Heavy jobs (safe-run)": "Ciężkie zadania (safe-run)",
    "Efficiency cores only (cool and quiet)": "Tylko rdzenie energooszczędne (chłodno i cicho)",
    "All cores (fast - the paladin still watches the temperature)":
        "Wszystkie rdzenie (szybko — temperatury i tak pilnuje paladyn)",
    "CPU limit for heavy jobs": "Limit CPU dla ciężkich zadań",
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
    "macOS:  %@": "macOS:  %@",
    "Cores:  %d performance + %d efficiency  ·  %d GB RAM": "Rdzenie:  %d wydajnych + %d oszczędnych  ·  %d GB RAM",
    "Cooling:  %d fans": "Chłodzenie:  wentylatory: %d",
    "Cooling:  passive, no fans": "Chłodzenie:  pasywne, bez wentylatorów",
    "Chip reading:  the higher of the CPU and GPU average (macmon)": "Odczyt chipa:  wyższa ze średnich CPU i GPU (macmon)",
    "macmon averages every SMC key it can read: Tp/Te/Ts on the CPU side, Tg on the GPU side. The guard shows whichever average is higher, so during LLM or video work this is the GPU cluster. It is a relative index, not the hottest transistor, and the two averages saturate at different values on the same machine.": "macmon uśrednia wszystkie klucze SMC, jakie potrafi odczytać: Tp/Te/Ts po stronie CPU, Tg po stronie GPU. Strażnik pokazuje wyższą ze średnich, więc przy pracy LLM albo wideo jest to układ GPU. To wskaźnik względny, nie najgorętszy tranzystor, a obie średnie nasycają się przy różnych wartościach na tej samej maszynie.",
    "The chip reading is missing - is macmon installed?": "Brak odczytu chipa - czy macmon jest zainstalowany?",
    "Serial:  %@": "Nr seryjny:  %@",
    "Battery cycles:  %@": "Cykle baterii:  %@",
    "Chip sensor (macmon):  %@": "Czujnik chipa (macmon):  %@",
    "yes": "tak",
    "no": "nie",
    "Keep the Mac awake while heavy jobs run": "Trzymaj caffeinate na ciężkie zadania",
    "Right now: keeping the Mac awake": "Teraz: czuwanie trzymane",
    "Keep the screen on too (uses more power)": "Nie gaś też ekranu (więcej prądu i ciepła)",
    "Keep-awake time left": "Ile zostało czuwania",
    "What the guard did here (total)": "Co bezpiecznik zrobił na tej maszynie (od zawsze)",
    "Nothing here - and that is good news: your Mac has not been overheating.": "Nic tu nie ma - to dobrze, znaczy, że twoja maszyna się nie przegrzewała.",
    "Pause ended another way (manual resume, job exited, daemon restart): %d": "Pauza zakończona inaczej (ręczne wznowienie, proces sam się skończył, restart demona): %d",
    "Process tree details": "Szczegóły drzew procesów",
    "Guard statistics": "Statystyki strażnika",
    "Since the guard started (%@)": "Od startu strażnika (%@)",
    "Since the guard started (%@): no interventions yet.": "Od startu strażnika (%@): jeszcze bez interwencji.",
    "All time on this Mac, counting since %@": "Cały czas na tym Macu, liczone od %@",
    "Other Macs": "Inne Maki",
    "no interventions there yet": "tam jeszcze bez interwencji",
    "%@:  %@  (last report %@ ago)": "%@:  %@  (ostatni raport %@ temu)",
    "paused / resumed / terminated / sleep-lock released": "wstrzymane / wznowione / ubite / zwolnione blokady snu",
    "Heavy jobs paused": "Wstrzymane ciężkie zadania",
    "Jobs resumed after cooling": "Wznowione po ostygnięciu",
    "Jobs terminated at the kill threshold": "Zakończone awaryjnie przy progu krytycznym",
    "Sleep-lock releases due to heat": "Zwolnienia blokady snu z powodu ciepła",
    "counting since %@": "liczone od %@",
    "Nothing yet - the machine has not been hot enough.": "Jeszcze nic - maszyna nie była dość gorąca.",
    "Until a set hour": "Do konkretnej godziny",
    "Extend": "Przedłuż",
    "until %@": "do %@",
    "Extend by %d min": "Przedłuż o %d min",
    "Right now: NOT keeping the Mac awake": "Teraz: czuwanie nietrzymane",
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
    "Uninstall coffee-paladin…":
        "Odinstaluj coffee-paladin…",
    "Uninstall coffee-paladin?":
        "Odinstalować coffee-paladin?",
    "Goes away: the daemon and the menu bar (they stop starting at login), the app, the heat, safe-run, thermal-report and fleet commands, and the skill for AI agents.\n\nStays: the measurement history and the black box in ~/.coffee-paladin. That is what a service centre asks for when a Mac dies under load.":
        "Zniknie: demon i pasek menu (przestaną startować przy logowaniu), aplikacja oraz polecenia heat, safe-run, thermal-report i fleet, a także wtyczka dla agentów AI.\n\nZostanie: historia pomiarów i czarna skrzynka w ~/.coffee-paladin. To jest dokładnie to, o co pyta serwis, kiedy Mac gaśnie pod obciążeniem.",
    "Delete the history and the black box too":
        "Usuń też historię i czarną skrzynkę",
    "Uninstall":
        "Odinstaluj",
    "Delete the black box as well?":
        "Usunąć także czarną skrzynkę?",
    "Every measurement, every pause and every hard shutdown this Mac recorded goes with it. This cannot be undone, and it is the record a service centre or a warranty claim asks for. Uninstalling without this leaves the files untouched and costs nothing.":
        "Przepadnie każdy pomiar, każda pauza i każde twarde zgaśnięcie, jakie ten Mac zapisał. Tego nie da się cofnąć, a to właśnie ten zapis bierze serwis albo reklamacja gwarancyjna. Deinstalacja bez tego zostawia pliki nietknięte i nic nie kosztuje.",
    "Delete everything":
        "Usuń wszystko",
    "Icon only, no numbers":
        "Sama ikona (zmieści się w każdym pasku)",
    "Icon and chip temperature":
        "Ikona i temperatura chipa",
]

let RU: [String: String] = [
    "Keep the Mac awake while heavy jobs run": "Не давать Mac засыпать, пока идут тяжёлые задачи",
    "Right now: keeping the Mac awake": "Сейчас: бодрствование удерживается",
    "Keep the screen on too (uses more power)": "Не гасить и экран (больше энергии и тепла)",
    "Keep-awake time left": "Сколько осталось бодрствования",
    "What the guard did here (total)": "Что защита сделала на этой машине (за всё время)",
    "Nothing here - and that is good news: your Mac has not been overheating.": "Здесь пусто - и это хорошо: ваш Mac не перегревался.",
    "Pause ended another way (manual resume, job exited, daemon restart): %d": "Пауза завершилась иначе (ручное возобновление, процесс сам завершился, перезапуск демона): %d",
    "Process tree details": "Деревья процессов подробно",
    "Guard statistics": "Статистика стража",
    "Since the guard started (%@)": "С запуска стража (%@)",
    "Since the guard started (%@): no interventions yet.": "С запуска стража (%@): вмешательств пока не было.",
    "All time on this Mac, counting since %@": "За всё время на этом Mac, отсчёт с %@",
    "Other Macs": "Другие Mac",
    "no interventions there yet": "там вмешательств пока не было",
    "%@:  %@  (last report %@ ago)": "%@:  %@  (последний отчёт %@ назад)",
    "paused / resumed / terminated / sleep-lock released": "остановлено / возобновлено / завершено / снято блокировок сна",
    "Heavy jobs paused": "Приостановлено тяжёлых задач",
    "Jobs resumed after cooling": "Возобновлено после остывания",
    "Jobs terminated at the kill threshold": "Завершено на критическом пороге",
    "Sleep-lock releases due to heat": "Снятия блокировки сна из-за нагрева",
    "counting since %@": "считаем с %@",
    "Nothing yet - the machine has not been hot enough.": "Пока ничего - машина не была достаточно горячей.",
    "Until a set hour": "До определённого часа",
    "Extend": "Продлить",
    "until %@": "до %@",
    "Extend by %d min": "Продлить на %d мин",
    "Right now: NOT keeping the Mac awake": "Сейчас: бодрствование не удерживается",
    "no data - is coffee-paladin running?": "нет данных - работает ли coffee-paladin?",
    "data is stale (%@) - the guard may have died": "данные устарели (%@) - демон мог упасть",
    " (remembered)": " (запомнено)",
    "the Mac shut down without warning: %@": "Mac выключился без предупреждения: %@",
    "Battery:  %@": "Батарея:  %@",
    "stopped": "стоит",
    "Memory used of total, load average over cores, fan speed": "Использовано памяти из общего объёма, средняя нагрузка на ядра, обороты вентиляторов",
    "%d rpm": "%d об/мин", "%@ rpm": "%@ об/мин",
    "n/a": "н/д",
    "Draw:  %.1f W": "Мощность:  %.1f Вт",
    "Disk:  %d / %d GB used (%d%%)": "Диск:  занято %d / %d ГБ (%d%%)",
    "Power:  %@": "Питание:  %@",
    "AC adapter": "адаптер питания",
    "battery %@": "батарея %@",
    "Load:  %.2f / %d cores": "Нагрузка:  %.2f / %d ядер",
    "Throttling: CPU capped at %d%% speed": "Троттлинг: CPU ограничен до %d%% скорости",
    "   readings: %.0f-%.0f C": "   измерения: %.0f-%.0f C",
    "rising %.1f C/min - about %.0f min to pause": "растёт на %.1f C/мин - до паузы около %.0f мин",
    "rising %.1f C/min": "растёт на %.1f C/мин",
    "What is loading the Mac": "Что нагружает Mac",
    "Held: %d": "Остановлено: %d",
    "  (by hand)": "  (вручную)",
    "Calm": "Спокойно",
    "Warming up": "Нагревается",
    "Hot": "Горячо",
    "Critical": "Критично",
    "Under the guard (safe-run):": "Под надзором (safe-run):",
    "Heating the most (CPU stands in for heat):": "Греют больше всего (CPU вместо замера тепла):",
    "cores": "ядер",
    "Chip thresholds:  pause %.0f °C, kill %.0f °C": "Пороги чипа:  пауза %.0f °C, завершение %.0f °C",
    "Eating the most RAM:": "Больше всего памяти занимают:",
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
    "OFF - the Mac is only being watched": "ВЫКЛЮЧЕНО — Mac только под наблюдением",
    "Show in the bar": "Показывать в строке меню",
    "Show all": "Показать всё",
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
    "careful - under ordinary heavy work the chip already sits here, so long jobs will be paused often": "осторожно - при обычной тяжёлой работе чип уже здесь, поэтому длинные задачи будут часто останавливаться",
    "recommended - the pause comes well before the chip's own limiter": "рекомендуется - пауза наступает задолго до собственного ограничителя чипа",
    "late - a job will run hot for a while before anything happens": "поздно - задача какое-то время будет греться, прежде чем что-то произойдёт",
    "almost never - the reading rarely goes higher than this, so the pause may not come at all": "почти никогда - показание редко бывает выше, так что паузы может не быть вовсе",
    "no limit: a job may use the whole machine": "без ограничения: задача может занять всю машину",
    "about %d of %d cores; the job gets tiny micro-pauses (works for any program)": "примерно %d из %d ядер; задача получает крошечные микропаузы (работает с любой программой)",
    "Battery gate": "Пауза при заряде ниже",
    "pause below this charge when unplugged": "без адаптера тяжёлые задачи подождут зарядку",
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
    "Agent activity": "Активность ИИ-агентов",
    "Live (from hooks):": "Вживую (из хуков):",
    "Agents today: %@ (ccusage)": "Агенты сегодня: %@ (ccusage)",
    "Per agent": "По агенту",
    "Per model": "По модели",
    "Active block (counted by ccusage, not your account limit)": "Активный блок (его считает ccusage, это не лимит аккаунта)",
    "%@ tokens · %@/min · %.0f min left": "%@ токенов · %@/мин · осталось %.0f мин",
    "%@ tokens · %.0f min left": "%@ токенов · осталось %.0f мин",
    "at this rate the guard pauses in ~%.0f min, before the block ends": "при таком темпе страж остановит работу через ~%.0f мин, до конца блока",
    "%@ tokens": "%@ токенов",
    "Claude limits: %@": "Лимиты Claude: %@",
    "Thermal protection": "Тепловая защита",
    "%@: %d%%": "%@: %d%%",
    "(resets %@)": "(сброс %@)",
    "5h limit": "лимит 5 ч",
    "7d limit": "лимит 7 дней",
    "context": "контекст",
    "%@  ·  idle": "%@  ·  простаивает",
    "%@  ·  %.1f cores in its tree": "%@  ·  %.1f ядер в дереве",
    "Chip": "Чип",
    "Battery": "Батарея",
    "Fans": "Вентиляторы",
    "State": "Состояние",
    "Snapshot": "Снимок",
    "Export report": "Сохранить отчёт",
    "Start the guard again": "Запустить страж снова",
    "no AI session is running right now": "сейчас не работает ни одна сессия ИИ",
    "… %d more": "… ещё %d",
    "AI session marker": "Маркер сессии ИИ",
    "Battery temperature (from 40 °C)": "Температура батареи (от 40 °C)",
    "Fan rpm (when spinning)": "Обороты вентиляторов (когда крутятся)",
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
    "Keep awake": "Не давать Mac спать",
    "Off": "Выключить",
    "%d min": "%d мин",
    "%d h": "%d ч",
    "Indefinitely": "Бессрочно",
    "While an app is running": "Пока работает приложение",
    "While downloading (network active)": "Пока идёт загрузка (сеть активна)",
    "released automatically when the Mac gets hot": "снимается само, когда Mac нагревается",
    "Keep-awake: %@ left": "Бодрствование: осталось %@",
    "Held right now: %d": "Сейчас остановлено: %d",
    "Turn thermal protection off?": "Отключить тепловую защиту?",
    "The paladin will keep measuring and writing down what it would have paused, and will stop nothing at all, even above %.0f °C.": "Паладин продолжит измерять и записывать, что он остановил бы, но не остановит ничего, даже выше %.0f °C.",
    "Turn protection off": "Отключить защиту",
    "Keep it on": "Оставить включённой",
    "Watch only": "Только наблюдение",
    "The paladin keeps measuring and writes to the log what it would pause, but it stops nothing until you switch this back on.": "Паладин продолжает измерять и записывать в журнал, что он остановил бы, но ничего не останавливает, пока вы не включите защиту снова.",
    "Thermal protection is on": "Тепловая защита включена",
    "Above %.0f °C the paladin pauses heavy jobs and starts them again by itself at %.0f °C.": "Выше %.0f °C паладин ставит тяжёлые задачи на паузу и сам возобновляет их при %.0f °C.",
    "Jobs resumed": "Задачи возобновлены",
    "Held jobs (%d) are running again; if the chip is still hot the paladin pauses them again on its next reading.": "Остановленные задачи (%d) снова работают; если чип всё ещё горячий, паладин остановит их при следующем измерении.",
    "Heavy processes right now: %d": "Тяжёлых процессов сейчас: %d",
    "Measurement interval": "Частота измерений",
    "Pick the report period.": "Выберите период отчёта.",
    "Included: hardware, battery, sudden shutdowns, interventions, measurement timeline.":
        "В отчёте: железо, батарея, внезапные отключения, вмешательства, шкала измерений.",
    "From:": "С:",
    "This topic will not work": "Эта тема не сработает",
    "Use only letters, digits, _ and -, up to 64 characters. A space stops the push silently, and # or ? publish to a shorter topic than the one you typed.": "Используйте только буквы, цифры, _ и -, до 64 символов. Пробел молча блокирует push, а # или ? публикуют в более короткую тему, чем введённая.",
    "First steps with the paladin": "Первые шаги с паладином",
    "Phone notifications…": "Уведомления на телефон…",
    "First steps…": "Первые шаги...",
    "WHAT IT CAN DO\n• The paladin watches the chip, the battery, the fans and the power source - by default a reading every 15 seconds.\n• When things get too hot, it FREEZES heavy processes instead of letting the Mac cook itself. The pause destroys nothing: the process stops mid-instruction and continues once the chip cools. Example? Measured: 89 °C → 60 °C in 19 seconds, no loss.\n• It finds the real culprit: CPU is counted across the whole process tree, so it also sees a script that spawns hundreds of short jobs while using almost nothing itself.\n• On battery at 10% or less it pauses long jobs - they resume when you plug in, or once the charge is back above 25% (both figures are defaults; the Battery gate slider moves them together).\n• It keeps a black box: after a hard failure the last 8 readings survive. One click turns them into a report for a repair shop (should you ever need it).\n• Keep-awake - works like the well-known Caffeine or Amphetamine, but unlike them it comes with a fuse: the sleep lock is released the moment the Mac reaches pause level. Sleep is the fastest cooling there is.": "ЧТО ОН УМЕЕТ\n• Паладин следит за чипом, батареей, вентиляторами и источником питания - по умолчанию замер каждые 15 секунд.\n• Когда становится слишком горячо, он ЗАМОРАЖИВАЕТ тяжёлые процессы, вместо того чтобы дать Mac свариться. Пауза ничего не разрушает: процесс замирает посреди инструкции и продолжает с того же места, как только чип остынет. Пример? Измерено: 89 °C → 60 °C за 19 секунд, без потерь.\n• Он находит настоящего виновника: CPU считается по всему дереву процессов, поэтому виден и скрипт, который порождает сотни коротких задач, а сам почти ничего не потребляет.\n• На батарее при 10% и ниже он ставит длинные задачи на паузу - они возобновятся, когда вы подключите питание, или когда заряд снова поднимется выше 25% (обе цифры это значения по умолчанию, ползунок «Пауза при заряде ниже» двигает их вместе).\n• Он ведёт чёрный ящик: после жёсткого сбоя остаются 8 последних замеров. Один клик превращает их в отчёт для сервиса (если он когда-нибудь понадобится).\n• «Не давать Mac спать» - работает как известные Caffeine или Amphetamine, но, в отличие от них, идёт с предохранителем: блокировка сна снимается в тот момент, когда Mac доходит до уровня паузы. Сон охлаждает быстрее всего.",
    "WHAT WILL HAPPEN\n• Your choice in the welcome window decides how you start.\n\n\"Watch only\" mode: the paladin measures, logs and alerts, but PAUSES NOTHING.\n\n\"Enable protection\" mode: it pauses at the defined thresholds.\n\nSwitching is easy - one switch at the top of the menu.\n\n• Default thresholds on a Mac with fans: pause at 85 °C, resume at 76 °C, gentle closing of processes at 90 °C - and only after 4 critical readings in a row, which is about 45 seconds at the default 15-second interval and shorter if you speed the interval up. A fanless Mac (an Air, or Neo) gets 78/70/88 instead. The thresholds are always picked for YOUR machine: see menu > \"About my Mac\".\n\n• Termination is the last resort, for when the chip stays critical despite the pauses: something we could not pause is heating, or pausing was not enough. The process is woken up first and gets SIGTERM, a polite \"shut down\" - a chance to save its state, close its files, clean up. That is why we call it gentle. Twenty seconds later, anything still alive gets SIGKILL. A job left frozen for more than 45 minutes is closed the same gentle way; a pause caused only by a low battery gets 4 hours, because waiting for a charger is not a failure.\n\n• A pause is not the only remedy. The process that caused it comes back on efficiency cores instead of at full speed, and stays there until the Mac has been quiet for five minutes. A job you started with `safe-run --normal` keeps all its cores.\n\n• Notifications: on. Sounds: off (enable them in Settings). At the critical level a system banner breaks through everything - Focus and full-screen included.\n• The system, Finder, your terminal and your AI agent are never frozen. An app with a window that the guard does not know by name, a browser or a video app, is pushed to efficiency cores and named in the menu instead of being frozen - unless there is a real emergency: a cooling failure, the battery at its kill threshold, or macOS itself reporting critical. A heavy job it does know by name (python, ffmpeg, a compiler) is paused whether or not it sits inside an app bundle. The guard will not freeze the session working next to it.": "ЧТО БУДЕТ ПРОИСХОДИТЬ\n• Ваш выбор в окне приветствия определяет, как вы начнёте.\n\nРежим «Только наблюдение»: паладин измеряет, ведёт журнал и предупреждает, но НИЧЕГО НЕ СТАВИТ НА ПАУЗУ.\n\nРежим «Включить защиту»: он ставит на паузу на заданных порогах.\n\nПереключиться просто, это один переключатель вверху меню.\n\n• Пороги по умолчанию на Mac с вентиляторами: пауза при 85 °C, возобновление при 76 °C, мягкое закрытие процессов при 90 °C, и только после 4 критических замеров подряд, то есть примерно через 45 секунд при интервале по умолчанию 15 с, и быстрее, если вы ускорите интервал. Mac без вентилятора (Air или Neo) получает 78/70/88. Пороги всегда подбираются под ВАШУ машину: смотрите меню > «Об этом Mac».\n\n• Завершение процесса это крайняя мера, на случай, когда чип остаётся в критической зоне несмотря на паузы: греет что-то, что мы не смогли поставить на паузу, или паузы не хватило. Процесс сначала будят, и он получает SIGTERM, вежливое «завершись», то есть шанс сохранить состояние, закрыть файлы, прибрать за собой. Поэтому мы называем это мягким закрытием. Через двадцать секунд всё, что ещё живо, получает SIGKILL. Задачу, оставленную в заморозке дольше 45 минут, закрываем так же мягко; пауза, вызванная только низким зарядом батареи, получает 4 часа, потому что ожидание зарядки это не авария.\n\n• Пауза не единственное средство. Процесс, который её вызвал, возвращается на энергоэффективные ядра, а не на полную мощность, и остаётся там, пока на Mac не будет спокойно пять минут подряд. Задача, запущенная через `safe-run --normal`, сохраняет все свои ядра.\n\n• Уведомления: включены. Звуки: выключены (включите их в Настройках). На критическом уровне системный баннер пробивается через всё, включая Фокусирование и полноэкранный режим.\n• Система, Finder, ваш терминал и ваш ИИ-агент никогда не замораживаются. Приложение с окном, которое страж не знает по имени, браузер или программа для видео, отправляется на энергоэффективные ядра и называется в меню вместо заморозки, если только нет настоящей аварии: отказ охлаждения, батарея на пороге принудительного завершения или сам macOS сообщает о критическом состоянии. Тяжёлую задачу, которую страж знает по имени (python, ffmpeg, компилятор), он ставит на паузу независимо от того, находится она внутри пакета приложения или нет. Страж не заморозит сессию, которая работает рядом с ним.",
    "WHAT YOU CAN SET\n• Chip pause threshold - a slider; resume follows 9 °C lower, gentle closing 5 °C higher (never above 100).\n• Measurement interval 5-30 s: more often = faster reaction, but costlier in CPU use.\n• Heavy jobs (safe-run): all cores (fast) or efficiency cores only (cool and quiet), plus a CPU limit of 50-100%.\n• Battery gate, signals, keep-awake, this Mac's name in the fleet.": "ЧТО МОЖНО НАСТРОИТЬ\n• Порог паузы по чипу - ползунок; возобновление идёт на 9 °C ниже, мягкое закрытие на 5 °C выше (никогда выше 100).\n• Интервал замеров 5-30 с: чаще = быстрее реакция, но дороже по использованию CPU.\n• Тяжёлые задачи (safe-run): все ядра (быстро) или только энергоэффективные ядра (прохладно и тихо), плюс лимит CPU 50-100%.\n• «Пауза при заряде ниже», сигналы, «Не давать Mac спать», имя этого Mac в парке машин.",
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
    "max capacity: %d%%": "макс. ёмкость: %d%%",
    "set up: %@": "настроен: %@",
    "Turns off banners, their sounds and phone push - one gate for all.":
        "Отключает уведомления, их звуки и push — один шлюз для всего.",
    "Exception: the critical banner shouts regardless.":
        "Исключение: критический баннер кричит независимо.",
    "It is the ‹Thermal protection› switch: OFF = watch-only.":
        "Это состояние переключателя ‹Тепловая защита›: выключен = только наблюдение.",
    "fastest reaction - the guard itself burns ~3.5% of one core all the time":
        "самая быстрая реакция, но страж сам жжёт ~3,5% ядра постоянно",
    "reacts up to 5 s sooner than default, costs ~1.8% of one core":
        "реагирует до 5 с быстрее, стоит ~1,8% ядра",
    "default: good reaction at ~1.2% of one core":
        "по умолчанию: хорошая реакция при ~1,2% ядра",
    "frugal - an automatic pause may come tens of seconds after the threshold":
        "экономно, но автопауза может прийти через десятки секунд после порога",
    "Heavy jobs (safe-run)": "Тяжёлые задачи (safe-run)",
    "Efficiency cores only (cool and quiet)": "Только энергоэффективные ядра (холодно и тихо)",
    "All cores (fast - the paladin still watches the temperature)":
        "Все ядра (быстро — за температурой всё равно следит паладин)",
    "CPU limit for heavy jobs": "Лимит CPU для тяжёлых задач",
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
    "macOS:  %@": "macOS:  %@",
    "Cores:  %d performance + %d efficiency  ·  %d GB RAM": "Ядра:  %d производительных + %d энергоэффективных  ·  %d ГБ ОЗУ",
    "Cooling:  %d fans": "Охлаждение:  вентиляторов: %d",
    "Cooling:  passive, no fans": "Охлаждение:  пассивное, без вентиляторов",
    "Chip reading:  the higher of the CPU and GPU average (macmon)": "Показание чипа:  большее из средних CPU и GPU (macmon)",
    "macmon averages every SMC key it can read: Tp/Te/Ts on the CPU side, Tg on the GPU side. The guard shows whichever average is higher, so during LLM or video work this is the GPU cluster. It is a relative index, not the hottest transistor, and the two averages saturate at different values on the same machine.": "macmon усредняет все ключи SMC, которые может прочитать: Tp/Te/Ts со стороны CPU, Tg со стороны GPU. Страж показывает большее из средних, поэтому при работе LLM или видео это кластер GPU. Это относительный показатель, а не самый горячий транзистор, и обе средние насыщаются на разных значениях на одной машине.",
    "The chip reading is missing - is macmon installed?": "Нет показаний чипа - установлен ли macmon?",
    "Serial:  %@": "Серийный номер:  %@",
    "Battery cycles:  %@": "Циклы батареи:  %@",
    "Chip sensor (macmon):  %@": "Датчик чипа (macmon):  %@",
    "yes": "да",
    "no": "нет",
    "Uninstall coffee-paladin…":
        "Удалить coffee-paladin…",
    "Uninstall coffee-paladin?":
        "Удалить coffee-paladin?",
    "Goes away: the daemon and the menu bar (they stop starting at login), the app, the heat, safe-run, thermal-report and fleet commands, and the skill for AI agents.\n\nStays: the measurement history and the black box in ~/.coffee-paladin. That is what a service centre asks for when a Mac dies under load.":
        "Уйдёт: демон и строка меню (перестанут запускаться при входе), приложение и команды heat, safe-run, thermal-report и fleet, а также навык для ИИ-агентов.\n\nОстанется: история замеров и чёрный ящик в ~/.coffee-paladin. Именно это спрашивает сервис, когда Mac гаснет под нагрузкой.",
    "Delete the history and the black box too":
        "Удалить также историю и чёрный ящик",
    "Uninstall":
        "Удалить",
    "Delete the black box as well?":
        "Удалить и чёрный ящик?",
    "Every measurement, every pause and every hard shutdown this Mac recorded goes with it. This cannot be undone, and it is the record a service centre or a warranty claim asks for. Uninstalling without this leaves the files untouched and costs nothing.":
        "Пропадёт каждый замер, каждая пауза и каждое жёсткое выключение, записанные этим Mac. Это необратимо, а именно этот журнал берут сервис или гарантийная претензия. Удаление без этого оставляет файлы нетронутыми и ничего не стоит.",
    "Delete everything":
        "Удалить всё",
    "Icon only, no numbers":
        "Только значок (влезет в любую строку меню)",
    "Icon and chip temperature":
        "Значок и температура чипа",
]

let ZH: [String: String] = [
    "Keep the Mac awake while heavy jobs run": "繁重任务运行时保持 Mac 唤醒",
    "Right now: keeping the Mac awake": "当前：正在保持唤醒",
    "Keep the screen on too (uses more power)": "屏幕也不熄灭（更耗电、更热）",
    "Keep-awake time left": "唤醒剩余时间",
    "What the guard did here (total)": "守护在这台机器上做过什么（累计）",
    "Nothing here - and that is good news: your Mac has not been overheating.": "这里是空的 - 这是好消息：你的 Mac 没有过热。",
    "Pause ended another way (manual resume, job exited, daemon restart): %d": "暂停以其他方式结束(手动恢复、进程自行退出、守护进程重启):%d",
    "Process tree details": "进程树详情",
    "Guard statistics": "守卫统计",
    "Since the guard started (%@)": "自守卫启动(%@)",
    "Since the guard started (%@): no interventions yet.": "自守卫启动(%@):尚无干预。",
    "All time on this Mac, counting since %@": "本机全部时间,自 %@ 起计",
    "Other Macs": "其他 Mac",
    "no interventions there yet": "那边尚无干预",
    "%@:  %@  (last report %@ ago)": "%@:  %@  (上次报告在 %@ 前)",
    "paused / resumed / terminated / sleep-lock released": "已暂停 / 已恢复 / 已终止 / 已释放睡眠锁",
    "Heavy jobs paused": "已暂停的繁重任务",
    "Jobs resumed after cooling": "降温后已恢复",
    "Jobs terminated at the kill threshold": "在临界阈值终止",
    "Sleep-lock releases due to heat": "因过热解除防睡眠锁定的次数",
    "counting since %@": "自 %@ 起统计",
    "Nothing yet - the machine has not been hot enough.": "暂无 - 机器还不够热。",
    "Until a set hour": "到指定时刻",
    "Extend": "延长",
    "until %@": "到 %@",
    "Extend by %d min": "延长 %d 分钟",
    "Right now: NOT keeping the Mac awake": "当前：未保持唤醒",
    "no data - is coffee-paladin running?": "没有数据 - coffee-paladin 在运行吗？",
    "data is stale (%@) - the guard may have died": "数据已过期（%@）- 守护进程可能已停止",
    " (remembered)": "（记忆值）",
    "the Mac shut down without warning: %@": "Mac 毫无预警地关机了：%@",
    "Battery:  %@": "电池：  %@",
    "stopped": "停转",
    "Memory used of total, load average over cores, fan speed": "已用内存/总内存,核心平均负载,风扇转速",
    "%d rpm": "%d 转/分", "%@ rpm": "%@ 转/分",
    "n/a": "无",
    "Draw:  %.1f W": "功耗：  %.1f W",
    "Disk:  %d / %d GB used (%d%%)": "磁盘：  已用 %d / %d GB（%d%%）",
    "Power:  %@": "电源：  %@",
    "AC adapter": "电源适配器",
    "battery %@": "电池 %@",
    "Load:  %.2f / %d cores": "负载：  %.2f / %d 核",
    "Throttling: CPU capped at %d%% speed": "降频：CPU 被限制到 %d%% 速度",
    "   readings: %.0f-%.0f C": "   测量值：%.0f-%.0f C",
    "rising %.1f C/min - about %.0f min to pause": "每分钟上升 %.1f C - 约 %.0f 分钟后暂停",
    "rising %.1f C/min": "每分钟上升 %.1f C",
    "What is loading the Mac": "什么在给 Mac 加负载",
    "Held: %d": "已暂停:%d",
    "  (by hand)": "  (手动)",
    "Calm": "平静",
    "Warming up": "正在升温",
    "Hot": "很热",
    "Critical": "危急",
    "Under the guard (safe-run):": "在守卫之下(safe-run):",
    "Heating the most (CPU stands in for heat):": "最发热的进程(以 CPU 代表发热):",
    "cores": "核",
    "Chip thresholds:  pause %.0f °C, kill %.0f °C": "芯片阈值:暂停 %.0f °C,终止 %.0f °C",
    "Eating the most RAM:": "内存占用最多：",
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
    "OFF - the Mac is only being watched": "已关闭 —— 仅在观察这台 Mac",
    "Show in the bar": "菜单栏显示内容",
    "Show all": "全部显示",
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
    "careful - under ordinary heavy work the chip already sits here, so long jobs will be paused often": "谨慎 - 普通重负载时芯片就在这个温度,长任务会被频繁暂停",
    "recommended - the pause comes well before the chip's own limiter": "推荐 - 暂停远早于芯片自身的限频",
    "late - a job will run hot for a while before anything happens": "偏晚 - 任务会先热上一阵子才有动作",
    "almost never - the reading rarely goes higher than this, so the pause may not come at all": "几乎不会触发 - 读数很少更高,暂停可能根本不来",
    "no limit: a job may use the whole machine": "不限制:任务可以占用整台机器",
    "about %d of %d cores; the job gets tiny micro-pauses (works for any program)": "约 %d 个核心(共 %d 个);任务会得到极短的微暂停(适用于任何程序)",
    "Battery gate": "电量低于此值时暂停",
    "pause below this charge when unplugged": "未接电源时，繁重任务将等待充电",
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
    "Agent activity": "AI 代理活动",
    "Live (from hooks):": "实时（来自 hooks）：",
    "Agents today: %@ (ccusage)": "今日代理消耗：%@（ccusage）",
    "Per agent": "按代理",
    "Per model": "按模型",
    "Active block (counted by ccusage, not your account limit)": "当前区块（由 ccusage 统计，不是你的账号额度）",
    "%@ tokens · %@/min · %.0f min left": "%@ 个 token · %@/分钟 · 还剩 %.0f 分钟",
    "%@ tokens · %.0f min left": "%@ 个 token · 还剩 %.0f 分钟",
    "at this rate the guard pauses in ~%.0f min, before the block ends": "按此速度守卫将在约 %.0f 分钟后暂停工作，早于区块结束",
    "%@ tokens": "%@ 个 token",
    "Claude limits: %@": "Claude 限额：%@",
    "Thermal protection": "过热保护",
    "%@: %d%%": "%@：%d%%",
    "(resets %@)": "（%@ 重置）",
    "5h limit": "5 小时额度",
    "7d limit": "7 天额度",
    "context": "上下文",
    "%@  ·  idle": "%@  ·  空闲",
    "%@  ·  %.1f cores in its tree": "%@  ·  在其进程树中 %.1f 核",
    "Chip": "芯片",
    "Battery": "电池",
    "Fans": "风扇",
    "State": "状态",
    "Snapshot": "快照",
    "Export report": "导出报告",
    "Start the guard again": "重新启动守卫",
    "no AI session is running right now": "当前没有运行中的 AI 会话",
    "… %d more": "… 还有 %d 个",
    "AI session marker": "AI 会话标记",
    "Battery temperature (from 40 °C)": "电池温度（40 °C 起）",
    "Fan rpm (when spinning)": "风扇转速（旋转时）",
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
    "Keep awake": "保持 Mac 唤醒",
    "Off": "关闭",
    "%d min": "%d 分钟",
    "%d h": "%d 小时",
    "Indefinitely": "无限期",
    "While an app is running": "当某个应用运行时",
    "While downloading (network active)": "下载期间(网络活跃)",
    "released automatically when the Mac gets hot": "Mac 变热时自动解除",
    "Keep-awake: %@ left": "保持唤醒:剩余 %@",
    "Held right now: %d": "当前已暂停:%d",
    "Turn thermal protection off?": "关闭热保护?",
    "The paladin will keep measuring and writing down what it would have paused, and will stop nothing at all, even above %.0f °C.": "帕拉丁会继续测量并记录它本会暂停的内容,但不会停止任何进程,即使超过 %.0f °C。",
    "Turn protection off": "关闭保护",
    "Keep it on": "保持开启",
    "Watch only": "仅观察",
    "The paladin keeps measuring and writes to the log what it would pause, but it stops nothing until you switch this back on.": "帕拉丁继续测量并把它本会暂停的内容写入日志,但在你重新打开保护之前不会停止任何进程。",
    "Thermal protection is on": "热保护已开启",
    "Above %.0f °C the paladin pauses heavy jobs and starts them again by itself at %.0f °C.": "超过 %.0f °C 时帕拉丁会暂停重任务,并在 %.0f °C 时自动恢复。",
    "Jobs resumed": "任务已恢复",
    "Held jobs (%d) are running again; if the chip is still hot the paladin pauses them again on its next reading.": "已暂停的任务(%d 个)又在运行;如果芯片仍然很热,帕拉丁会在下一次读数时再次暂停它们。",
    "Heavy processes right now: %d": "当前繁重进程数:%d",
    "Measurement interval": "测量频率",
    "Pick the report period.": "选择报告时间段。",
    "Included: hardware, battery, sudden shutdowns, interventions, measurement timeline.":
        "报告含:硬件、电池、突然关机、干预、测量时间线。",
    "From:": "从:",
    "This topic will not work": "这个主题无法使用",
    "Use only letters, digits, _ and -, up to 64 characters. A space stops the push silently, and # or ? publish to a shorter topic than the one you typed.": "只能使用字母、数字、_ 和 -,最多 64 个字符。空格会让推送静默失败,而 # 或 ? 会发布到比你输入的更短的主题。",
    "First steps with the paladin": "圣骑士入门指南",
    "Phone notifications…": "手机通知…",
    "First steps…": "入门指南...",
    "WHAT IT CAN DO\n• The paladin watches the chip, the battery, the fans and the power source - by default a reading every 15 seconds.\n• When things get too hot, it FREEZES heavy processes instead of letting the Mac cook itself. The pause destroys nothing: the process stops mid-instruction and continues once the chip cools. Example? Measured: 89 °C → 60 °C in 19 seconds, no loss.\n• It finds the real culprit: CPU is counted across the whole process tree, so it also sees a script that spawns hundreds of short jobs while using almost nothing itself.\n• On battery at 10% or less it pauses long jobs - they resume when you plug in, or once the charge is back above 25% (both figures are defaults; the Battery gate slider moves them together).\n• It keeps a black box: after a hard failure the last 8 readings survive. One click turns them into a report for a repair shop (should you ever need it).\n• Keep-awake - works like the well-known Caffeine or Amphetamine, but unlike them it comes with a fuse: the sleep lock is released the moment the Mac reaches pause level. Sleep is the fastest cooling there is.": "它能做什么\n• 圣骑士监控芯片、电池、风扇和电源 - 默认每 15 秒测量一次。\n• 一旦过热,它会冻结繁重进程,而不是让 Mac 把自己煮熟。暂停不会破坏任何东西:进程在指令中途停住,芯片冷却后从原处继续。例子?实测:89 °C → 60 °C 只用 19 秒,零损失。\n• 它能找出真正的元凶:CPU 按整个进程树统计,所以连自己几乎不占资源、却派生出数百个短任务的脚本也看得见。\n• 使用电池且电量在 10% 或以下时,它会暂停长任务 - 接上电源后恢复,或者电量回到 25% 以上时恢复(这两个数字都是默认值,「电量低于此值时暂停」滑块会同时移动它们)。\n• 它保留一个黑匣子:硬故障之后,最后 8 次读数仍然保存下来。一键即可把它们变成给维修店的报告(万一你需要的话)。\n• 保持唤醒 - 和常见的 Caffeine 或 Amphetamine 一样,但不同之处在于它带保险丝:Mac 一到暂停阈值,睡眠锁立刻释放。睡眠是最快的降温方式。",
    "WHAT WILL HAPPEN\n• Your choice in the welcome window decides how you start.\n\n\"Watch only\" mode: the paladin measures, logs and alerts, but PAUSES NOTHING.\n\n\"Enable protection\" mode: it pauses at the defined thresholds.\n\nSwitching is easy - one switch at the top of the menu.\n\n• Default thresholds on a Mac with fans: pause at 85 °C, resume at 76 °C, gentle closing of processes at 90 °C - and only after 4 critical readings in a row, which is about 45 seconds at the default 15-second interval and shorter if you speed the interval up. A fanless Mac (an Air, or Neo) gets 78/70/88 instead. The thresholds are always picked for YOUR machine: see menu > \"About my Mac\".\n\n• Termination is the last resort, for when the chip stays critical despite the pauses: something we could not pause is heating, or pausing was not enough. The process is woken up first and gets SIGTERM, a polite \"shut down\" - a chance to save its state, close its files, clean up. That is why we call it gentle. Twenty seconds later, anything still alive gets SIGKILL. A job left frozen for more than 45 minutes is closed the same gentle way; a pause caused only by a low battery gets 4 hours, because waiting for a charger is not a failure.\n\n• A pause is not the only remedy. The process that caused it comes back on efficiency cores instead of at full speed, and stays there until the Mac has been quiet for five minutes. A job you started with `safe-run --normal` keeps all its cores.\n\n• Notifications: on. Sounds: off (enable them in Settings). At the critical level a system banner breaks through everything - Focus and full-screen included.\n• The system, Finder, your terminal and your AI agent are never frozen. An app with a window that the guard does not know by name, a browser or a video app, is pushed to efficiency cores and named in the menu instead of being frozen - unless there is a real emergency: a cooling failure, the battery at its kill threshold, or macOS itself reporting critical. A heavy job it does know by name (python, ffmpeg, a compiler) is paused whether or not it sits inside an app bundle. The guard will not freeze the session working next to it.": "将会发生什么\n• 欢迎窗口里的选择决定你从哪里开始。\n\n「仅观察」模式:圣骑士只测量、记录和提醒,不暂停任何东西。\n\n「启用保护」模式:达到设定的阈值时它会暂停。\n\n切换很简单 - 菜单顶部有一个开关。\n\n• 有风扇的 Mac 的默认阈值:85 °C 暂停,76 °C 恢复,90 °C 温和关闭进程 - 而且只有在连续 4 次临界读数之后才会执行,按默认 15 秒的间隔算大约是 45 秒,如果你把间隔调快就更短。无风扇的 Mac(Air 或 Neo)使用 78/70/88。阈值始终按你的机器挑选:见菜单 > 「关于我的 Mac」。\n\n• 终止进程是最后手段,用于暂停之后芯片仍然停在临界状态的情况:有我们无法暂停的东西在发热,或者暂停不够。进程会先被唤醒,然后收到 SIGTERM,一个客气的「请关闭」,也就是保存状态、关闭文件、清理现场的机会。所以我们称之为温和关闭。二十秒后,仍然活着的进程会收到 SIGKILL。被冻结超过 45 分钟的任务,会以同样温和的方式关闭;仅因电量低而产生的暂停可以有 4 小时,因为等充电器不算故障。\n\n• 暂停不是唯一的处理方式。引发暂停的进程恢复时跑在能效核心上,而不是满速,并且一直留在那里,直到 Mac 安静五分钟为止。用 `safe-run --normal` 启动的任务保留全部核心。\n\n• 通知:开启。声音:关闭(在设置里开启)。到了临界级别,系统横幅会穿透一切,包括专注模式和全屏。\n• 系统、Finder、你的终端和你的 AI 代理永远不会被冻结。守卫不认识名字的带窗口应用、浏览器或视频程序,会被推到能效核心并在菜单里点名,而不是被冻结,除非出现真正的紧急情况:散热失效、电池到达强制终止阈值,或者 macOS 自己报告临界状态。它按名字认识的繁重任务(python、ffmpeg、编译器),无论是否位于应用包内都会被暂停。守卫不会冻结在它旁边工作的会话。",
    "WHAT YOU CAN SET\n• Chip pause threshold - a slider; resume follows 9 °C lower, gentle closing 5 °C higher (never above 100).\n• Measurement interval 5-30 s: more often = faster reaction, but costlier in CPU use.\n• Heavy jobs (safe-run): all cores (fast) or efficiency cores only (cool and quiet), plus a CPU limit of 50-100%.\n• Battery gate, signals, keep-awake, this Mac's name in the fleet.": "你可以设置\n• 芯片暂停阈值 - 滑块;恢复自动低 9 °C,温和关闭自动高 5 °C(绝不超过 100)。\n• 测量间隔 5-30 秒:更频繁 = 反应更快,但 CPU 开销更大。\n• 繁重任务(safe-run):全部核心(快)或仅能效核心(凉爽安静),外加 50-100% 的 CPU 限制。\n• 「电量低于此值时暂停」、信号、保持唤醒、这台 Mac 在机群中的名字。",
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
    "max capacity: %d%%": "最大容量: %d%%",
    "set up: %@": "配置于: %@",
    "Turns off banners, their sounds and phone push - one gate for all.":
        "关闭通知、其声音和手机推送——同一道闸门。",
    "Exception: the critical banner shouts regardless.":
        "例外:危险横幅无论如何都会警报。",
    "It is the ‹Thermal protection› switch: OFF = watch-only.":
        "即主开关‹过热保护›:关闭 = 仅观察。",
    "fastest reaction - the guard itself burns ~3.5% of one core all the time":
        "反应最快,但守卫自身持续占用约3.5%单核",
    "reacts up to 5 s sooner than default, costs ~1.8% of one core":
        "比默认快最多5秒,占用约1.8%单核",
    "default: good reaction at ~1.2% of one core":
        "默认:约1.2%单核,反应良好",
    "frugal - an automatic pause may come tens of seconds after the threshold":
        "省电,但自动暂停可能在超过阈值后数十秒才触发",
    "Heavy jobs (safe-run)": "繁重任务(safe-run)",
    "Efficiency cores only (cool and quiet)": "仅能效核心(凉爽安静)",
    "All cores (fast - the paladin still watches the temperature)":
        "全部核心(快 - 温度仍由圣骑士监控)",
    "CPU limit for heavy jobs": "繁重任务的 CPU 限制",
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
    "macOS:  %@": "macOS:  %@",
    "Cores:  %d performance + %d efficiency  ·  %d GB RAM": "核心:%d 性能核 + %d 能效核  ·  %d GB 内存",
    "Cooling:  %d fans": "散热:%d 个风扇",
    "Cooling:  passive, no fans": "散热:被动式,无风扇",
    "Chip reading:  the higher of the CPU and GPU average (macmon)": "芯片读数:CPU 与 GPU 平均值中较高者(macmon)",
    "macmon averages every SMC key it can read: Tp/Te/Ts on the CPU side, Tg on the GPU side. The guard shows whichever average is higher, so during LLM or video work this is the GPU cluster. It is a relative index, not the hottest transistor, and the two averages saturate at different values on the same machine.": "macmon 会对它能读取的所有 SMC 键取平均:CPU 侧的 Tp/Te/Ts,GPU 侧的 Tg。守卫显示两者中较高的平均值,因此在运行 LLM 或视频任务时显示的是 GPU 集群。这是一个相对指标,不是最热的晶体管,而且同一台机器上两个平均值的饱和点并不相同。",
    "The chip reading is missing - is macmon installed?": "缺少芯片读数 - 是否已安装 macmon?",
    "Serial:  %@": "序列号:  %@",
    "Battery cycles:  %@": "电池循环:  %@",
    "Chip sensor (macmon):  %@": "芯片传感器(macmon):  %@",
    "yes": "是",
    "no": "否",
    "Uninstall coffee-paladin…":
        "卸载 coffee-paladin…",
    "Uninstall coffee-paladin?":
        "要卸载 coffee-paladin 吗？",
    "Goes away: the daemon and the menu bar (they stop starting at login), the app, the heat, safe-run, thermal-report and fleet commands, and the skill for AI agents.\n\nStays: the measurement history and the black box in ~/.coffee-paladin. That is what a service centre asks for when a Mac dies under load.":
        "将被移除：守护进程与菜单栏（不再随登录启动）、应用本体，以及 heat、safe-run、thermal-report 和 fleet 命令，还有给 AI 代理的技能包。\n\n将会保留：~/.coffee-paladin 里的测量历史与黑匣子。当 Mac 在负载下熄灭时，维修中心要的正是这些。",
    "Delete the history and the black box too":
        "同时删除历史记录与黑匣子",
    "Uninstall":
        "卸载",
    "Delete the black box as well?":
        "连黑匣子也一起删除吗？",
    "Every measurement, every pause and every hard shutdown this Mac recorded goes with it. This cannot be undone, and it is the record a service centre or a warranty claim asks for. Uninstalling without this leaves the files untouched and costs nothing.":
        "这台 Mac 记录的每一次测量、每一次暂停、每一次硬关机都会随之消失。此操作无法撤销，而维修中心或保修索赔要的正是这份记录。不勾选这一项的卸载会完整保留文件，且没有任何代价。",
    "Delete everything":
        "全部删除",
    "Icon only, no numbers":
        "仅图标（任何菜单栏都放得下）",
    "Icon and chip temperature":
        "图标与芯片温度",
]

let ES: [String: String] = [
    "Keep the Mac awake while heavy jobs run": "Mantener el Mac despierto mientras corren tareas pesadas",
    "Right now: keeping the Mac awake": "Ahora: manteniendo el Mac despierto",
    "Keep the screen on too (uses more power)": "Mantener también la pantalla encendida (más consumo y calor)",
    "Keep-awake time left": "Tiempo restante de vigilia",
    "What the guard did here (total)": "Lo que hizo el guardián en esta máquina (histórico)",
    "Nothing here - and that is good news: your Mac has not been overheating.": "Aquí no hay nada, y es buena noticia: tu Mac no se ha sobrecalentado.",
    "Pause ended another way (manual resume, job exited, daemon restart): %d": "La pausa terminó de otra forma (reanudación manual, el proceso terminó solo, reinicio del demonio): %d",
    "Process tree details": "Detalles de árboles de procesos",
    "Guard statistics": "Estadísticas del paladín",
    "Since the guard started (%@)": "Desde que arrancó el paladín (%@)",
    "Since the guard started (%@): no interventions yet.": "Desde que arrancó el paladín (%@): todavía sin intervenciones.",
    "All time on this Mac, counting since %@": "Todo el tiempo en este Mac, contando desde %@",
    "Other Macs": "Otros Mac",
    "no interventions there yet": "allí todavía sin intervenciones",
    "%@:  %@  (last report %@ ago)": "%@:  %@  (último informe hace %@)",
    "paused / resumed / terminated / sleep-lock released": "pausados / reanudados / terminados / bloqueos de sueño liberados",
    "Heavy jobs paused": "Tareas pesadas pausadas",
    "Jobs resumed after cooling": "Reanudadas tras enfriarse",
    "Jobs terminated at the kill threshold": "Terminadas en el umbral crítico",
    "Sleep-lock releases due to heat": "Bloqueos de sueño liberados por calor",
    "counting since %@": "contando desde %@",
    "Nothing yet - the machine has not been hot enough.": "Nada aún: la máquina no se ha calentado lo suficiente.",
    "Until a set hour": "Hasta una hora concreta",
    "Extend": "Prolongar",
    "until %@": "hasta las %@",
    "Extend by %d min": "Prolongar %d min",
    "Right now: NOT keeping the Mac awake": "Ahora: sin mantener el Mac despierto",
    "no data - is coffee-paladin running?": "sin datos - ¿está funcionando coffee-paladin?",
    "data is stale (%@) - the guard may have died": "datos obsoletos (%@) - el guardián pudo detenerse",
    " (remembered)": " (recordado)",
    "the Mac shut down without warning: %@": "el Mac se apagó sin aviso: %@",
    "Battery:  %@": "Batería:  %@",
    "stopped": "parado",
    "Memory used of total, load average over cores, fan speed": "Memoria usada del total, carga media por núcleos, velocidad de los ventiladores",
    "%d rpm": "%d rpm", "%@ rpm": "%@ rpm",
    "n/a": "n/d",
    "Draw:  %.1f W": "Consumo:  %.1f W",
    "Disk:  %d / %d GB used (%d%%)": "Disco:  %d / %d GB usados (%d%%)",
    "Power:  %@": "Alimentación:  %@",
    "AC adapter": "adaptador de corriente",
    "battery %@": "batería %@",
    "Load:  %.2f / %d cores": "Carga:  %.2f / %d núcleos",
    "Throttling: CPU capped at %d%% speed": "Estrangulamiento: CPU limitada al %d%% de velocidad",
    "   readings: %.0f-%.0f C": "   lecturas: %.0f-%.0f C",
    "rising %.1f C/min - about %.0f min to pause": "sube %.1f C/min - pausa en unos %.0f min",
    "rising %.1f C/min": "sube %.1f C/min",
    "What is loading the Mac": "Qué está cargando el Mac",
    "Held: %d": "Detenidos: %d",
    "  (by hand)": "  (a mano)",
    "Calm": "En calma",
    "Warming up": "Calentándose",
    "Hot": "Caliente",
    "Critical": "Crítico",
    "Under the guard (safe-run):": "Bajo el paladín (safe-run):",
    "Heating the most (CPU stands in for heat):": "Los que más calientan (la CPU representa el calor):",
    "cores": "núcleos",
    "Chip thresholds:  pause %.0f °C, kill %.0f °C": "Umbrales del chip:  pausa %.0f °C, cierre %.0f °C",
    "Eating the most RAM:": "Lo que más RAM consume:",
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
    "OFF - the Mac is only being watched": "DESACTIVADO: el Mac solo está siendo observado",
    "Show in the bar": "Mostrar en la barra",
    "Show all": "Mostrar todo",
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
    "careful - under ordinary heavy work the chip already sits here, so long jobs will be paused often": "con cuidado - con trabajo pesado normal el chip ya está aquí, así que los trabajos largos se pausarán a menudo",
    "recommended - the pause comes well before the chip's own limiter": "recomendado - la pausa llega mucho antes del limitador propio del chip",
    "late - a job will run hot for a while before anything happens": "tarde - el trabajo estará caliente un rato antes de que pase algo",
    "almost never - the reading rarely goes higher than this, so the pause may not come at all": "casi nunca - la lectura rara vez sube más, así que la pausa puede no llegar",
    "no limit: a job may use the whole machine": "sin límite: el trabajo puede usar toda la máquina",
    "about %d of %d cores; the job gets tiny micro-pauses (works for any program)": "unos %d de %d núcleos; el trabajo recibe micropausas diminutas (funciona con cualquier programa)",
    "Battery gate": "Pausar con batería por debajo de",
    "pause below this charge when unplugged": "sin adaptador, las tareas pesadas esperarán al cargador",
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
    "Agent activity": "Actividad de agentes IA",
    "Live (from hooks):": "En vivo (desde hooks):",
    "Agents today: %@ (ccusage)": "Agentes hoy: %@ (ccusage)",
    "Per agent": "Por agente",
    "Per model": "Por modelo",
    "Active block (counted by ccusage, not your account limit)": "Bloque activo (lo cuenta ccusage, no es el límite de tu cuenta)",
    "%@ tokens · %@/min · %.0f min left": "%@ tokens · %@/min · quedan %.0f min",
    "%@ tokens · %.0f min left": "%@ tokens · quedan %.0f min",
    "at this rate the guard pauses in ~%.0f min, before the block ends": "a este ritmo el guardián pausará en ~%.0f min, antes de que acabe el bloque",
    "%@ tokens": "%@ tokens",
    "Claude limits: %@": "Límites de Claude: %@",
    "Thermal protection": "Protección térmica",
    "%@: %d%%": "%@: %d%%",
    "(resets %@)": "(se reinicia %@)",
    "5h limit": "límite 5 h",
    "7d limit": "límite 7 días",
    "context": "contexto",
    "%@  ·  idle": "%@  ·  inactiva",
    "%@  ·  %.1f cores in its tree": "%@  ·  %.1f núcleos en su árbol",
    "Chip": "Chip",
    "Battery": "Batería",
    "Fans": "Ventiladores",
    "State": "Estado",
    "Snapshot": "Instantánea",
    "Export report": "Guardar informe",
    "Start the guard again": "Iniciar el paladín de nuevo",
    "no AI session is running right now": "ninguna sesión de IA está activa ahora",
    "… %d more": "… %d más",
    "AI session marker": "Marcador de sesión IA",
    "Battery temperature (from 40 °C)": "Temperatura de la batería (desde 40 °C)",
    "Fan rpm (when spinning)": "Rpm de ventiladores (cuando giran)",
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
    "Keep awake": "Mantener el Mac despierto",
    "Off": "Apagar",
    "%d min": "%d min",
    "%d h": "%d h",
    "Indefinitely": "Indefinidamente",
    "While an app is running": "Mientras corra una aplicación",
    "While downloading (network active)": "Mientras se descarga (red activa)",
    "released automatically when the Mac gets hot": "se libera solo cuando el Mac se calienta",
    "Keep-awake: %@ left": "Despierto: quedan %@",
    "Held right now: %d": "Detenidos ahora: %d",
    "Turn thermal protection off?": "¿Desactivar la protección térmica?",
    "The paladin will keep measuring and writing down what it would have paused, and will stop nothing at all, even above %.0f °C.": "El paladín seguirá midiendo y anotando lo que habría pausado, y no detendrá nada, ni siquiera por encima de %.0f °C.",
    "Turn protection off": "Desactivar protección",
    "Keep it on": "Dejarla activada",
    "Watch only": "Solo observar",
    "The paladin keeps measuring and writes to the log what it would pause, but it stops nothing until you switch this back on.": "El paladín sigue midiendo y anota en el registro lo que pausaría, pero no detiene nada hasta que vuelvas a activar la protección.",
    "Thermal protection is on": "Protección térmica activada",
    "Above %.0f °C the paladin pauses heavy jobs and starts them again by itself at %.0f °C.": "Por encima de %.0f °C el paladín pausa los trabajos pesados y los reanuda solo a %.0f °C.",
    "Jobs resumed": "Trabajos reanudados",
    "Held jobs (%d) are running again; if the chip is still hot the paladin pauses them again on its next reading.": "Los trabajos detenidos (%d) vuelven a ejecutarse; si el chip sigue caliente, el paladín los pausará de nuevo en la siguiente lectura.",
    "Heavy processes right now: %d": "Procesos pesados ahora: %d",
    "Measurement interval": "Frecuencia de medición",
    "Pick the report period.": "Elige el periodo del informe.",
    "Included: hardware, battery, sudden shutdowns, interventions, measurement timeline.":
        "Incluye: hardware, batería, apagados repentinos, intervenciones, línea de mediciones.",
    "From:": "Desde:",
    "This topic will not work": "Este tema no funcionará",
    "Use only letters, digits, _ and -, up to 64 characters. A space stops the push silently, and # or ? publish to a shorter topic than the one you typed.": "Usa solo letras, dígitos, _ y -, hasta 64 caracteres. Un espacio bloquea el push en silencio, y # o ? publican en un tema más corto del que escribiste.",
    "First steps with the paladin": "Primeros pasos con el paladín",
    "Phone notifications…": "Notificaciones en el móvil…",
    "First steps…": "Primeros pasos...",
    "WHAT IT CAN DO\n• The paladin watches the chip, the battery, the fans and the power source - by default a reading every 15 seconds.\n• When things get too hot, it FREEZES heavy processes instead of letting the Mac cook itself. The pause destroys nothing: the process stops mid-instruction and continues once the chip cools. Example? Measured: 89 °C → 60 °C in 19 seconds, no loss.\n• It finds the real culprit: CPU is counted across the whole process tree, so it also sees a script that spawns hundreds of short jobs while using almost nothing itself.\n• On battery at 10% or less it pauses long jobs - they resume when you plug in, or once the charge is back above 25% (both figures are defaults; the Battery gate slider moves them together).\n• It keeps a black box: after a hard failure the last 8 readings survive. One click turns them into a report for a repair shop (should you ever need it).\n• Keep-awake - works like the well-known Caffeine or Amphetamine, but unlike them it comes with a fuse: the sleep lock is released the moment the Mac reaches pause level. Sleep is the fastest cooling there is.": "QUÉ SABE HACER\n• El paladín vigila el chip, la batería, los ventiladores y la fuente de alimentación: por defecto una medición cada 15 segundos.\n• Cuando la cosa se calienta demasiado, CONGELA los procesos pesados en vez de dejar que el Mac se cueza. La pausa no destruye nada: el proceso se detiene a mitad de instrucción y sigue en cuanto el chip se enfría. ¿Un ejemplo? Medido: 89 °C → 60 °C en 19 segundos, sin pérdidas.\n• Encuentra al culpable de verdad: la CPU se cuenta en todo el árbol de procesos, así que también ve el script que lanza cientos de tareas cortas sin apenas consumir por sí mismo.\n• Con la batería al 10% o menos pausa los trabajos largos, y los reanuda cuando enchufas la corriente o cuando la carga vuelve a superar el 25% (las dos cifras son valores por defecto, el deslizador «Pausar con batería por debajo de» las mueve juntas).\n• Lleva una caja negra: tras un fallo brusco sobreviven las 8 últimas mediciones. Con un clic se convierten en un informe para el servicio técnico (por si algún día hace falta).\n• Mantener el Mac despierto: funciona como los conocidos Caffeine o Amphetamine, pero a diferencia de ellos viene con fusible: el bloqueo del sueño se suelta en el momento en que el Mac llega al nivel de pausa. Dormir es la forma más rápida de enfriar.",
    "WHAT WILL HAPPEN\n• Your choice in the welcome window decides how you start.\n\n\"Watch only\" mode: the paladin measures, logs and alerts, but PAUSES NOTHING.\n\n\"Enable protection\" mode: it pauses at the defined thresholds.\n\nSwitching is easy - one switch at the top of the menu.\n\n• Default thresholds on a Mac with fans: pause at 85 °C, resume at 76 °C, gentle closing of processes at 90 °C - and only after 4 critical readings in a row, which is about 45 seconds at the default 15-second interval and shorter if you speed the interval up. A fanless Mac (an Air, or Neo) gets 78/70/88 instead. The thresholds are always picked for YOUR machine: see menu > \"About my Mac\".\n\n• Termination is the last resort, for when the chip stays critical despite the pauses: something we could not pause is heating, or pausing was not enough. The process is woken up first and gets SIGTERM, a polite \"shut down\" - a chance to save its state, close its files, clean up. That is why we call it gentle. Twenty seconds later, anything still alive gets SIGKILL. A job left frozen for more than 45 minutes is closed the same gentle way; a pause caused only by a low battery gets 4 hours, because waiting for a charger is not a failure.\n\n• A pause is not the only remedy. The process that caused it comes back on efficiency cores instead of at full speed, and stays there until the Mac has been quiet for five minutes. A job you started with `safe-run --normal` keeps all its cores.\n\n• Notifications: on. Sounds: off (enable them in Settings). At the critical level a system banner breaks through everything - Focus and full-screen included.\n• The system, Finder, your terminal and your AI agent are never frozen. An app with a window that the guard does not know by name, a browser or a video app, is pushed to efficiency cores and named in the menu instead of being frozen - unless there is a real emergency: a cooling failure, the battery at its kill threshold, or macOS itself reporting critical. A heavy job it does know by name (python, ffmpeg, a compiler) is paused whether or not it sits inside an app bundle. The guard will not freeze the session working next to it.": "QUÉ VA A PASAR\n• Tu elección en la ventana de bienvenida decide cómo empiezas.\n\nModo «Solo observar»: el paladín mide, registra y avisa, pero NO PAUSA NADA.\n\nModo «Activar protección»: pausa en los umbrales definidos.\n\nCambiar es fácil, hay un interruptor arriba del todo en el menú.\n\n• Umbrales por defecto en un Mac con ventiladores: pausa a 85 °C, reanudación a 76 °C, cierre suave de procesos a 90 °C, y solo después de 4 lecturas críticas seguidas, que son unos 45 segundos con el intervalo por defecto de 15 s, y menos si aceleras el intervalo. Un Mac sin ventilador (un Air, o Neo) usa 78/70/88 en su lugar. Los umbrales se eligen siempre para TU máquina: mira el menú > «Acerca de mi Mac».\n\n• Terminar el proceso es el último recurso, para cuando el chip sigue en estado crítico pese a las pausas: está calentando algo que no pudimos pausar, o pausar no bastó. Primero se despierta el proceso y recibe SIGTERM, un cortés «ciérrate», es decir, la oportunidad de guardar su estado, cerrar sus archivos y limpiar. Por eso lo llamamos cierre suave. Veinte segundos después, lo que siga vivo recibe SIGKILL. Un trabajo que lleve congelado más de 45 minutos se cierra de la misma manera suave; una pausa causada solo por batería baja tiene 4 horas, porque esperar al cargador no es un fallo.\n\n• La pausa no es el único remedio. El proceso que la provocó vuelve en los núcleos de eficiencia en vez de a toda velocidad, y se queda ahí hasta que el Mac lleve cinco minutos tranquilo. Un trabajo que hayas lanzado con `safe-run --normal` conserva todos sus núcleos.\n\n• Notificaciones: activadas. Sonidos: desactivados (actívalos en Ajustes). En el nivel crítico un aviso del sistema atraviesa todo, incluidos Concentración y la pantalla completa.\n• El sistema, Finder, tu terminal y tu agente de IA nunca se congelan. Una app con ventana que el guardián no conoce por su nombre, un navegador o un programa de vídeo, pasa a los núcleos de eficiencia y aparece nombrada en el menú en vez de ser congelada, salvo que haya una emergencia real: un fallo de refrigeración, la batería en su umbral de terminación o el propio macOS informando de estado crítico. Un trabajo pesado que sí conoce por su nombre (python, ffmpeg, un compilador) se pausa esté o no dentro de un paquete de aplicación. El guardián no congelará la sesión que trabaja a su lado.",
    "WHAT YOU CAN SET\n• Chip pause threshold - a slider; resume follows 9 °C lower, gentle closing 5 °C higher (never above 100).\n• Measurement interval 5-30 s: more often = faster reaction, but costlier in CPU use.\n• Heavy jobs (safe-run): all cores (fast) or efficiency cores only (cool and quiet), plus a CPU limit of 50-100%.\n• Battery gate, signals, keep-awake, this Mac's name in the fleet.": "QUÉ PUEDES CONFIGURAR\n• Umbral de pausa del chip: un deslizador; la reanudación va 9 °C por debajo y el cierre suave 5 °C por encima (nunca por encima de 100).\n• Intervalo de medición 5-30 s: más a menudo = reacción más rápida, pero más gasto de CPU.\n• Trabajos pesados (safe-run): todos los núcleos (rápido) o solo los de eficiencia (fresco y silencioso), más un límite de CPU del 50-100%.\n• «Pausar con batería por debajo de», señales, «Mantener el Mac despierto» y el nombre de este Mac en la flota.",
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
    "max capacity: %d%%": "capacidad máx.: %d%%",
    "set up: %@": "configurado: %@",
    "Turns off banners, their sounds and phone push - one gate for all.":
        "Apaga avisos, sus sonidos y el push al móvil: una sola puerta para todo.",
    "Exception: the critical banner shouts regardless.":
        "Excepción: el banner crítico grita igualmente.",
    "It is the ‹Thermal protection› switch: OFF = watch-only.":
        "Es el estado del interruptor ‹Protección térmica›: apagado = solo observación.",
    "fastest reaction - the guard itself burns ~3.5% of one core all the time":
        "reacción más rápida, pero el guardián quema ~3,5% de un núcleo sin parar",
    "reacts up to 5 s sooner than default, costs ~1.8% of one core":
        "reacciona hasta 5 s antes, cuesta ~1,8% de un núcleo",
    "default: good reaction at ~1.2% of one core":
        "por defecto: buena reacción con ~1,2% de un núcleo",
    "frugal - an automatic pause may come tens of seconds after the threshold":
        "ahorrador, pero la pausa automática puede llegar decenas de segundos tras el umbral",
    "Heavy jobs (safe-run)": "Tareas pesadas (safe-run)",
    "Efficiency cores only (cool and quiet)": "Solo núcleos de eficiencia (frío y silencioso)",
    "All cores (fast - the paladin still watches the temperature)":
        "Todos los núcleos (rápido - el paladín sigue vigilando la temperatura)",
    "CPU limit for heavy jobs": "Límite de CPU para tareas pesadas",
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
    "macOS:  %@": "macOS:  %@",
    "Cores:  %d performance + %d efficiency  ·  %d GB RAM": "Núcleos:  %d de rendimiento + %d de eficiencia  ·  %d GB de RAM",
    "Cooling:  %d fans": "Refrigeración:  %d ventiladores",
    "Cooling:  passive, no fans": "Refrigeración:  pasiva, sin ventiladores",
    "Chip reading:  the higher of the CPU and GPU average (macmon)": "Lectura del chip:  la mayor de las medias de CPU y GPU (macmon)",
    "macmon averages every SMC key it can read: Tp/Te/Ts on the CPU side, Tg on the GPU side. The guard shows whichever average is higher, so during LLM or video work this is the GPU cluster. It is a relative index, not the hottest transistor, and the two averages saturate at different values on the same machine.": "macmon promedia todas las claves SMC que puede leer: Tp/Te/Ts en el lado de la CPU, Tg en el de la GPU. El paladín muestra la media más alta, así que durante trabajo con LLM o vídeo es el clúster de GPU. Es un índice relativo, no el transistor más caliente, y las dos medias se saturan en valores distintos en la misma máquina.",
    "The chip reading is missing - is macmon installed?": "Falta la lectura del chip - ¿está instalado macmon?",
    "Serial:  %@": "Número de serie:  %@",
    "Battery cycles:  %@": "Ciclos de batería:  %@",
    "Chip sensor (macmon):  %@": "Sensor del chip (macmon):  %@",
    "yes": "sí",
    "no": "no",
    "Uninstall coffee-paladin…":
        "Desinstalar coffee-paladin…",
    "Uninstall coffee-paladin?":
        "¿Desinstalar coffee-paladin?",
    "Goes away: the daemon and the menu bar (they stop starting at login), the app, the heat, safe-run, thermal-report and fleet commands, and the skill for AI agents.\n\nStays: the measurement history and the black box in ~/.coffee-paladin. That is what a service centre asks for when a Mac dies under load.":
        "Se va: el demonio y la barra de menus (dejan de arrancar al iniciar sesion), la app y los comandos heat, safe-run, thermal-report y fleet, mas la habilidad para agentes de IA.\n\nSe queda: el historial de mediciones y la caja negra en ~/.coffee-paladin. Es justo lo que pide un servicio tecnico cuando un Mac se apaga bajo carga.",
    "Delete the history and the black box too":
        "Borrar tambien el historial y la caja negra",
    "Uninstall":
        "Desinstalar",
    "Delete the black box as well?":
        "¿Borrar tambien la caja negra?",
    "Every measurement, every pause and every hard shutdown this Mac recorded goes with it. This cannot be undone, and it is the record a service centre or a warranty claim asks for. Uninstalling without this leaves the files untouched and costs nothing.":
        "Desaparece cada medicion, cada pausa y cada apagado brusco que este Mac registro. No se puede deshacer, y es justo el registro que pide un servicio tecnico o una reclamacion de garantia. Desinstalar sin esto deja los archivos intactos y no cuesta nada.",
    "Delete everything":
        "Borrar todo",
    "Icon only, no numbers":
        "Solo el icono (cabe en cualquier barra)",
    "Icon and chip temperature":
        "Icono y temperatura del chip",
]

let DICTS: [String: [String: String]] = ["pl": PL, "ru": RU, "zh": ZH, "es": ES]

func T(_ s: String) -> String { DICTS[lang]?[s] ?? s }

// MARK: - icons

// Coffee uses cup.and.saucer after "mug" proved less clear.
let MUG = "cup.and.saucer"
let MUG_FILL = "cup.and.saucer.fill"

/// Draw a small app-icon-style logo on demand.
/// The logo is a gradient squircle with a white thermometer and no resource files.
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

/// Load the user's custom logo from ~/.coffee-paladin/logo.png.
/// The image must be a black mark on a transparent background; isTemplate lets macOS
/// recolor it for the current light or dark appearance.
func customLogo() -> NSImage? {
    guard let img = NSImage(contentsOfFile: base + "/logo.png") else { return nil }
    img.isTemplate = true
    return img
}


// MARK: - paladin welcome (first launch)

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

/// Show the welcome window once, on the first menu bar launch.
/// It uses monochrome paladin art, labelColor for light/dark appearance, vibrancy,
/// and a startup mode choice.
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
        playPaladinSound(force: true)
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

        // Paladin art, best fallback first:
        //   1. paladin_welcome.gif  - official animation (NSImageView plays GIFs),
        //   2. paladin_welcome.png  - same character, static frame,
        //   3. PALADIN_FRAMES       - ASCII frames when branding assets are missing.
        // The third level keeps the window from ever being empty.
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
            iv.animates = true          // GIF only; no effect for PNG
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

        // The guide link opens a side window, but does NOT close welcome or set welcomed.
        // The user still must choose one of the startup modes above.
        let guideBtn = NSButton(title: T("First steps…"), target: self, action: #selector(openGuideLink))
        guideBtn.isBordered = false
        guideBtn.attributedTitle = NSAttributedString(string: T("First steps…"),
            attributes: [.font: NSFont.systemFont(ofSize: 11),
                         .foregroundColor: NSColor.linkColor])
        guideBtn.frame = NSRect(x: W/2 - 150, y: 8, width: 300, height: 20)
        fx.addSubview(guideBtn)

        // The timer runs only in ASCII mode. Sprites are animated by NSImageView;
        // waking the CPU 11x/s for no reason is exactly what a fanless Mac does not need.
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

// MARK: - fleet (shared folder, same files as CLI `fleet`)

struct FleetHost {
    let name: String
    var model: String = ""
    var serial: String = ""
    let age: TimeInterval
    let chip: Double?
    /// The host published a remembered reading, not a measured one. Rendered with "~"
    /// so a fleet operator reading the menu sees the same qualifier the CLI shows.
    var chipStale: Bool = false
    let fans: Int?
    let watts: Double?
    let ramPct: Int?
    let level: Int
    let paused: [String]
    let onAC: Bool
    let battPct: Int?
    var battC: Double? = nil
}

/// Read guard counters from every machine in the fleet folder.
/// Fleet snapshots use nil for an unconfigured or unreadable folder, and an empty list
/// when the folder exists but no host has published yet.
///
/// This stays separate from `fleetHosts()`: that function carries momentary readings,
/// while this one carries totals. The fleet snapshot is a copy of the local snapshot,
/// so counters are already in it and need no protocol change.
///
/// Return file age too: numbers from a machine that has not reported for fifteen minutes
/// must not look current.
func fleetStats() -> [(host: String, ses: [String: Int], sum: [String: Int], age: TimeInterval)] {
    let raw = GuardCfg.string("fleet_dir", "")
    guard !raw.isEmpty else { return [] }
    let dir = NSString(string: raw).expandingTildeInPath
    guard let items = try? FileManager.default.contentsOfDirectory(atPath: dir) else { return [] }
    var out: [(host: String, ses: [String: Int], sum: [String: Int], age: TimeInterval)] = []
    for fname in items.sorted() {
        guard fname.hasSuffix(".json"), !fname.hasPrefix(".") else { continue }
        let path = dir + "/" + fname
        guard let d = FileManager.default.contents(atPath: path),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { continue }
        func readCounts(_ key: String) -> [String: Int] {
            var w: [String: Int] = [:]
            if let t = j[key] as? [String: Any] {
                // "since" arrives as a fractional epoch (Python time.time()); `as? Int`
                // rejects it and the date silently vanishes, so go through NSNumber.
                for (k, v) in t { if let n = v as? NSNumber { w[k] = n.intValue } }
            }
            return w
        }
        let mtime = (try? FileManager.default.attributesOfItem(atPath: path)[.modificationDate]) as? Date
        let host = (j["host"] as? String) ?? String(fname.dropLast(5))
        out.append((host: host, ses: readCounts("stats_session"), sum: readCounts("stats_total"),
                    age: mtime.map { Date().timeIntervalSince($0) } ?? 1e9))
    }
    return out
}

func fleetHosts() -> [FleetHost]? {
    let raw = GuardCfg.string("fleet_dir", "")
    guard !raw.isEmpty else { return nil }
    let dir = NSString(string: raw).expandingTildeInPath
    guard let items = try? FileManager.default.contentsOfDirectory(atPath: dir) else { return nil }
    var out: [FleetHost] = []
    for fname in items.sorted() {
        // An iCloud-evicted file (".<host>.json.icloud") means the host EXISTS, but
        // data is not local. Show it as stale instead of silently hiding it.
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
            // max(0,...): future mtime from SMB clock skew must not produce a
            // negative age, or the host would look forever fresh.
            age: mtime.map { max(0, Date().timeIntervalSince($0)) } ?? 1e9,
            chip: num(j["chip_c"]),
            chipStale: (j["chip_stale"] as? Bool) ?? false,
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
    // Floor, do not round: 95 s is "1 min ago", not "2 min ago".
    if s < 60 { return T("now") }
    if s < 7200 { return String(format: T("%d min ago"), max(1, Int(s / 60))) }
    return String(format: T("%d h ago"), Int(s / 3600))
}

/// Show the footer logo from ~/.coffee-paladin/logo_footer.png.
/// In dark mode, prefer logo_footer_dark.png with light text when it exists.
/// Missing files mean no row.
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
        // The logo is a button: click opens the URL from config.json (`footer_logo_url`).
        // Centred against the REAL width, not the 400 pt this view is born with: NSMenu
        // stretches the row to the menu's width, and the header already re-centres for
        // the same reason. Without it the mark sat off to one side.
        let b = NSButton(frame: NSRect(x: (400 - w) / 2, y: 6, width: w, height: h))
        b.image = img
        b.isBordered = false
        b.imagePosition = .imageOnly
        b.imageScaling = .scaleProportionallyUpOrDown
        b.target = self
        b.action = #selector(openSite)
        b.toolTip = GuardCfg.string("footer_logo_url", "")
        addSubview(b)
        logoButton = b
    }

    private var logoButton: NSButton?

    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        if let b = logoButton { b.frame.origin.x = (bounds.width - b.frame.width) / 2 }
    }

    @objc private func openSite() {
        let raw = GuardCfg.string("footer_logo_url", "")
        if !raw.isEmpty, let url = URL(string: raw) {
            NSWorkspace.shared.open(urlWithUTM(url.absoluteString) ?? url)
        }
    }

    required init?(coder: NSCoder) { fatalError() }
}

/// Render the menu header with centered logo, name, and version.
/// If ~/.coffee-paladin/logo.png exists, show it; otherwise draw the built-in squircle.
/// Every external app link carries UTM so analytics can distinguish menu-bar traffic
/// from README or post traffic.
func urlWithUTM(_ s: String, medium: String = "app") -> URL? {
    guard var c = URLComponents(string: s) else { return URL(string: s) }
    var q = c.queryItems ?? []
    q.append(contentsOf: [URLQueryItem(name: "utm_source", value: "coffee-paladin"),
                          URLQueryItem(name: "utm_medium", value: medium),
                          URLQueryItem(name: "utm_campaign", value: "panbookovsky")])
    c.queryItems = q
    return c.url ?? URL(string: s)
}

/// Build the repository link with UTM "share" for share posts and emails.
func shareLink() -> String {
    urlWithUTM("https://github.com/pawelkwaczynski/coffee-paladin", medium: "share")?.absoluteString
        ?? "https://github.com/pawelkwaczynski/coffee-paladin"
}


/// Play the optional paladin armor sound when showing paladin art.
/// The same Sounds switch controls it; missing file means silence, not an error.
/// `force` is for the one-time welcome chime: it plays before the user has ever
/// seen the Sounds switch, so the daemon's silent default must not mute it.
func playPaladinSound(force: Bool = false) {
    guard force || GuardCfg.bool("sound", false) else { return }
    let p = base + "/sounds/paladin.wav"
    guard FileManager.default.fileExists(atPath: p) else { return }
    let pr = Process()
    pr.executableURL = URL(fileURLWithPath: "/usr/bin/afplay")
    pr.arguments = [p]
    try? pr.run()
}



/// Show the "First steps" guide in the menu language.
/// It is available from the menu and welcome window; a second click only raises it.
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

        let iconView = NSImageView(frame: NSRect(x: (W - 40) / 2, y: H - 58, width: 40, height: 40))
        if let img = NSImage(contentsOfFile: base + "/paladin_welcome.png") { iconView.image = img }
        iconView.imageScaling = .scaleProportionallyUpOrDown
        fx.addSubview(iconView)
        let title = NSTextField(labelWithString: T("First steps with the paladin"))
        title.font = .boldSystemFont(ofSize: 14)
        title.alignment = .center
        title.frame = NSRect(x: 0, y: H - 84, width: W, height: 20)
        fx.addSubview(title)

        let text = NSMutableAttributedString()
        // Three sections, not four: what it can do, what will happen, what you can set.
        // The phone-push walkthrough is setup for a feature that is off by default - it
        // made a first-run screen read like a manual, so it moved behind its own button.
        let sections = [T(GUIDE_CAN), T(GUIDE_WILL), T(GUIDE_SET)]
        for s in sections {
            let lines = s.split(separator: "\n", maxSplits: 1, omittingEmptySubsequences: false)
            // Add the colon and blank line under each section header while assembling text,
            // not in dictionaries. Otherwise every change would touch four headers in five
            // languages, twenty entries total.
            var header = String(lines[0]).trimmingCharacters(in: .whitespaces)
            if !header.hasSuffix(":") { header += ":" }
            text.append(NSAttributedString(string: header + "\n\n",
                attributes: [.font: NSFont.boldSystemFont(ofSize: 12), .foregroundColor: NSColor.labelColor]))
            if lines.count > 1 {
                text.append(NSAttributedString(string: String(lines[1]),
                    attributes: [.font: NSFont.systemFont(ofSize: 12), .foregroundColor: NSColor.secondaryLabelColor]))
            }
            text.append(NSAttributedString(string: "\n\n"))
        }
        text.append(NSAttributedString(string: T(GUIDE_BYE),
            attributes: [.font: NSFont.systemFont(ofSize: 12, weight: .medium), .foregroundColor: NSColor.labelColor]))

        // The phone-push setup lives here as a button: one click to the same dialog that
        // used to be a wall of text in the middle of a first-run screen.
        let ntfyBtn = NSButton(title: T("Phone notifications…"), target: Bar.shared,
                               action: #selector(Bar.ntfyDialog))
        ntfyBtn.bezelStyle = .rounded
        // Centred, not pinned to the left corner: it is the only button in the window,
        // and the width has to hold the longest label of the five languages.
        let ntfyW: CGFloat = 260
        ntfyBtn.frame = NSRect(x: (W - ntfyW) / 2, y: 12, width: ntfyW, height: 24)
        fx.addSubview(ntfyBtn)

        let scroll = NSScrollView(frame: NSRect(x: 16, y: 46, width: W - 32, height: H - 140))
        scroll.hasVerticalScroller = true
        scroll.drawsBackground = false
        let tv = NSTextView(frame: NSRect(x: 0, y: 0, width: W - 48, height: 10))
        tv.isEditable = false
        tv.drawsBackground = false
        tv.textContainerInset = NSSize(width: 0, height: 4)
        tv.textStorage?.setAttributedString(text)
        tv.isVerticallyResizable = true
        tv.autoresizingMask = [.width]
        scroll.documentView = tv
        fx.addSubview(scroll)

        win = w
        w.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}

// Guide content keys (EN = translation dictionary key).
let GUIDE_CAN = "WHAT IT CAN DO\n• The paladin watches the chip, the battery, the fans and the power source - by default a reading every 15 seconds.\n• When things get too hot, it FREEZES heavy processes instead of letting the Mac cook itself. The pause destroys nothing: the process stops mid-instruction and continues once the chip cools. Example? Measured: 89 °C → 60 °C in 19 seconds, no loss.\n• It finds the real culprit: CPU is counted across the whole process tree, so it also sees a script that spawns hundreds of short jobs while using almost nothing itself.\n• On battery at 10% or less it pauses long jobs - they resume when you plug in, or once the charge is back above 25% (both figures are defaults; the Battery gate slider moves them together).\n• It keeps a black box: after a hard failure the last 8 readings survive. One click turns them into a report for a repair shop (should you ever need it).\n• Keep-awake - works like the well-known Caffeine or Amphetamine, but unlike them it comes with a fuse: the sleep lock is released the moment the Mac reaches pause level. Sleep is the fastest cooling there is."
let GUIDE_WILL = "WHAT WILL HAPPEN\n• Your choice in the welcome window decides how you start.\n\n\"Watch only\" mode: the paladin measures, logs and alerts, but PAUSES NOTHING.\n\n\"Enable protection\" mode: it pauses at the defined thresholds.\n\nSwitching is easy - one switch at the top of the menu.\n\n• Default thresholds on a Mac with fans: pause at 85 °C, resume at 76 °C, gentle closing of processes at 90 °C - and only after 4 critical readings in a row, which is about 45 seconds at the default 15-second interval and shorter if you speed the interval up. A fanless Mac (an Air, or Neo) gets 78/70/88 instead. The thresholds are always picked for YOUR machine: see menu > \"About my Mac\".\n\n• Termination is the last resort, for when the chip stays critical despite the pauses: something we could not pause is heating, or pausing was not enough. The process is woken up first and gets SIGTERM, a polite \"shut down\" - a chance to save its state, close its files, clean up. That is why we call it gentle. Twenty seconds later, anything still alive gets SIGKILL. A job left frozen for more than 45 minutes is closed the same gentle way; a pause caused only by a low battery gets 4 hours, because waiting for a charger is not a failure.\n\n• A pause is not the only remedy. The process that caused it comes back on efficiency cores instead of at full speed, and stays there until the Mac has been quiet for five minutes. A job you started with `safe-run --normal` keeps all its cores.\n\n• Notifications: on. Sounds: off (enable them in Settings). At the critical level a system banner breaks through everything - Focus and full-screen included.\n• The system, Finder, your terminal and your AI agent are never frozen. An app with a window that the guard does not know by name, a browser or a video app, is pushed to efficiency cores and named in the menu instead of being frozen - unless there is a real emergency: a cooling failure, the battery at its kill threshold, or macOS itself reporting critical. A heavy job it does know by name (python, ffmpeg, a compiler) is paused whether or not it sits inside an app bundle. The guard will not freeze the session working next to it."
let GUIDE_SET = "WHAT YOU CAN SET\n• Chip pause threshold - a slider; resume follows 9 °C lower, gentle closing 5 °C higher (never above 100).\n• Measurement interval 5-30 s: more often = faster reaction, but costlier in CPU use.\n• Heavy jobs (safe-run): all cores (fast) or efficiency cores only (cool and quiet), plus a CPU limit of 50-100%.\n• Battery gate, signals, keep-awake, this Mac's name in the fleet."
let GUIDE_BYE = "Enjoy your work!\nPaweł"


final class HeaderRow: NSView {
    private var logoView: NSImageView?
    private var appLabel: NSTextField?
    private var centeredLabels: [NSTextField] = []

    init() {
        // 360, not 400: the header must not be what widens the whole menu.
        // NSMenu still supplies the real width; center in setFrameSize.
        super.init(frame: NSRect(x: 0, y: 0, width: 400, height: 88))
        autoresizingMask = [.width]
        if let logo = customLogo() {
            // Horizontal logo (wordmark): centered, height 22, width from aspect ratio.
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
        // Product name and motto are the product's face and must stay at the top
        // of the menu, not only in the footer.
        // Deliberately no paladin thumbnail beside them: detailed art at 30 px
        // becomes a color sticker and clashes with the monochrome wordmark above.
        // Paladin art lives in the panel (name click) and the welcome window.
        let app = NSTextField(labelWithString: "\(APPNAME)  ·  v\(VERSION)")
        app.font = .systemFont(ofSize: 13, weight: .semibold)
        app.textColor = .labelColor
        app.alignment = .center
        app.frame = NSRect(x: 0, y: 38, width: 360, height: 18)
        addSubview(app)
        appLabel = app
        centeredLabels.append(app)

        let motto = NSTextField(labelWithString: MOTTO)
        motto.font = .systemFont(ofSize: 11, weight: .regular)
        motto.textColor = .labelColor
        motto.alignment = .center
        motto.frame = NSRect(x: 0, y: 22, width: 360, height: 14)
        addSubview(motto)
        centeredLabels.append(motto)

        let name = NSTextField(labelWithString: T("A project of the AIrON student research club."))
        name.font = .systemFont(ofSize: 11)
        name.textColor = .secondaryLabelColor
        name.alignment = .center
        name.frame = NSRect(x: 0, y: 6, width: 360, height: 14)
        addSubview(name)
        centeredLabels.append(name)

        // .inVisibleRect: the tracking area follows EVERY row resize, so the
        // pointing cursor still works after NSMenu stretches the view.
        addTrackingArea(NSTrackingArea(rect: .zero,
                                       options: [.mouseEnteredAndExited, .activeAlways,
                                                 .cursorUpdate, .inVisibleRect],
                                       owner: self, userInfo: nil))
        layoutContent()
    }
    required init?(coder: NSCoder) { fatalError() }

    // The header used to be centered in a fixed 400 pt while the menu can be wider.
    // Center from bounds.
    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        layoutContent()
    }

    private func layoutContent() {
        if let iv = logoView {
            iv.frame.origin.x = (bounds.width - iv.frame.width) / 2
        }
        for l in centeredLabels { l.frame.size.width = bounds.width }
    }

    private func isOnLogo(_ p: NSPoint) -> Bool { logoView?.frame.contains(p) ?? false }
    private func isOnName(_ p: NSPoint) -> Bool { appLabel?.frame.contains(p) ?? false }

    override func cursorUpdate(with event: NSEvent) {
        let p = convert(event.locationInWindow, from: nil)
        if isOnLogo(p) || isOnName(p) { NSCursor.pointingHand.set() } else { NSCursor.arrow.set() }
    }

    override func mouseUp(with event: NSEvent) {
        let p = convert(event.locationInWindow, from: nil)
        if isOnLogo(p) {
            // The AIrON logo links to the student club's English CS program at AHE.
            enclosingMenuItem?.menu?.cancelTracking()
            if let u = urlWithUTM("https://www.ahe.lodz.pl/study-in-english/eng-in-computer-science") {
                NSWorkspace.shared.open(u)
            }
            return
        }
        guard isOnName(p) else { return }
        // Close the menu before showing the panel; otherwise it captures mouse events
        // and the panel cannot be dismissed by click.
        enclosingMenuItem?.menu?.cancelTracking()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.12) { PaladinPanel.shared.toggle() }
    }
}


/// Show the paladin panel anchored to the menu bar icon.
/// It uses the official animation, does not take focus or appear in Dock/Cmd-Tab,
/// and closes on the first outside click or Esc.
final class PaladinPanel: NSObject {
    static let shared = PaladinPanel()
    private var panel: NSPanel?
    private var localMonitor: Any?
    private var globalMonitor: Any?

    func toggle() {
        if panel != nil { close(); return }
        guard let sprite = NSImage(contentsOfFile: base + "/paladin_welcome.gif")
            ?? NSImage(contentsOfFile: base + "/paladin_welcome.png") else { return }
        playPaladinSound()   // Play armor sound for the panel too.

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

        let nameLabel = NSTextField(labelWithString: APPNAME)
        nameLabel.font = .systemFont(ofSize: 13, weight: .semibold)
        nameLabel.alignment = .center
        nameLabel.frame = NSRect(x: 0, y: 28, width: W, height: 18)
        fx.addSubview(nameLabel)

        let motto = NSTextField(labelWithString: MOTTO)
        motto.font = .systemFont(ofSize: 11)
        motto.textColor = .secondaryLabelColor
        motto.alignment = .center
        motto.frame = NSRect(x: 8, y: 10, width: W - 16, height: 14)
        fx.addSubview(motto)

        positionBelow(p, width: W, height: H)
        p.orderFrontRegardless()
        panel = p

        // Close on any click, including inside the panel, or Esc.
        globalMonitor = NSEvent.addGlobalMonitorForEvents(
            matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in self?.close() }
        localMonitor = NSEvent.addLocalMonitorForEvents(
            matching: [.leftMouseDown, .rightMouseDown, .keyDown]) { [weak self] e in
                if e.type == .keyDown && e.keyCode != 53 { return e }   // 53 = Esc
                self?.close(); return e
            }
    }

    /// Anchor the panel under the menu bar icon.
    /// If the icon cannot be located (another display, hidden by Bartender), fall back
    /// to the top-right screen corner.
    private func positionBelow(_ p: NSPanel, width W: CGFloat, height H: CGFloat) {
        if let b = Bar.shared?.item.button, let buttonWindow = b.window {
            let screenRect = buttonWindow.convertToScreen(b.convert(b.bounds, to: nil))
            var x = screenRect.midX - W/2
            let y = screenRect.minY - H - 6
            if let vis = (buttonWindow.screen ?? NSScreen.main)?.visibleFrame {
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
        if let m = globalMonitor { NSEvent.removeMonitor(m); globalMonitor = nil }
        if let m = localMonitor { NSEvent.removeMonitor(m); localMonitor = nil }
        panel?.orderOut(nil)
        panel = nil
    }
}


/// Draw a switch with explicit protection colors.
/// NSSwitch inherits the system accent color; here green must mean protected and gray
/// must mean not protected. The colors are systemGreen / tertiaryLabel, so they work
/// in light and dark appearances.
final class ToggleSwitch: NSControl {
    var isOn: Bool { didSet { needsDisplay = true } }
    var color: NSColor = .systemGreen
    init(on: Bool, target: AnyObject, action: Selector) {
        self.isOn = on
        super.init(frame: NSRect(x: 0, y: 0, width: 38, height: 22))
        self.target = target
        self.action = action
    }
    required init?(coder: NSCoder) { fatalError() }

    override func draw(_ r: NSRect) {
        let trackRect = NSRect(x: 0, y: 2, width: bounds.width, height: bounds.height - 4)
        let trackPath = NSBezierPath(roundedRect: trackRect, xRadius: trackRect.height / 2, yRadius: trackRect.height / 2)
        (isOn ? color : NSColor.tertiaryLabelColor).setFill()
        trackPath.fill()
        let d = trackRect.height - 4
        let x = isOn ? trackRect.maxX - d - 2 : trackRect.minX + 2
        let knob = NSBezierPath(ovalIn: NSRect(x: x, y: trackRect.minY + 2, width: d, height: d))
        NSColor.white.setFill()
        NSGraphicsContext.saveGraphicsState()
        let shadow = NSShadow()
        shadow.shadowColor = NSColor.black.withAlphaComponent(0.25)
        shadow.shadowBlurRadius = 1.5
        shadow.shadowOffset = NSSize(width: 0, height: -0.5)
        shadow.set()
        knob.fill()
        NSGraphicsContext.restoreGraphicsState()
    }

    override func mouseDown(with event: NSEvent) {
        toggle()
    }

    func toggle() {
        isOn.toggle()
        if let a = action { NSApp.sendAction(a, to: target, from: self) }
    }

    // ACCESSIBILITY. This switch decides whether the Mac is protected, but it is drawn
    // manually and used to announce nothing. VoiceOver only read the row label, so a
    // blind user did not know this was a switch or what state it was in. It also was
    // not keyboard-operable.
    override func isAccessibilityElement() -> Bool { true }
    override func accessibilityRole() -> NSAccessibility.Role? { .checkBox }
    override func accessibilityValue() -> Any? { isOn }
    override func isAccessibilityEnabled() -> Bool { true }
    override func accessibilityPerformPress() -> Bool { toggle(); return true }

    override var acceptsFirstResponder: Bool { true }
    override func keyDown(with event: NSEvent) {
        // Space and Enter behave like any system control.
        if event.keyCode == 49 || event.keyCode == 36 { toggle() } else { super.keyDown(with: event) }
    }
}


/// Render a menu row with a label on the left and a switch on the right.
/// The two most-used toggles, thermal pausing and autostart, need visible state
/// without reading surrounding text.
final class SwitchRow: NSView {
    /// Update the subtitle live after the switch changes.
    /// It used to be built once when the menu opened: a click changed config, but the
    /// text stayed old until close/reopen, which makes the switch look broken.
    private var subtitleLabel: NSTextField?
    private var titleLabel: NSTextField?
    private var toggleSwitch: ToggleSwitch?
    private var textX: CGFloat = 21
    private let offSubtitle: String?
    private weak var externalTarget: AnyObject?
    private let externalAction: Selector

    init(_ title: String, on: Bool, target: AnyObject, action: Selector,
         offSubtitle: String? = nil, iconName: String? = nil,
         fixedSubtitle: String? = nil, color: NSColor = .systemGreen) {
        self.offSubtitle = offSubtitle
        self.externalTarget = target
        self.externalAction = action
        // Height is CONSTANT, even when the subtitle is temporarily absent; otherwise
        // the row jumps on every toggle and widens the menu.
        // Reserve space for the red subtitle ONLY when protection is off as the menu
        // opens. Reserving it while protection is on left an empty line and made two
        // switches look oddly far apart. If protection is toggled OFF in an open menu,
        // there is no room for the red subtitle; the switch state and "watch-only"
        // guard notification carry the state.
        let W: CGFloat = 360
        let H: CGFloat = (fixedSubtitle != nil || (offSubtitle != nil && !on)) ? 40 : 26
        super.init(frame: NSRect(x: 0, y: 0, width: W, height: H))
        // The switch hugs the RIGHT edge of the real menu, not a fixed 400 pt width.
        autoresizingMask = [.width]

        // Icon on the left, like regular menu items. A switch row must not look
        // truncated next to rows that have icons.
        if let iconName = iconName,
           let sym = NSImage(systemSymbolName: iconName, accessibilityDescription: nil) {
            sym.isTemplate = true
            let iv = NSImageView(image: sym)
            iv.contentTintColor = .secondaryLabelColor
            iv.frame = NSRect(x: 20, y: H - 21, width: 16, height: 16)
            addSubview(iv)
            textX = 44
        }

        let et = NSTextField(labelWithString: title)
        et.font = .menuFont(ofSize: 0)
        et.textColor = .labelColor
        et.frame = NSRect(x: textX, y: H - 20, width: W - 69 - textX, height: 17)
        addSubview(et)
        titleLabel = et

        if offSubtitle != nil && !on {
            let pod = NSTextField(labelWithString: "")
            pod.font = .systemFont(ofSize: 11, weight: .medium)
            pod.textColor = .systemRed
            pod.frame = NSRect(x: textX, y: 3, width: W - 69 - textX, height: 14)
            addSubview(pod)
            subtitleLabel = pod
        } else if let fixedSubtitle = fixedSubtitle {
            // Permanent informational subtitle, such as heavy process count; neutral color.
            let pod = NSTextField(labelWithString: fixedSubtitle)
            pod.font = .systemFont(ofSize: 11)
            pod.textColor = .secondaryLabelColor
            pod.frame = NSRect(x: textX, y: 3, width: W - 69 - textX, height: 14)
            addSubview(pod)
        }

        // Align the switch with the label center, not the whole row center. In a row
        // with a subtitle (H=44), the label sits high and a row-centered switch looked low.
        let sw = ToggleSwitch(on: on, target: self, action: #selector(switchChanged(_:)))
        sw.color = color
        sw.frame = NSRect(x: W - 62, y: H - 22.5, width: 38, height: 22)
        addSubview(sw)
        toggleSwitch = sw
        updateSubtitle(on: on)
    }
    required init?(coder: NSCoder) { fatalError() }

    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        toggleSwitch?.frame.origin.x = bounds.width - 62
        titleLabel?.frame.size.width = bounds.width - 69 - textX
        subtitleLabel?.frame.size.width = bounds.width - 69 - textX
    }

    private func updateSubtitle(on: Bool) {
        subtitleLabel?.stringValue = on ? "" : (offSubtitle ?? "")
    }

    @objc private func switchChanged(_ s: ToggleSwitch) {
        updateSubtitle(on: s.isOn)
        if let cel = externalTarget { NSApp.sendAction(externalAction, to: cel, from: self) }
    }
}


/// Generate a random, unguessable ntfy topic name.
/// The topic name is the only protection for ntfy alerts.
func randomTopic() -> String {
    let chars = Array("abcdefghjkmnpqrstuvwxyz23456789")
    let suffix = String((0..<10).map { _ in chars[Int(arc4random_uniform(UInt32(chars.count)))] })
    return "mac-guard-" + suffix
}

/// Render bar icons as SF Symbols, not emoji.
/// Emoji have fixed colors, vary in width across OS versions, and break text alignment.
/// Template symbols take the bar color and look native; if a symbol is unavailable on
/// this macOS version, fall back to a short text label.
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
    case chip, gpu, battery, fans, watts, ram, disk, throttle, paused, flame, awakeLeft, agent

    var label: String {
        switch self {
        case .chip: return T("Chip temperature")
        case .gpu: return T("GPU temperature")
        case .battery: return T("Battery temperature (from 40 °C)")
        case .fans: return T("Fan rpm (when spinning)")
        case .watts: return T("Power draw (W)")
        case .ram: return T("RAM used")
        case .disk: return T("Disk used")
        case .throttle: return T("Throttling marker")
        case .paused: return T("Pause marker")
        case .flame: return T("Flame at critical")
        case .awakeLeft: return T("Keep-awake time left")
        case .agent: return T("AI session marker")
        }
    }

    /// A fresh bar shows a small FIXED core (chip and RAM) plus CONDITIONAL
    /// elements that stay invisible until they carry news: fans only while they
    /// spin, battery only from 40 °C up (the cell-degradation line), an AI
    /// marker only while an agent session runs, throttle and pause markers only
    /// when active. Every MacBook Pro since 2021 has a notch and macOS silently
    /// drops a status item that does not fit (field report: 14-inch M1 Pro),
    /// so width is spent only when something happens - and a 60 s hysteresis
    /// keeps elements from flickering in and out at a boundary.
    var byDefault: Bool {
        switch self {
        case .chip, .ram, .fans, .battery, .agent,
             .throttle, .paused, .flame: return true
        case .gpu, .watts, .disk, .awakeLeft: return false
        }
    }
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
    /// Return whether everything is already shown, to disable "Show all".
    var allEnabled: Bool { Item.allCases.allSatisfy { enabled($0) } }
    /// Save the whole batch once; clicking item by item means N file writes and N refreshes.
    func enableAll() {
        for i in Item.allCases { on[i.rawValue] = true }
        save()
    }

    /// Nothing but the thermometer. The markers go too: this preset exists for a
    /// bar with no room left, and a marker that appears later would take the item
    /// back over the width that made it disappear in the first place.
    func enableNone() {
        for i in Item.allCases { on[i.rawValue] = false }
        save()
    }

    func enableChipOnly() {
        for i in Item.allCases { on[i.rawValue] = (i == .chip) }
        save()
    }

    var noneEnabled: Bool { Item.allCases.allSatisfy { !enabled($0) } }
    var onlyChipEnabled: Bool { Item.allCases.allSatisfy { enabled($0) == ($0 == .chip) } }
}

let prefs = Prefs()

// MARK: - guard configuration (thresholds live in config.json, the daemon re-reads it every cycle)

/// Read and write the guard's config.json.
/// Always merge with existing content; the daemon owns this file and keeps far more
/// settings there than the menu bar shows.
enum GuardCfg {
    /// Return nil when config cannot be read.
    /// This is not the same as an empty config: `set()` must then refuse to write,
    /// or one failed read deletes all 30 keys. Missing `dry_run` is read by the daemon
    /// as watch-only, so moving a slider would silently disable protection.
    static func read() -> [String: Any]? {
        guard let d = FileManager.default.contents(atPath: configPath) else {
            return FileManager.default.fileExists(atPath: configPath) ? nil : [:]
        }
        guard let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return nil }
        return j
    }

    /// Cache config while building ONE menu.
    /// Without it, one menu open performs ~17 full reads and parses of config.json,
    /// and even more with the fleet submenu open. It is invalidated explicitly in
    /// menuNeedsUpdate and after every write.
    private static var cache: [String: Any]?
    /// The cache is STATIC and touched from TWO threads: `menuNeedsUpdate` sets it on
    /// the main thread, while `refreshFleet` -> `fleetHosts()` -> `GuardCfg.string`
    /// reads it on a background thread (DispatchQueue.global). Swift dictionaries are
    /// not thread-safe; concurrent read/write is undefined behavior, from garbage values
    /// to a crashed menu bar. All access goes through this lock.
    private static let lock = NSLock()

    static func beginCache() {
        let fresh = read() ?? [:]
        lock.lock(); cache = fresh; lock.unlock()
    }

    static func endCache() { lock.lock(); cache = nil; lock.unlock() }

    static func all() -> [String: Any] {
        lock.lock()
        let current = cache
        lock.unlock()
        // Read from disk OUTSIDE the lock; I/O under lock would stall the main thread.
        return current ?? (read() ?? [:])
    }

    /// Read once per call, not twice.
    /// The menu asked for config ~25 times per open; half came from `double` reading
    /// the file twice.
    static func double(_ key: String, _ fallback: Double) -> Double {
        let c = all()
        if let d = c[key] as? Double { return d }
        if let i = c[key] as? Int { return Double(i) }
        return fallback
    }

    static func bool(_ key: String, _ fallback: Bool) -> Bool { (all()[key] as? Bool) ?? fallback }
    static func string(_ key: String, _ fallback: String) -> String { (all()[key] as? String) ?? fallback }

    static func set(_ values: [String: Any]) {
        // Same flock as the daemon (`config.lock`): read-modify-write from two
        // processes must not interleave, or the losing write disappears without a trace.
        let fd = open(base + "/config.lock", O_CREAT | O_WRONLY, 0o644)
        if fd >= 0 { flock(fd, LOCK_EX) }
        defer { if fd >= 0 { flock(fd, LOCK_UN); close(fd) } }
        guard var j = read() else {
            // Config exists but is unreadable. Writing would erase the rest of its keys,
            // so leave it untouched. A switch doing nothing is better than silently
            // disabling protection.
            NSLog("coffee-paladin: config.json nieczytelny - zapis wstrzymany")
            return
        }
        for (k, v) in values { j[k] = v }
        if let d = try? JSONSerialization.data(withJSONObject: j, options: [.prettyPrinted, .sortedKeys]) {
            // .atomic: the Python daemon shares this file; truncated write = DEFAULTS config.
            try? d.write(to: URL(fileURLWithPath: configPath), options: .atomic)
            cache = j                     // The write is source of truth until cycle end.
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

/// Record manual keep-awake requests in awake.json.
/// The daemon executes them via caffeinate with the overriding thermal fuse; one
/// instance decides.
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

/// Read hardware detected by the guard at startup from hardware.json.
func hardwareInfo() -> [String: Any] {
    guard let d = FileManager.default.contents(atPath: hwPath),
          let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return [:] }
    return j
}

/// Control login autostart by enabling or disabling both LaunchAgents.
/// `launchctl disable` does not kill a running instance; it only disables login startup,
/// exactly as the switch promises.
enum Autostart {
    static let services = ["pl.pawel.coffee-paladin", "pl.pawel.coffee-paladin-bar"]
    static func enabled() -> Bool {
        let out = shell(["/bin/launchctl", "print-disabled", "gui/\(getuid())"])
        // Missing entry = enabled; ANY disabled service means the switch is OFF.
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

/// Pick a warning for the slider value before the user commits it.
/// The common mistake is copying the battery threshold (45 C) to the chip: at 45 C the
/// guard would pause constantly because an idle chip already sits at 40-55 C.
/// The second tuple element is an SF Symbol name. No emoji: they have fixed colors and
/// look like stickers in menus, while template symbols take the text color.
/// What a given pause threshold means on a real machine. The numbers behind these
/// sentences come from a month of readings on one Mac with fans: ordinary heavy work
/// sits between 76 and 96, the CPU side of the reading saturates near 98 and the GPU
/// side near 103. The bands below 70 are gone because the slider no longer goes there.
func thresholdWarning(_ v: Double) -> (String, String) {
    if v < 78 { return (T("careful - under ordinary heavy work the chip already sits here, so long jobs will be paused often"), "lightbulb") }
    if v <= 92 { return (T("recommended - the pause comes well before the chip's own limiter"), "checkmark.circle") }
    if v <= 96 { return (T("late - a job will run hot for a while before anything happens"), "exclamationmark.triangle") }
    return (T("almost never - the reading rarely goes higher than this, so the pause may not come at all"), "exclamationmark.triangle")
}

/// Render a menu row with a slider.
/// NSMenuItem.view accepts arbitrary views, so the slider and its description live
/// directly in the menu, without a separate preferences window.
///
/// Keep the first-version fixes: description wraps instead of clipping, text stays
/// readable via labelColor, warning severity uses a symbol rather than color, and
/// derived values update WHILE dragging. Otherwise a slider at 65 C could still claim
/// "resume at 76 C" from the menu-open state.
final class SliderRow: NSView {
    let slider = NSSlider()
    private let value = NSTextField(labelWithString: "")
    private let note = NSTextField(labelWithString: "")
    private let derived = NSTextField(labelWithString: "")
    private let onChange: (Double) -> Void
    private let unit: String
    private let describe: (Double) -> (String, String)
    private let derive: ((Double) -> String)?

    init(title: String, min: Double, max: Double, current: Double, unit: String, step: Double = 5,
         describe: @escaping (Double) -> (String, String),
         derive: ((Double) -> String)? = nil,
         onChange: @escaping (Double) -> Void) {
        self.onChange = onChange
        self.unit = unit
        self.describe = describe
        self.derive = derive
        let height: CGFloat = derive == nil ? 82 : 100
        super.init(frame: NSRect(x: 0, y: 0, width: 400, height: height))
        // This was the only menu view that did not follow menu width: in wider submenus,
        // sliders clung to the left edge with dead space on the right.
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
        // Ticks follow the step the caller asked for. Hardcoding 5 meant a range of
        // 70 to 98 got six ticks 5.6 degrees apart, so the number under the slider
        // could never be the one the user aimed at.
        slider.numberOfTickMarks = Int((max - min) / Swift.max(step, 1)) + 1
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

/// Accept both 90 and 90.0 from Python JSON.
func num(_ v: Any?) -> Double? {
    if let d = v as? Double { return d }
    if let i = v as? Int { return Double(i) }
    return (v as? NSNumber)?.doubleValue
}

func numInt(_ v: Any?) -> Int? { num(v).map { Int($0) } }

struct Job { let name: String; let minutes: Int }
struct TopCPU { let name: String; let cpu: Int }
struct TopRAM { let name: String; let gb: Double }

struct FreezeCandidate {
    let pid: Int
    let name: String
    let cpu: Int
}

struct Snap {
    var chip: Double?, gpu: Double?, batt: Double?, watts: Double?
    /// The daemon remembered this chip value instead of measuring it (its sensor did not
    /// answer). Shown with a qualifier, and never used to accuse the fans.
    var chipStale = false
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
    /// List exactly what will receive SIGSTOP during manual freeze.
    /// The daemon publishes this because only it knows the never-touch lists. Previously
    /// the menu showed top CPU here, including WindowServer and AI agents the guard
    /// would never touch.
    var freezeCandidates: [FreezeCandidate] = []
    var heavyCount: Int = 0
    var topRamList: [TopRAM] = []
    var pausesToday = 0, killsToday = 0
    var statsTotal: [String: Int] = [:]   // lifetime total; survives daemon restarts
    var statsSession: [String: Int] = [:] // since the current daemon session started
    var lastCrash: String?
    var thrPause: Double?, thrResume: Double?, thrKill: Double?
    var stamp = ""
    var stale = true
}

func readSnap() -> Snap? {
    guard let data = FileManager.default.contents(atPath: statusPath),
          let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
    var s = Snap()
    s.chip = num(j["chip_c"])
    s.chipStale = (j["chip_stale"] as? Bool) ?? false
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
                return FreezeCandidate(pid: pid, name: ($0["name"] as? String) ?? "?",
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
    // NSNumber, not `as? Int`: "since" is a fractional epoch from Python's time.time()
    // and a plain Int cast drops it, which showed up as "total since ?" in the menu.
    if let t = j["stats_total"] as? [String: Any] {
        for (k, v) in t { if let n = v as? NSNumber { s.statsTotal[k] = n.intValue } }
    }
    if let t = j["stats_session"] as? [String: Any] {
        for (k, v) in t { if let n = v as? NSNumber { s.statsSession[k] = n.intValue } }
    }
    if let p = j["last_hard_shutdown"] as? [String: Any] { s.lastCrash = p["time"] as? String }
    if let t = j["thresholds"] as? [String: Any] {
        s.thrPause = num(t["pause"])
        s.thrResume = num(t["resume"])
        s.thrKill = num(t["kill"])
    }
    if let m = try? FileManager.default.attributesOfItem(atPath: statusPath)[.modificationDate] as? Date {
        s.stale = Date().timeIntervalSince(m) > 90
    }
    return s
}

/// Draw the chip temperature chart from history.csv.
/// Bars are colored by thresholds (green/yellow/red), with a pause-threshold line,
/// pause markers (level >= 2), and min/max labels at the edges instead of unscaled
/// black text bars. Draw once when the menu opens, with no timers; the chart must not
/// heat the Mac it protects.
final class ChartRow: NSView {
    private let values: [Double]
    private let pauseMarkers: [Bool]
    private let times: [String]
    private let processes: [String]
    private let pauseThreshold: Double
    private let resumeThreshold: Double
    /// Bar under the cursor; nil means the mouse is outside the chart.
    private var hoveredIndex: Int?
    private var trackingArea: NSTrackingArea?

    static func make() -> ChartRow? {
        guard let text = try? String(contentsOfFile: historyPath, encoding: .utf8) else { return nil }
        var vals: [Double] = []
        var pauseMarkers: [Bool] = []
        var times: [String] = []
        var processes: [String] = []
        for line in text.split(separator: "\n").suffix(61) {
            let c = line.split(separator: ",", omittingEmptySubsequences: false)
            if c.count > 11, let v = Double(c[2]) {
                vals.append(v)
                pauseMarkers.append((Int(c[11]) ?? 0) >= 2)
                // "YYYY-MM-DD HH:MM:SS" -> "HH:MM" for time-axis labels under the chart.
                let t = String(c[0])
                times.append(t.count >= 16 ? String(t.dropFirst(11).prefix(5)) : "")
                // Heaviest process at that moment, for the hover callout.
                let processName = c.count > 12 ? String(c[12]).trimmingCharacters(in: .whitespaces) : ""
                let cpu = c.count > 13 ? String(c[13]).trimmingCharacters(in: .whitespaces) : ""
                processes.append(processName.isEmpty ? "" : (cpu.isEmpty ? processName : "\(processName) \(cpu)%"))
            }
        }
        guard vals.count >= 3 else { return nil }
        return ChartRow(vals, pauseMarkers, times, processes)
    }

    init(_ v: [Double], _ p: [Bool], _ t: [String], _ pr: [String]) {
        values = v
        pauseMarkers = p
        times = t
        processes = pr
        pauseThreshold = GuardCfg.double("soc_pause_c", 90)
        resumeThreshold = GuardCfg.double("soc_resume_c", 82)
        // +12 pt for the time axis under the bars.
        super.init(frame: NSRect(x: 0, y: 0, width: 400, height: 76))
        autoresizingMask = [.width]
    }
    required init?(coder: NSCoder) { fatalError() }

    // Track the mouse over the chart. No timer; redraw only when the cursor really
    // changes the selected bar.
    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let o = trackingArea { removeTrackingArea(o) }
        let o = NSTrackingArea(rect: bounds,
                               options: [.mouseEnteredAndExited, .mouseMoved, .activeAlways, .inVisibleRect],
                               owner: self, userInfo: nil)
        addTrackingArea(o)
        trackingArea = o
    }

    override func mouseMoved(with event: NSEvent) {
        let p = convert(event.locationInWindow, from: nil)
        let left: CGFloat = 44, right: CGFloat = 16
        let W = bounds.width - left - right
        guard W > 0, !values.isEmpty else { return }
        let step = W / CGFloat(values.count)
        let i = Int((p.x - left) / step)
        let newIndex = (p.x >= left && i >= 0 && i < values.count) ? i : nil
        if newIndex != hoveredIndex { hoveredIndex = newIndex; needsDisplay = true }
    }

    override func mouseExited(with event: NSEvent) {
        if hoveredIndex != nil { hoveredIndex = nil; needsDisplay = true }
    }

    override func draw(_ dirtyRect: NSRect) {
        let left: CGFloat = 44, right: CGFloat = 16, bottom: CGFloat = 18, topInset: CGFloat = 8
        let W = bounds.width - left - right, H = bounds.height - bottom - topInset
        guard W > 40, H > 20, !values.isEmpty else { return }
        let lo = values.min()!, hi = values.max()!
        // Include the pause threshold in the scale only when the machine runs near it;
        // otherwise cold readings compress into a flat line at the bottom.
        let top = hi >= pauseThreshold - 15 ? Swift.max(hi, pauseThreshold) : hi
        let span = Swift.max(top - lo, 1.0)
        func y(_ v: Double) -> CGFloat { bottom + CGFloat((v - lo) / span) * H }

        let n = values.count
        let step = W / CGFloat(n)
        let barWidth = Swift.max(step - 1.5, 1.0)
        for (i, v) in values.enumerated() {
            let color: NSColor = v >= pauseThreshold ? .systemRed
                               : v > resumeThreshold ? .systemYellow : .systemGreen
            color.withAlphaComponent(0.85).setFill()
            let x = left + CGFloat(i) * step
            NSBezierPath(roundedRect:
                NSRect(x: x, y: bottom, width: barWidth, height: Swift.max(y(v) - bottom, 1.5)),
                xRadius: 0.5, yRadius: 0.5).fill()
            if pauseMarkers[i] {
                // Pause marker: red dot ABOVE the bar, a guard intervention.
                NSColor.systemRed.setFill()
                NSBezierPath(ovalIn: NSRect(x: x + barWidth / 2 - 1.5,
                                            y: bounds.height - 6, width: 3, height: 3)).fill()
            }
        }

        // Hovered bar: outline it so the selected reading is clear.
        if let k = hoveredIndex, values.indices.contains(k) {
            let x = left + CGFloat(k) * step
            NSColor.labelColor.withAlphaComponent(0.55).setStroke()
            let outline = NSBezierPath(rect: NSRect(x: x - 0.5, y: bottom - 0.5,
                                                  width: barWidth + 1,
                                                  height: Swift.max(y(values[k]) - bottom, 1.5) + 1))
            outline.lineWidth = 1
            outline.stroke()
        }

        // Pause-threshold line (dashed), if it fits the scale.
        if pauseThreshold >= lo && pauseThreshold <= top {
            let yp = y(pauseThreshold)
            let path = NSBezierPath()
            path.move(to: NSPoint(x: left, y: yp))
            path.line(to: NSPoint(x: left + W, y: yp))
            path.setLineDash([3, 3], count: 2, phase: 0)
            path.lineWidth = 1
            NSColor.systemRed.withAlphaComponent(0.6).setStroke()
            path.stroke()
        }

        // Scale labels at edges: max at top, min at bottom instead of an extra row below.
        let atr: [NSAttributedString.Key: Any] = [
            .font: NSFont.monospacedDigitSystemFont(ofSize: 9, weight: .regular),
            .foregroundColor: NSColor.secondaryLabelColor]
        String(format: "%.0f°", top).draw(at: NSPoint(x: 14, y: bounds.height - topInset - 8),
                                          withAttributes: atr)
        String(format: "%.0f°", lo).draw(at: NSPoint(x: 14, y: bottom - 1), withAttributes: atr)

        // Hover callout: reading time, temperature, and heaviest process. Draw it in
        // the view, not NSToolTip; menu tooltips appear late and get lost during mouse
        // movement.
        if let k = hoveredIndex, values.indices.contains(k) {
            var description = times.indices.contains(k) && !times[k].isEmpty ? times[k] + "   " : ""
            description += String(format: "%.1f°C", values[k])
            if processes.indices.contains(k), !processes[k].isEmpty { description += "   " + processes[k] }
            let atrP: [NSAttributedString.Key: Any] = [
                .font: NSFont.monospacedDigitSystemFont(ofSize: 9, weight: .medium),
                .foregroundColor: NSColor.labelColor]
            let size = (description as NSString).size(withAttributes: atrP)
            // Keep the callout within the chart so it does not escape the menu.
            let centerX = left + CGFloat(k) * step + barWidth / 2
            let x = Swift.min(Swift.max(centerX - size.width / 2, left),
                              left + W - size.width)
            let yT = bounds.height - size.height - 1
            NSColor.windowBackgroundColor.withAlphaComponent(0.92).setFill()
            NSBezierPath(roundedRect: NSRect(x: x - 4, y: yT - 2,
                                             width: size.width + 8, height: size.height + 3),
                         xRadius: 3, yRadius: 3).fill()
            (description as NSString).draw(at: NSPoint(x: x, y: yT), withAttributes: atrP)
        }

        // Time axis: start, middle, and end of measurement range (HH:MM from history.csv).
        if hoveredIndex == nil,
           let first = times.first(where: { !$0.isEmpty }),
           let last = times.last(where: { !$0.isEmpty }) {
            first.draw(at: NSPoint(x: left, y: 2), withAttributes: atr)
            let lastWidth = (last as NSString).size(withAttributes: atr).width
            last.draw(at: NSPoint(x: left + W - lastWidth, y: 2), withAttributes: atr)
            let i = times.count / 2
            if times.indices.contains(i), !times[i].isEmpty, times.count > 6 {
                let middleWidth = (times[i] as NSString).size(withAttributes: atr).width
                times[i].draw(at: NSPoint(x: left + W / 2 - middleWidth / 2, y: 2), withAttributes: atr)
            }
        }
    }
}

/// Format minutes as "1 h 23 min" for the keep-awake time remaining row.
func fmtDur(_ minutes: Int) -> String {
    if minutes >= 60 {
        let h = minutes / 60, m = minutes % 60
        return m == 0 ? String(format: T("%d h"), h)
                      : String(format: T("%d h"), h) + " " + String(format: T("%d min"), m)
    }
    return String(format: T("%d min"), max(minutes, 1))
}

/// Render the language row on the main menu card.
/// Five buttons replace a submenu buried in Settings. A click writes `lang` to
/// config.json and restarts the bar; launchd brings it back because
/// KeepAlive.SuccessfulExit=false.
final class LangRow: NSView {
    private let codes = ["en", "pl", "ru", "zh", "es"]
    private let labels = ["EN", "PL", "RU", "中文", "ES"]

    private var buttons: [NSButton] = []

    init() {
        super.init(frame: NSRect(x: 0, y: 0, width: 400, height: 30))
        // The menu can be WIDER than the base width when long text rows stretch it.
        // NSMenu stretches item views to the full width, so compute the center from
        // bounds in layout(), not from the fixed 400, or the row hangs on the left.
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
            buttons.append(b)
        }
        layoutContent()
    }

    required init?(coder: NSCoder) { fatalError() }

    // setFrameSize, not layout(): NSMenu stretches item views by changing the frame,
    // and layout() without a layer may not run at all.
    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        layoutContent()
    }

    private func layoutContent() {
        let w: CGFloat = 66, gap: CGFloat = 6
        var x: CGFloat = (bounds.width - (CGFloat(buttons.count) * w
                                          + CGFloat(buttons.count - 1) * gap)) / 2
        for b in buttons {
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
    /// Menu-facing cache of the live rows. The tail read and JSON parse run on
    /// a background queue; the menu only ever reads the last snapshot, so a
    /// slow disk cannot stall menuNeedsUpdate (same discipline as the fleet).
    private var liveRowsCache: [String] = []
    private var liveRowsBusy = false

    func recorderLiveCached() -> [String] {
        if !liveRowsBusy {
            liveRowsBusy = true
            DispatchQueue.global(qos: .utility).async { [weak self] in
                let rows = self?.recorderLiveRows() ?? []
                DispatchQueue.main.async {
                    self?.liveRowsCache = rows
                    self?.liveRowsBusy = false
                }
            }
        }
        return liveRowsCache
    }

    /// Freshest recorder event per session, "project · tool · Ns ago" rows.
    func recorderLiveRows() -> [String] {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"
        let path = agentEventsDir + "/" + fmt.string(from: Date()) + ".jsonl"
        guard let handle = FileHandle(forReadingAtPath: path) else { return [] }
        defer { try? handle.close() }
        let size = (try? handle.seekToEnd()) ?? 0
        let want: UInt64 = 64 * 1024
        try? handle.seek(toOffset: size > want ? size - want : 0)
        guard let data = try? handle.readToEnd(),
              let text = String(data: data, encoding: .utf8) else { return [] }
        var freshest: [String: (Double, String, String)] = [:]   // sid -> (epoch, tool, project)
        for line in text.split(separator: "\n") {
            guard let d = line.data(using: .utf8),
                  let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
                  let sid = j["session_id"] as? String,
                  let epoch = j["epoch"] as? Double else { continue }
            let tool = (j["tool_name"] as? String) ?? (j["hook_event_name"] as? String) ?? "?"
            let project = (j["project"] as? String) ?? "?"
            if epoch > (freshest[sid]?.0 ?? 0) { freshest[sid] = (epoch, tool, project) }
        }
        let now = Date().timeIntervalSince1970
        return freshest.values
            .filter { now - $0.0 < 120 }
            .sorted { $0.0 > $1.0 }
            .map { String(format: "%@ · %@ · %.0f s", $0.2, $0.1, now - $0.0) }
    }

    /// Account limits of the active Claude Code session, read from the cache
    /// the paladin statusline writes on every render (whitelisted fields only,
    /// no session ids or paths). The bar never queries anything: no statusline
    /// running = no fresh file = the row simply does not exist.
    func claudeUsageText() -> String? {
        guard let d = FileManager.default.contents(atPath: base + "/claude_usage_cache.json"),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
              let epoch = (j["epoch"] as? NSNumber)?.doubleValue else { return nil }
        // Statuslines refresh every 15 s while a session is open; five minutes
        // of silence means the session is gone and the numbers are history.
        if Date().timeIntervalSince1970 - epoch > 300 { return nil }
        var bits: [String] = []
        if let m = j["model"] as? String, !m.isEmpty { bits.append(m) }
        // Spelled out rather than compressed. The bar is not the statusline: it has room,
        // and "5h 16% ↺13:30" asks the reader to decode three symbols to learn one fact.
        func window(_ key: String, _ label: String, _ resetKey: String) {
            guard let p = (j[key] as? NSNumber)?.intValue else { return }
            let reset = (j[resetKey] as? String) ?? ""
            bits.append(String(format: T("%@: %d%%"), label, p)
                        + (reset.isEmpty ? "" : " " + String(format: T("(resets %@)"), reset)))
        }
        window("five_hour_pct", T("5h limit"), "five_hour_reset")
        // The weekly reset day is formatted HERE, from the epoch, in the
        // BAR's language: the statusline wrote its text in the session's
        // language, and "Wed" inside a Polish menu is a localization bug.
        if let p = (j["seven_day_pct"] as? NSNumber)?.intValue {
            var reset = (j["seven_day_reset"] as? String) ?? ""
            if let epoch = (j["seven_day_reset_epoch"] as? NSNumber)?.doubleValue, epoch > 0 {
                let f = DateFormatter()
                f.locale = Locale(identifier: ["en": "en_US", "pl": "pl_PL", "ru": "ru_RU",
                                               "zh": "zh_CN", "es": "es_ES"][lang] ?? "en_US")
                f.setLocalizedDateFormatFromTemplate("EEE")
                reset = f.string(from: Date(timeIntervalSince1970: epoch))
            }
            bits.append(String(format: T("%@: %d%%"), T("7d limit"), p)
                        + (reset.isEmpty ? "" : " " + String(format: T("(resets %@)"), reset)))
        }
        if let c = (j["context_pct"] as? NSNumber)?.intValue {
            bits.append(String(format: T("%@: %d%%"), T("context"), c))
        }
        guard bits.count > 1 else { return nil }
        return String(format: T("Claude limits: %@"), bits.joined(separator: " · "))
    }

    /// Cached "cost today" from the external `ccusage` CLI. The cache file is
    /// the contract: the menu NEVER waits for the tool, it shows what the last
    /// background refresh wrote (10 min TTL) or nothing at all.
    func ccusageTodayText() -> String? {
        guard let d = FileManager.default.contents(atPath: ccusageCachePath),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
              let epoch = j["epoch"] as? Double else { return nil }
        // Tokens lead, money follows. On a subscription the dollar figure is not money
        // anyone spent - it is what the same work would have cost through the API - so
        // presenting it as THE number of the day misreads the bill for most users.
        var parts: [String] = []
        if let tok = num(j["tokens"]), tok > 0, let t = tokenText(tok) {
            parts.append(String(format: T("%@ tokens"), t))
        }
        if GuardCfg.bool("ccusage_cost", true), let c = num(j["cost"]), c > 0 {
            parts.append(String(format: "~$%.2f", c))
        }
        let text = parts.joined(separator: " · ")
        if text.isEmpty { return nil }
        // "Today" must mean today: a stale cache from a removed ccusage would
        // otherwise present yesterday's cost as current, forever.
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyyMMdd"
        if (j["day"] as? String) != fmt.string(from: Date()) { return nil }
        if Date().timeIntervalSince1970 - epoch > 600 { return nil }
        return String(format: T("Agents today: %@ (ccusage)"), text)
    }

    /// Rows for the expanded breakdown: per agent, then per model, then the active block.
    /// Everything here is display-only text built from the cache the background refresh
    /// wrote; the menu never waits for the tool.
    func ccusageDetailRows(etaPauseMin: Double?) -> [(String, String)] {
        guard let d = FileManager.default.contents(atPath: ccusageCachePath),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
              let epoch = j["epoch"] as? Double,
              Date().timeIntervalSince1970 - epoch <= 600 else { return [] }
        let showCost = GuardCfg.bool("ccusage_cost", true)
        func line(_ e: [String: Any]) -> String? {
            guard let name = e["name"] as? String,
                  let tok = num(e["tokens"]), tok > 0,
                  let t0 = tokenText(tok) else { return nil }
            var t = String(format: T("%@ tokens"), t0)
            if showCost, let c = num(e["cost"]), c > 0 { t += String(format: " · ~$%.2f", c) }
            return modelLabel(name) + "   " + t
        }
        var rows: [(String, String)] = []
        // Heading first, rows second was backwards: a section whose entries all fail the
        // filter left a title standing over nothing.
        func section(_ title: String, _ entries: [[String: Any]], icon: String) {
            let lines = entries.prefix(6).compactMap(line)
            guard !lines.isEmpty else { return }
            rows.append(("", title))
            for l in lines { rows.append((icon, l)) }
        }
        section(T("Per agent"), (j["agents"] as? [[String: Any]]) ?? [], icon: "terminal")
        section(T("Per model"), (j["models"] as? [[String: Any]]) ?? [], icon: "cpu")
        if let b = j["block"] as? [String: Any], let tok = num(b["tokens"]), tok > 0,
           let tokTxt = tokenText(tok),
           let endEpoch = num(b["endEpoch"]),
           case let left = (endEpoch - Date().timeIntervalSince1970) / 60.0, left > 0 {
            rows.append(("", T("Active block (counted by ccusage, not your account limit)")))
            // The rate is optional: a block one minute old has no meaningful pace, and an
            // invented one would be worse than a shorter row.
            if let perMin = num(b["perMinute"]), let rate = tokenText(perMin) {
                rows.append(("clock", String(format: T("%@ tokens · %@/min · %.0f min left"),
                                             tokTxt, rate, left)))
            } else {
                rows.append(("clock", String(format: T("%@ tokens · %.0f min left"), tokTxt, left)))
            }
            // The one thing no usage dashboard can say: this machine may stop the work
            // before the block runs out. Only claimed when the guard itself forecasts it.
            if let eta = etaPauseMin, eta > 0, left > 0, eta < left {
                rows.append(("exclamationmark.triangle",
                             String(format: T("at this rate the guard pauses in ~%.0f min, before the block ends"), eta)))
            }
        }
        return rows
    }

    // Touched from the main thread only; the background task hands completion
    // back to main, so the flag needs no lock.
    private static var ccusageRefreshing = false

    func refreshCcusageCache() {
        if let d = FileManager.default.contents(atPath: ccusageCachePath),
           let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
           let epoch = j["epoch"] as? Double,
           Date().timeIntervalSince1970 - epoch < 600 { return }
        if Bar.ccusageRefreshing { return }
        Bar.ccusageRefreshing = true
        DispatchQueue.global(qos: .utility).async {
            defer { DispatchQueue.main.async { Bar.ccusageRefreshing = false } }
            let home = NSHomeDirectory()
            let candidates = ["/opt/homebrew/bin/ccusage", "/usr/local/bin/ccusage",
                              home + "/.local/bin/ccusage", home + "/.bun/bin/ccusage",
                              home + "/.npm-global/bin/ccusage"]
            guard let bin = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0) })
            else { return }                       // no ccusage = the row simply does not exist
            // Two calls, one refresh: the daily totals (~1.5 s) and the active block
            // (~0.4 s). Both land in the same cache file, both are best-effort.
            let blockInfo = self.readActiveBlock(bin: bin, home: home)
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: bin)
            // npm/bun shims start with `env node`; a LaunchAgent's inherited
            // environment may lack the runtime. Hand the child an explicit PATH.
            var env = ProcessInfo.processInfo.environment
            env["PATH"] = ["/opt/homebrew/bin", "/usr/local/bin",
                           home + "/.local/bin", home + "/.bun/bin",
                           home + "/.npm-global/bin",
                           "/usr/bin", "/bin", "/usr/sbin", "/sbin"].joined(separator: ":")
            proc.environment = env
            let fmt = DateFormatter()
            fmt.dateFormat = "yyyyMMdd"
            proc.arguments = ["daily", "--json", "--by-agent", "--since", fmt.string(from: Date())]
            let pipe = Pipe()
            proc.standardOutput = pipe
            proc.standardError = FileHandle.nullDevice
            guard (try? proc.run()) != nil else { return }
            DispatchQueue.global().asyncAfter(deadline: .now() + 5) {
                if proc.isRunning { proc.terminate() }
            }
            proc.waitUntilExit()
            let out = pipe.fileHandleForReading.readDataToEndOfFile()
            guard proc.terminationStatus == 0,
                  let j = try? JSONSerialization.jsonObject(with: out) else { return }
            // Defensive: find the first plausible total without pinning the
            // exact schema of an external tool.
            // Prefer the documented totals before any recursive guessing.
            if let top = j as? [String: Any],
               let totals = top["totals"] as? [String: Any],
               let known = totals["totalCost"] as? Double {
                // The breakdown is best-effort: totals alone still produce a useful row,
                // so a schema change in the per-agent part must not cost us the headline.
                var agents: [[String: Any]] = []
                var models: [[String: Any]] = []
                if let days = top["daily"] as? [[String: Any]], let day = days.first {
                    func entries(_ raw: Any?, nameKey: String) -> [[String: Any]] {
                        guard let list = raw as? [[String: Any]] else { return [] }
                        return list.compactMap { e in
                            guard let n = e[nameKey] as? String else { return nil }
                            // A missing set of token fields is not "zero tokens": summing
                            // absent keys used to manufacture a 0 that looked measured.
                            let parts = ["inputTokens", "outputTokens",
                                         "cacheCreationTokens", "cacheReadTokens"]
                                .compactMap { num(e[$0]) }
                            guard let tok = num(e["totalTokens"])
                                    ?? (parts.isEmpty ? nil : parts.reduce(0, +)) else { return nil }
                            let c = num(e["totalCost"]) ?? num(e["cost"]) ?? 0
                            return ["name": n, "tokens": tok, "cost": c]
                        }
                    }
                    agents = entries(day["agents"], nameKey: "agent")
                    models = entries(day["modelBreakdowns"], nameKey: "modelName")
                }
                self.writeCcusageCache(cost: known, tokens: num(totals["totalTokens"]),
                                       agents: agents, models: models, block: blockInfo)
                return
            }
            func findCost(_ any: Any) -> Double? {
                if let dict = any as? [String: Any] {
                    for key in ["totalCost", "total_cost", "costUSD", "cost"] {
                        if let v = dict[key] as? Double { return v }
                    }
                    for v in dict.values { if let c = findCost(v) { return c } }
                }
                if let arr = any as? [Any] {
                    var sum = 0.0
                    var found = false
                    for v in arr { if let c = findCost(v) { sum += c; found = true } }
                    return found ? sum : nil
                }
                return nil
            }
            guard let cost = findCost(j) else { return }
            self.writeCcusageCache(cost: cost, tokens: nil, agents: [], models: [],
                                   block: blockInfo)
        }
    }

    /// Format a token count the way people say it: 322M, 1.2B, 45k.
    private func tokenText(_ n: Double) -> String? {
        // A corrupt cache or a schema change must produce NO row, not "nanM" or "-2k".
        guard n.isFinite, n >= 0 else { return nil }
        if n >= 1e9 { return String(format: "%.1fB", n / 1e9) }
        if n >= 1e6 { return String(format: "%.0fM", n / 1e6) }
        if n >= 1e3 { return String(format: "%.0fk", n / 1e3) }
        return String(format: "%.0f", n)
    }

    /// Model identifiers are display labels. On Bedrock and similar providers the raw name
    /// can be a full ARN carrying an account id, and this text ends up in screenshots.
    private func modelLabel(_ raw: String) -> String {
        let tail = raw.split(whereSeparator: { $0 == "/" }).last.map(String.init) ?? raw
        let short = tail.split(separator: ":").first.map(String.init) ?? tail
        return short.count > 40 ? String(short.prefix(39)) + "…" : short
    }

    /// The ACTIVE five-hour block as ccusage counts it from local logs. This is NOT the
    /// account's official 5h limit - that one comes from Claude Code's session JSON and
    /// lives on its own row. Two different numbers, and the UI must never merge them.
    private func readActiveBlock(bin: String, home: String) -> [String: Any] {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: bin)
        proc.arguments = ["blocks", "--active", "--json"]
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = ["/opt/homebrew/bin", "/usr/local/bin", home + "/.local/bin",
                       home + "/.bun/bin", home + "/.npm-global/bin",
                       "/usr/bin", "/bin", "/usr/sbin", "/sbin"].joined(separator: ":")
        proc.environment = env
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = FileHandle.nullDevice
        guard (try? proc.run()) != nil else { return [:] }
        DispatchQueue.global().asyncAfter(deadline: .now() + 5) {
            if proc.isRunning { proc.terminate() }
        }
        proc.waitUntilExit()
        let out = pipe.fileHandleForReading.readDataToEndOfFile()
        guard proc.terminationStatus == 0,
              let j = try? JSONSerialization.jsonObject(with: out) as? [String: Any],
              let blocks = j["blocks"] as? [[String: Any]],
              let b = blocks.first(where: { ($0["isActive"] as? Bool) == true })
        else { return [:] }
        let projection = b["projection"] as? [String: Any] ?? [:]
        var info: [String: Any] = [:]
        let tokens = num(b["totalTokens"]) ?? 0
        info["tokens"] = tokens
        // The rate is computed from the SAME tokens the row shows, over the time the block
        // has been running. ccusage exports two burn-rate fields whose values differ by
        // three orders of magnitude (tokensPerMinute counts cache reads, the indicator
        // variant does not); picking either would make the row disagree with its own
        // total. Elapsed comes from the block's own start and end, not a wall clock.
        var elapsed = 0.0
        let iso = ISO8601DateFormatter()
        // ccusage stamps milliseconds ("...T09:00:00.000Z"), which the default option set
        // refuses. Without this the rate was silently never computed - the row rendered
        // fine, just permanently without its most useful number.
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let plain = ISO8601DateFormatter()
        func parse(_ v: Any?) -> Date? {
            guard let str = v as? String else { return nil }
            return iso.date(from: str) ?? plain.date(from: str)
        }
        let end = parse(b["endTime"])
        if let st = parse(b["startTime"]) {
            elapsed = Date().timeIntervalSince(st) / 60.0
        } else if let et = end {
            elapsed = 300.0 - (et.timeIntervalSince(Date()) / 60.0)
        }
        if elapsed >= 1, tokens > 0 { info["perMinute"] = tokens / elapsed }
        // Store WHEN the block ends, never how many minutes are left. A countdown written
        // into a 10-minute cache is wrong the moment it is written: it kept counting from
        // the refresh, so the menu could show minutes that had already passed and, at the
        // end of a block, present a finished one as active. A timestamp cannot go stale.
        if let et = end {
            info["endEpoch"] = et.timeIntervalSince1970
        } else if let r = num(projection["remainingMinutes"]) {
            info["endEpoch"] = Date().timeIntervalSince1970 + r * 60
        }
        // Models are display-only labels, capped: the point is "what dominates the block",
        // not a full inventory.
        info["models"] = ((b["models"] as? [String]) ?? []).prefix(3).map { $0 }
        return info
    }

    private func writeCcusageCache(cost: Double, tokens: Double?,
                                   agents: [[String: Any]], models: [[String: Any]],
                                   block: [String: Any]) {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyyMMdd"
        // The cache holds NUMBERS, not a finished sentence. Storing the rendered text
        // meant `ccusage_cost: false` did nothing until the 10-minute TTL expired: the
        // config decides how the row reads, so the config has to be read when it is drawn.
        let cache: [String: Any] = ["epoch": Date().timeIntervalSince1970,
                                    "day": fmt.string(from: Date()),
                                    "cost": cost, "tokens": tokens ?? 0,
                                    "agents": agents, "models": models, "block": block]
        if let data = try? JSONSerialization.data(withJSONObject: cache) {
            try? data.write(to: URL(fileURLWithPath: ccusageCachePath), options: .atomic)
        }
    }

    /// Keep the single menu bar instance.
    /// The paladin panel needs it to know which icon to anchor under.
    static weak var shared: Bar?
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    let menu = NSMenu()
    var timer: Timer?
    // Fleet cache: I/O over the shared folder (iCloud/SMB) must NOT run on the main
    // thread while opening the menu. A network hiccup would block the whole menu.
    var fleetCache: [FleetHost]?
    var fleetCacheAt = Date.distantPast
    private var tick = 0
    /// Run one-shot refreshes after human actions.
    /// The fixed timer runs every 5 s and should stay that way; at idle it costs almost
    /// nothing. After a click, 5 s is forever: the daemon reacts in ~0.4 s and the bar
    /// used to show stale state.
    private var postActionTimers: [Timer] = []
    /// Track the watch-only state the human JUST requested before the daemon confirms it.
    /// `nil` means no pending expectation.
    private var expectedDryRun: Bool?
    private var expectedDryRunSince = Date.distantPast
    /// Prevent the guide from returning every 5 s when the signal file cannot be removed.
    private var shownGuideFromSignal = false
    private var shownWindowFromStuckSignal = false
    /// Exist only while the manual-freeze confirmation window is open.
    private var allCheckbox: NSButton?
    private var processCheckboxes: [NSButton] = []

    override init() {
        super.init()
        Bar.shared = self
        // macOS normally disables menu items without actions; most rows here are
        // information, not commands. Without this flag the whole readout was gray
        // and unreadable.
        menu.autoenablesItems = false
        menu.delegate = self
        item.menu = menu
        refresh()
        refreshFleet()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { Welcome.shared.maybeShow() }
        // .common, not .default: in .default the timer does NOT tick while the menu is
        // open or a modal window is shown (report, ntfy, fleet name). The bar readout
        // froze along with animations and the signal-file dispatcher, exactly when a
        // human is looking at the temperature.
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in
            guard let self = self else { return }
            self.handleSignals()
            self.refresh()
            self.tick += 1
            if self.tick % 6 == 0 { self.refreshFleet() }   // fleet every ~30 s, in background
            // ccusage every ~60 s (its own 10 min TTL decides when the tool actually runs).
            // Refreshing ONLY while building the menu meant the cost row appeared on the
            // SECOND opening at the earliest: the first opening started the background
            // refresh and drew a menu that did not have the answer yet. Someone who had
            // just installed ccusage saw nothing and concluded the integration was missing.
            if self.tick % 12 == 1 { self.refreshCcusageCache() }
        }
        if let t = timer { RunLoop.main.add(t, forMode: .common) }
    }

    /// Handle signal files: `touch ~/.coffee-paladin/show_guide` or
    /// `echo ntfy > ~/.coffee-paladin/show_window` (guide|ntfy|fleetname|observe).
    /// They open windows remotely for screenshots and support.
    ///
    /// This MUST be a separate method. The dispatcher used to live inside the timer
    /// closure, where `return` on an empty file returned from the WHOLE tick and skipped
    /// refresh(). An empty signal file stopped bar refresh for 30 s; a file with future
    /// mtime (clock skew, Time Machine restore, iCloud file from a machine with a fast
    /// clock) stopped it forever.
    func handleSignals() {
        let fm = FileManager.default
        let guideSignal = base + "/show_guide"
        if fm.fileExists(atPath: guideSignal) {
            // If the file cannot be removed (read-only directory, uchg flag), the window
            // would return every 5 s and make work impossible. Show it once.
            let removed = (try? fm.removeItem(atPath: guideSignal)) != nil
            if removed || !shownGuideFromSignal {
                shownGuideFromSignal = true
                Guide.shared.show()
            }
        } else {
            shownGuideFromSignal = false
        }

        let windowSignal = base + "/show_window"
        guard let contents = try? String(contentsOfFile: windowSignal, encoding: .utf8) else { return }
        let body = contents.trimmingCharacters(in: .whitespacesAndNewlines)
        // `echo ntfy > file` first truncates the file to zero, then writes content.
        // If the timer hits that window it reads an empty string and used to open Guide
        // instead of ntfy. Leave an empty file for the next cycle; if it is still empty
        // after 30 s, clean it up. abs(), because future mtime counts too.
        if body.isEmpty {
            if let a = try? fm.attributesOfItem(atPath: windowSignal),
               let m = a[.modificationDate] as? Date,
               abs(Date().timeIntervalSince(m)) > 30 {
                try? fm.removeItem(atPath: windowSignal)
            }
            return
        }
        // DO NOT OPEN A WINDOW ON TOP OF A WINDOW. This dispatcher runs from the timer
        // and could call `runModal` while another modal was already active, such as quit
        // confirmation or a manually opened ntfy dialog. Nested runModal blocks the bar:
        // the user sees two windows and cannot close either. Leave the signal on disk;
        // handle it after the first window closes.
        if NSApp.modalWindow != nil {
            return
        }
        // Same trap as show_guide: if the file cannot be removed (read-only
        // directory, uchg flag), the window would come back every five seconds
        // and make the Mac unusable. Act once per file that will not go away.
        let removed = (try? fm.removeItem(atPath: windowSignal)) != nil
        if !removed {
            if shownWindowFromStuckSignal { return }
            shownWindowFromStuckSignal = true
        } else {
            shownWindowFromStuckSignal = false
        }
        NSApp.activate(ignoringOtherApps: true)
        switch body {
        case "ntfy": ntfyDialog()
        case "fleetname": fleetNameDialog()
        case "observe": explainDry()
        // The way in when the status item is not on screen at all: on a Mac with
        // a notch macOS silently declines to draw an item that does not fit, and
        // there is no API to ask whether that happened. The panel places itself
        // in the top-right corner when it cannot find the button.
        case "panel": PaladinPanel.shared.toggle()
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
        // Watch-only mode must NOT look like active protection. The bar used to turn
        // red at critical level in both modes, so the alarm implied the guard had acted;
        // in this mode it stops nothing.
        if s.dryRun { return .secondaryLabelColor }
        switch s.level {
        case 3: return .systemRed
        case 2: return .systemOrange
        case 1: return .systemYellow
        default: return .labelColor
        }
    }

    // FLAMING BAR: at critical level the icon burns for ~3 seconds and GOES OUT.
    // Keep it deliberately short, with a 60 s pause: animation wakes the CPU, and we
    // will not heat the Mac just to show that it is hot.
    private var animationTimer: Timer?
    private var animationFrame = 0
    private var lastFlameAt = Date.distantPast

    private func lightBar(_ s: Snap) {
        lastFlameAt = Date()
        animationFrame = 0
        animationTimer = Timer.scheduledTimer(withTimeInterval: 0.12, repeats: true) { [weak self] t in
            guard let self = self else { t.invalidate(); return }
            self.animationFrame += 1
            if self.animationFrame > 25 {
                t.invalidate()
                self.animationTimer = nil
                self.refresh()
                return
            }
            let colors: [NSColor] = [.systemRed, .systemOrange, .systemYellow]
            let out = NSMutableAttributedString()
            out.append(icon(self.animationFrame % 2 == 0 ? "flame.fill" : "flame",
                            fallback: "!", size: 13))
            if let c = s.chip { out.append(NSAttributedString(string: String(format: " %.0f°", c))) }
            out.addAttributes([.foregroundColor: colors[self.animationFrame % 3],
                               .font: NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .bold)],
                              range: NSRange(location: 0, length: out.length))
            self.item.button?.attributedTitle = out
        }
        // .common, not .default: with an open menu or any modal window, the runloop
        // switches to tracking mode and a .default timer stops ticking. The animation
        // used to stall mid-frame and block refresh(), freezing the bar on stale
        // temperature exactly when the user was looking at it.
        if let t = animationTimer { RunLoop.main.add(t, forMode: .common) }
    }

    // FAN: when fans start from zero, the icon spins blue for ~3 s. Same CPU-saving
    // rule as the flame: short, with a 60 s pause.
    private var lastFanAt = Date.distantPast
    private var lastFanRpm = -1
    /// Conditional bar elements hold for 60 s after their trigger clears, so a
    /// reading dancing on a boundary (fans 0/300 rpm, battery 39.8/40.1 °C)
    /// cannot make the bar flicker and shift width every couple of seconds.
    private var stickyUntil: [Item: Date] = [:]

    private func sticky(_ i: Item, _ active: Bool) -> Bool {
        if active {
            stickyUntil[i] = Date().addingTimeInterval(60)
            return true
        }
        if let hold = stickyUntil[i], hold > Date() { return true }
        stickyUntil[i] = nil
        return false
    }

    /// Live AI sessions from agent_activity.json, cached by mtime: the title
    /// refreshes every couple of seconds and must not parse JSON each time.
    private var activityCacheMtime: Date = .distantPast
    private var activityCacheCount = 0

    func agentSessionCount() -> Int {
        guard let attrs = try? FileManager.default.attributesOfItem(atPath: activityPath),
              let mtime = attrs[.modificationDate] as? Date else { return 0 }
        // Stale file = daemon stopped writing; a marker based on old data lies.
        if Date().timeIntervalSince(mtime) > 180 { return 0 }
        if mtime == activityCacheMtime { return activityCacheCount }
        activityCacheMtime = mtime
        activityCacheCount = 0
        if let d = FileManager.default.contents(atPath: activityPath),
           let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
           let agents = j["agents"] as? [[String: Any]] {
            activityCacheCount = agents.count
        }
        return activityCacheCount
    }
    // Last good chip reading. Under full load, a single macmon read can fail (null in
    // the snapshot for ~1 cycle) and the bar flashed blank even though the daemon had
    // a good temperature moments earlier. Hold the last value for max. 2 daemon cycles
    // and draw it gray.
    private var lastChip: Double?
    private var lastChipAt = Date.distantPast

    private func spinBar(_ s: Snap) {
        lastFanAt = Date()
        animationFrame = 0
        animationTimer = Timer.scheduledTimer(withTimeInterval: 0.12, repeats: true) { [weak self] t in
            guard let self = self else { t.invalidate(); return }
            self.animationFrame += 1
            if self.animationFrame > 25 {
                t.invalidate()
                self.animationTimer = nil
                self.refresh()
                return
            }
            let colors: [NSColor] = [.systemBlue, .systemCyan, .systemTeal]
            let out = NSMutableAttributedString()
            out.append(icon(self.animationFrame % 2 == 0 ? "fan.fill" : "fan",
                            fallback: "fan", size: 13))
            if let f = s.fans.max(), f > 0 {
                out.append(NSAttributedString(string: " " + (f >= 1000 ? String(format: "%.1fk", Double(f) / 1000.0) : "\(f)")))
            }
            out.addAttributes([.foregroundColor: colors[self.animationFrame % 3],
                               .font: NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .bold)],
                              range: NSRange(location: 0, length: out.length))
            self.item.button?.attributedTitle = out
        }
        // .common, not .default: with an open menu or any modal window, the runloop
        // switches to tracking mode and a .default timer stops ticking. The animation
        // used to stall mid-frame and block refresh(), freezing the bar on stale
        // temperature exactly when the user was looking at it.
        if let t = animationTimer { RunLoop.main.add(t, forMode: .common) }
    }

    // CUP: when caffeinate starts, the cup blinks for ~3 s.
    private var lastMugAt = Date.distantPast
    private var wasAwake: Bool? = nil

    private func blinkMug() {
        lastMugAt = Date()
        animationFrame = 0
        animationTimer = Timer.scheduledTimer(withTimeInterval: 0.12, repeats: true) { [weak self] t in
            guard let self = self else { t.invalidate(); return }
            self.animationFrame += 1
            if self.animationFrame > 25 {
                t.invalidate()
                self.animationTimer = nil
                self.refresh()
                return
            }
            let out = NSMutableAttributedString()
            out.append(icon(self.animationFrame % 2 == 0 ? MUG_FILL : MUG,
                            fallback: "cafe", size: 13))
            let color: NSColor = self.animationFrame % 2 == 0 ? .systemBrown : .labelColor
            out.addAttributes([.foregroundColor: color,
                               .font: NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .bold)],
                              range: NSRange(location: 0, length: out.length))
            self.item.button?.attributedTitle = out
        }
        // .common, not .default: with an open menu or any modal window, the runloop
        // switches to tracking mode and a .default timer stops ticking. The animation
        // used to stall mid-frame and block refresh(), freezing the bar on stale
        // temperature exactly when the user was looking at it.
        if let t = animationTimer { RunLoop.main.add(t, forMode: .common) }
    }

    /// Return seconds until the timer session ends.
    /// `nil` means the session has no end or has already passed. Read `awake.json`
    /// because it carries `until`; the snapshot only says keep-awake is active.
    func awakeSecondsLeft() -> Double? {
        let a = Awake.read()
        guard (a["mode"] as? String) == "timer", let until = a["until"] as? Double else { return nil }
        let remaining = until - Date().timeIntervalSince1970
        return remaining > 0 ? remaining : nil
    }

    /// Pull the snapshot a few times after a human action instead of waiting for the tick.
    /// Three shots give the daemon time to wake (~0.5 s), execute, and rewrite
    /// `status.json`. These are one-shot timers, so there is no loop here.
    func refreshAfterAction() {
        postActionTimers.forEach { $0.invalidate() }
        postActionTimers = [0.7, 1.6, 3.0].map { delay in
            let t = Timer.scheduledTimer(withTimeInterval: delay, repeats: false) { [weak self] _ in
                self?.refresh()
            }
            // .common like the fixed timer; otherwise it does not tick with an open menu
            // or modal window, exactly when the human watches the result of the click.
            RunLoop.main.add(t, forMode: .common)
            return t
        }
    }

    /// Remember what the human JUST requested so the bar does not show old state briefly.
    /// Do not lie for long: after 6 s, truth returns from the snapshot even if the
    /// daemon died. A dead daemon must look dead.
    func expectDryRun(_ dry: Bool) {
        expectedDryRun = dry
        expectedDryRunSince = Date()
        refreshAfterAction()
    }

    func refresh() {
        let bold = NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .regular)
        guard var s = readSnap() else {
            let out = NSMutableAttributedString()
            out.append(icon("thermometer.medium", fallback: "T"))
            out.append(NSAttributedString(string: " —"))
            out.addAttributes([.foregroundColor: NSColor.secondaryLabelColor, .font: bold],
                              range: NSRange(location: 0, length: out.length))
            item.button?.attributedTitle = out
            return
        }

        // Optimism with expiration. The snapshot is source of truth, but for a moment
        // after a click it is simply OLDER than the human's decision. Show that decision
        // until the daemon confirms it or 6 s pass, whichever comes first. Without this
        // expiration a dead daemon would look healthy.
        if let expected = expectedDryRun {
            if s.dryRun == expected || Date().timeIntervalSince(expectedDryRunSince) > 6 {
                expectedDryRun = nil
            } else {
                s.dryRun = expected
            }
        }

        // A macmon read gap (chip_c == null in a FRESH snapshot) must not blank the bar:
        // for max. 45 s (2 daemon cycles at ~15 s plus margin), show the last good value
        // in gray. A stale snapshot is different: then the daemon is likely dead and no
        // "last value" is truth about NOW.
        // A value the DAEMON remembered is shown the same way as one this bar remembered:
        // grayed out. Anything else would draw a recollection in the color of a reading.
        var chipFromMemory = s.chipStale && s.chip != nil
        if !s.stale, !s.chipStale, let c = s.chip {
            // Remember ONLY from a fresh snapshot. A value from a dead daemon's file
            // would refresh the timestamp on every cycle and pretend to be current
            // after the daemon restarts.
            lastChip = c
            lastChipAt = Date()
        } else if !s.stale, s.chip == nil, let c = lastChip,
                  Date().timeIntervalSince(lastChipAt) <= 45 {
            // s.chip == nil is now explicit. It used to be implied by the branch above
            // catching every non-nil value; since that branch also refuses remembered
            // ones, without this the bar would overwrite the daemon's remembered value
            // with its own older memory.
            s.chip = c
            chipFromMemory = true
        }

        if prefs.enabled(.flame), s.level >= 3, animationTimer == nil,
           Date().timeIntervalSince(lastFlameAt) > 60 {
            lightBar(s)
        }
        if animationTimer != nil { return }   // Flame frames have priority for ~3 s.

        // Fans started from zero -> blue spin.
        let maxRpm = s.fans.max() ?? 0
        if prefs.enabled(.flame), !s.stale, lastFanRpm == 0, maxRpm > 0,
           Date().timeIntervalSince(lastFanAt) > 60 {
            lastFanRpm = maxRpm
            spinBar(s)
        } else {
            lastFanRpm = maxRpm
        }
        // caffeinate started -> blinking cup.
        let isAwakeActive = !Awake.read().isEmpty
        if animationTimer == nil, prefs.enabled(.flame), !s.stale, wasAwake == false, isAwakeActive,
           Date().timeIntervalSince(lastMugAt) > 60 {
            blinkMug()
        }
        wasAwake = isAwakeActive
        if animationTimer != nil { return }

        let out = NSMutableAttributedString()
        func text(_ t: String) { out.append(NSAttributedString(string: t)) }
        func gap() { if out.length > 0 { text(" ") } }

        out.append(icon("thermometer.medium", fallback: "T"))
        var temps: [String] = []
        if prefs.enabled(.chip) { temps.append(s.chip.map { String(format: "%.0f°", $0) } ?? "—") }
        if prefs.enabled(.gpu), let g = s.gpu { temps.append(String(format: "%.0f°", g)) }
        // Battery temperature earns bar width only near the line that matters:
        // lithium cells degrade above ~40 °C and the guard pauses there. A cool
        // battery is the normal state and says nothing.
        if prefs.enabled(.battery), let b = s.batt, sticky(.battery, b >= 40) {
            temps.append(String(format: "%.0f°", b))
        }
        var chipRange: NSRange?
        if !temps.isEmpty {
            let start = out.length + 1                       // after the space following the icon
            text(" " + temps.joined(separator: "/"))
            if chipFromMemory, prefs.enabled(.chip), let first = temps.first {
                chipRange = NSRange(location: start, length: (first as NSString).length)
            }
        }

        if prefs.enabled(.fans), let f = s.fans.max() {
            // Stopped fans on a hot chip are an ALARM and always shown; spinning
            // fans carry news; stopped fans on a cool machine are the normal
            // state and would only spend notch width (60 s hysteresis on hide).
            if f == 0 && (s.chip ?? 0) >= 70 && !s.chipStale {
                gap()
                out.append(icon("exclamationmark.triangle.fill", fallback: "!"))
                text(" 0")
            } else if sticky(.fans, f > 0) {
                gap()
                out.append(icon("fan", fallback: "fan"))
                text(" " + (f >= 1000 ? String(format: "%.1fk", Double(f) / 1000.0) : "\(f)"))
            }
        }
        // One glance answers "is an AI working on this Mac right now": the
        // marker's mere presence is the answer, the number counts sessions.
        if prefs.enabled(.agent) {
            let n = agentSessionCount()
            if sticky(.agent, n > 0) {
                gap()
                out.append(icon("sparkles", fallback: "AI"))
                if n > 1 { text(" \(n)") }
            }
        }
        if prefs.enabled(.watts), let w = s.watts {
            // Checked = visible even at 0.4 W; hiding below 1 W looked like a broken
            // checkbox. Below 10 W, show one decimal place.
            gap(); out.append(icon("bolt.fill", fallback: "W"))
            text(w < 10 ? String(format: " %.1fW", w) : String(format: " %.0fW", w))
        }
        if prefs.enabled(.ram), let u = s.ramUsed, let t = s.ramTotal, t > 0 {
            gap(); out.append(icon("memorychip", fallback: "RAM"))
            text(String(format: " %.0f%%", 100 * u / t))
            // Swap gets no bar icon: macOS almost always keeps some swap, so the marker
            // looked random. Details live in the RAM menu row.
        }
        if prefs.enabled(.disk), let p = s.diskPct {
            gap(); out.append(icon("internaldrive", fallback: "SSD")); text(" \(p)%")
        }
        if prefs.enabled(.throttle), s.cpuLimit < 100 {
            gap(); out.append(icon("tortoise.fill", fallback: "slow"))
        }
        // In watch-only mode, the EYE icon is leading, not tucked at the end: the bar
        // used to turn red and flame exactly like protected mode, so the alarm looked
        // the same even though NOTHING will be paused.
        if s.dryRun { gap(); out.append(icon("eye", fallback: "obs")) }
        if s.keepAwake { gap(); out.append(icon(MUG_FILL, fallback: "awake")) }
        // Keep-awake time remaining, directly in the bar so the menu need not be opened.
        // Show ONLY sessions with a concrete end. Indefinite mode, "while app runs",
        // and "while downloading" have nothing to count down; inventing a timer would
        // be a lie.
        if prefs.enabled(.awakeLeft), s.keepAwake, let secondsLeft = awakeSecondsLeft() {
            gap()
            out.append(icon(MUG, fallback: "awake"))
            let h = Int(secondsLeft) / 3600, m = (Int(secondsLeft) % 3600) / 60
            out.append(NSAttributedString(
                string: " " + (h > 0 ? String(format: "%d:%02d", h, m)
                                     : String(format: "%d min", max(m, 1)))))
        }
        if prefs.enabled(.paused), !s.paused.isEmpty {
            gap(); out.append(icon("pause.circle.fill", fallback: "||"))
        }

        out.addAttributes([.foregroundColor: tint(s), .font: bold],
                          range: NSRange(location: 0, length: out.length))
        // Gray = "value from memory, not current reading"; apply AFTER whole-bar color
        // so no tint overwrites it.
        if let z = chipRange {
            out.addAttribute(.foregroundColor, value: NSColor.secondaryLabelColor, range: z)
        }
        item.button?.attributedTitle = out

        var tip = s.reason.isEmpty ? "coffee-paladin: " + T("Calm") : s.reason
        if let e = s.eta { tip += String(format: "\n%.0f min", e) }
        item.button?.toolTip = tip
    }

    func menuNeedsUpdate(_ m: NSMenu) {
        GuardCfg.beginCache()          // one config read for the whole menu
        defer { GuardCfg.endCache() }
        m.removeAllItems()
        // Brand section: logo + name, with nothing above it. This is the product's face.
        let head = NSMenuItem()
        head.view = HeaderRow()
        m.addItem(head)
        m.addItem(.separator())
        // Language directly under the brand, as its own cleanly separated section.
        let langTop = NSMenuItem()
        langTop.view = LangRow()
        m.addItem(langTop)
        m.addItem(.separator())
        guard let s = readSnap() else {
            // This is EXACTLY when the human needs the log, report, and guide. These
            // three used to disappear because they are built below, leaving one item:
            // "Quit coffee-paladin". Dead end.
            m.addItem(NSMenuItem(title: T("no data - is coffee-paladin running?"), action: nil, keyEquivalent: ""))
            let restart = m.addItem(withTitle: T("Start the guard again"),
                                    action: #selector(restartGuard), keyEquivalent: "")
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

        if s.stale { row("! " + String(format: T("data is stale (%@) - the guard may have died"), s.stamp)) }
        if let c = s.lastCrash { row(String(format: T("the Mac shut down without warning: %@"), c)) }

        // Pair readings into one line: temperatures together, load with fans, power
        // source with draw. The card stays shorter with no new translation keys, because
        // it is assembled from existing fragments.
        // Leading icons match the bar exactly (thermometer/fan/bolt/memorychip/internaldrive),
        // so the bar readout and card readout use the same visual language.
        // Icons inside a line (fan, bolt) are NSTextAttachment values from icon().
        func rowI(_ symbol: String, _ body: NSAttributedString, into menu: NSMenu? = nil) {
            let it = NSMenuItem(title: "", action: nil, keyEquivalent: "")
            it.image = img(symbol)
            let a = NSMutableAttributedString(attributedString: body)
            a.addAttribute(.font, value: NSFont.menuFont(ofSize: 0),
                           range: NSRange(location: 0, length: a.length))
            it.attributedTitle = a
            (menu ?? m).addItem(it)
        }
        func txt(_ s: String) -> NSAttributedString { NSAttributedString(string: s) }

        // No verdict headline here. Everything it said is already on screen: the bar
        // icon carries the state and its markers, the freeze switch below says how many
        // jobs are held, and the chart paints the hot readings red. A second copy of a
        // fact is not emphasis, it is another line to read before the numbers.
        rowI("thermometer.medium",
             txt("Chip:  " + (s.chip.map { String(format: "%.1f °C", $0) + (s.chipStale ? T(" (remembered)") : "") } ?? na)
                 + (s.gpu != nil ? String(format: "     GPU: %.1f °C", s.gpu!) : "")
                 + "     " + String(format: T("Battery:  %@"),
                                    s.batt.map { String(format: "%.1f °C", $0) } ?? na)))
        // caffeinate, held: the command's own name in red at the end of the machine row,
        // not a sentence of its own. Five variants of "the Mac is being kept awake" said
        // less than one word anybody can look up, and the mug matches the bar icon.
        // The countdown is added only for a timer, the one mode with an honest end;
        // which mode is running stays in the Keep awake submenu.
        func caffeinateTag(into line: NSMutableAttributedString) {
            line.append(NSAttributedString(string: "   "))
            line.append(icon(MUG_FILL, fallback: ""))
            line.append(NSAttributedString(string: " caffeinate",
                                           attributes: [.foregroundColor: NSColor.systemRed]))
            let awake = Awake.read()
            if (awake["mode"] as? String) == "timer", let until = awake["until"] as? Double {
                let left = max(0, until - Date().timeIntervalSince1970)
                line.append(NSAttributedString(string: " " + fmtDur(Int(left / 60)),
                                               attributes: [.foregroundColor: NSColor.secondaryLabelColor]))
            }
        }
        // One row for the machine's own numbers, no submenu and no labels: the icons
        // are the labels. RAM, cores and fans were context hidden one click away while
        // the card repeated them anyway whenever they got alarming, so the same reading
        // could appear twice or not at all. Now it appears once, always, and the row
        // fits: the widest case measured about 340 pt against the 360 pt the chart and
        // the switches already hold, so the menu keeps its width.
        let hwLine = NSMutableAttributedString()
        if let u = s.ramUsed, let t = s.ramTotal, t > 0 {
            hwLine.append(txt(String(format: t < 100 ? "%.1f/%.0f GB" : "%.0f/%.0f GB", u, t)))
            if let sw = s.swap, sw > 0.5 {
                hwLine.append(txt(String(format: sw < 10 ? " +%.1f swap" : " +%.0f swap", sw)))
            }
        }
        if !hwLine.string.isEmpty { hwLine.append(txt("   ")) }
        hwLine.append(icon("gauge", fallback: ""))
        hwLine.append(txt(String(format: " %.1f/%d", s.load, ProcessInfo.processInfo.processorCount)))
        if !s.fans.isEmpty {
            // Unit once at the end, but show ALL values. Filtering zeros would hide a fan
            // that stopped while another runs, exactly the symptom the cooling-failure
            // alarm exists for. Zero must be visible.
            hwLine.append(txt("   "))
            hwLine.append(icon("fan", fallback: ""))
            hwLine.append(txt(" " + (s.fans.allSatisfy { $0 == 0 }
                ? T("stopped")
                : String(format: T("%@ rpm"), s.fans.map(String.init).joined(separator: "\u{00B7}")))))
        }
        if s.keepAwake { caffeinateTag(into: hwLine) }
        let hwItem = NSMenuItem()
        // The leading icon goes where every other row keeps it, in the item's image, so
        // the text starts on the same line as the rows above and below. Carrying it
        // inside the string left this one row shifted left of the whole card.
        hwItem.image = img("memorychip")
        hwItem.attributedTitle = hwLine
        // Without the words on screen, the words live one hover away: VoiceOver reads the
        // tooltip, and so does anyone who cannot place an icon.
        hwItem.toolTip = T("Memory used of total, load average over cores, fan speed")
        m.addItem(hwItem)
        // Disk and power are not per-second readings, so they earn a row only when they
        // change what happens: a full disk, or running on battery where the gate applies.
        if let du = s.diskUsed, let dt = s.diskTotal, let dp = s.diskPct, dp >= 85 {
            rowI("internaldrive", txt(String(format: T("Disk:  %d / %d GB used (%d%%)"), du, dt, dp)))
        }
        if !s.onAC || s.watts != nil {
            let pw = NSMutableAttributedString()
            pw.append(txt(String(format: T("Power:  %@"), s.onAC ? T("AC adapter") : T("Battery"))))
            if let w = s.watts {
                pw.append(txt("     "))
                pw.append(icon("bolt.fill", fallback: ""))
                pw.append(txt(" " + String(format: T("Draw:  %.1f W"), w)))
            }
            rowI(s.onAC ? "powerplug" : "battery.100", pw)
        }
        // "CPU available: 100%" was misleading: this is CPU_Speed_Limit from pmset
        // (clock throttling), not free capacity. Show the row ONLY when throttling is
        // real; at 100% it is noise, and the label now states the meaning directly.
        if s.cpuLimit < 100 {
            row(String(format: T("Throttling: CPU capped at %d%% speed"), s.cpuLimit))
        }
        if let chart = ChartRow.make() {
            m.addItem(.separator())
            let it = NSMenuItem()
            it.view = chart
            m.addItem(it)
        }
        // The "about N min to pause" forecast was removed from the card: linear
        // extrapolation lies near the 88-90 C plateau where Apple cuts clocks.
        // trend_c_min and eta_pause_min stay in status.json for agents; do not mislead
        // the human.

        // Freeze action directly under readings and chart, where the user looks when hot.
        m.addItem(.separator())
        // PROTECTION SWITCH: the most important decision in the app, so do not hide it
        // in Settings. Switch ON means protection is active (dry_run = false).
        let watchOnly = GuardCfg.bool("dry_run", true)
        let protectionItem = NSMenuItem()
        protectionItem.view = SwitchRow(T("Thermal protection"),
                                 on: !watchOnly,
                                 target: self, action: #selector(toggleDry),
                                 offSubtitle: T("OFF - the Mac is only being watched"),
                                 iconName: "pause")
        m.addItem(protectionItem)
        // Autostart directly under protection: two switches together, one on/off section;
        // loop icon means "again at every login".
        let auto = NSMenuItem()
        auto.view = SwitchRow(T("Start at login"), on: Autostart.enabled(),
                              target: self, action: #selector(toggleAutostart),
                              iconName: "arrow.triangle.2.circlepath")
        m.addItem(auto)
        // Switch instead of a clickable item: ON = manually frozen. Blue avoids confusion
        // with green PROTECTION; the heavy-process count sits beside it.
        let frozen = !s.paused.isEmpty
        let freezeItem = NSMenuItem()
        let freezeView = SwitchRow(T("Freeze all heavy jobs now"),
                                 on: frozen,
                                 target: self, action: #selector(toggleFreeze(_:)),
                                 // Icon describes the row FUNCTION; state lives in the switch.
                                 // A "play" icon beside an ON switch contradicted itself.
                                 iconName: "pause.circle",
                                 // With jobs held, the count that matters is how many are
                                 // held, not how many could be: after the verdict row went
                                 // this is the only place on the card that still says it.
                                 fixedSubtitle: frozen
                                     ? String(format: T("Held right now: %d"), s.paused.count)
                                     : String(format: T("Heavy processes right now: %d"),
                                              s.heavyCount),
                                 color: .systemBlue)
        // Tooltip says WHICH processes are targeted (top 3 by CPU).
        if !s.topCpuList.isEmpty {
            freezeView.toolTip = s.topCpuList.map { "\($0.name) (\($0.cpu)%)" }.joined(separator: ", ")
        }
        freezeItem.view = freezeView
        m.addItem(freezeItem)
        m.addItem(.separator())

        // Export: the user chooses the format, not us.
        let rep = NSMenuItem(title: T("Export report for a repair shop"), action: nil, keyEquivalent: "")
        rep.image = img("wrench.and.screwdriver")
        rep.action = #selector(reportDialog)
        rep.target = self
        m.addItem(rep)
        let logIt = m.addItem(withTitle: T("Show the guard log"), action: #selector(openLog), keyEquivalent: "")
        logIt.target = self
        logIt.image = img("text.alignleft")

        // Directly under the log: same family. The log says WHAT happened; stats say
        // HOW MANY TIMES.
        let statsIt = m.addItem(withTitle: T("Guard statistics"),
                                action: #selector(openStats), keyEquivalent: "")
        statsIt.target = self
        statsIt.image = img("checkmark.shield")

        // The guide stays under the log because the welcome window appears once; after
        // closing it, there must still be a place to reopen the guide.
        let guideIt = m.addItem(withTitle: T("First steps…"), action: #selector(openGuide), keyEquivalent: "")
        guideIt.target = self
        guideIt.image = img("book")

        addTail(m, paused: !s.paused.isEmpty)
    }

    /// Return a template SF Symbol icon for a menu item, so it takes the system color.
    func img(_ name: String) -> NSImage? {
        let i = NSImage(systemSymbolName: name, accessibilityDescription: nil)
        i?.isTemplate = true
        return i
    }

    func addTail(_ m: NSMenu, paused: Bool) {
        m.addItem(.separator())
        // KEEP AWAKE like Amphetamine, except every mode has an overriding thermal fuse:
        // on overheating, the daemon still releases the sleep lock.
        let ka = NSMenuItem(title: T("Keep awake"), action: nil, keyEquivalent: "")
        ka.image = img(MUG)
        let km = NSMenu()
        km.autoenablesItems = false
        let cur = Awake.read()
        let curMode = cur["mode"] as? String
        // Whether keep-awake is REALLY held. `awake.json` describes only manual sessions;
        // the separate "hold for heavy jobs" path runs beside it. Without this, the menu
        // reported "Off" while the main card said "Keeping the Mac awake". The daemon
        // snapshot is proof because the daemon holds caffeinate.
        let actuallyHeld = readSnap()?.keepAwake ?? false

        let stateItem = NSMenuItem(title: T(actuallyHeld ? "Right now: keeping the Mac awake"
                                                        : "Right now: NOT keeping the Mac awake"),
                              action: nil, keyEquivalent: "")
        stateItem.isEnabled = false
        km.addItem(stateItem)
        km.addItem(.separator())

        let off = NSMenuItem(title: T("Off"), action: #selector(awakeOff), keyEquivalent: "")
        off.target = self
        // Checkmark only when NOTHING holds keep-awake, neither manual session nor auto.
        off.state = (curMode == nil && !actuallyHeld) ? .on : .off
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

        // "Until a set hour": ready whole hours instead of a text field. Calculate by
        // CALENDAR, not by adding seconds; otherwise DST changes and crossing midnight
        // produce the wrong hour. Store epoch anyway, so the rest of the code is unchanged.
        let untilItem = NSMenuItem(title: T("Until a set hour"), action: nil, keyEquivalent: "")
        let um = NSMenu()
        um.autoenablesItems = false
        let calendar = Calendar.current
        let now = Date()
        let fmt = DateFormatter()
        fmt.locale = Locale.current
        fmt.setLocalizedDateFormatFromTemplate("j:mm")   // 17:00 or 5:00 PM per system settings
        var foundCount = 0
        // Start from the CURRENT whole hour built from components. `date(bySetting:)`
        // searches for the NEXT matching date, so at 16:20 it already returned 17:00;
        // the loop then added another hour and the nearest option became 18:00. The
        // nearest whole hour is the useful one here, so do not lose it.
        var components = calendar.dateComponents([.year, .month, .day, .hour], from: now)
        components.minute = 0
        components.second = 0
        var candidateDate = calendar.date(from: components) ?? now
        while foundCount < 12 {
            candidateDate = calendar.date(byAdding: .hour, value: 1, to: candidateDate) ?? candidateDate
            let wholeHour = candidateDate
            if wholeHour <= now.addingTimeInterval(60) { continue }
            let it = NSMenuItem(title: String(format: T("until %@"), fmt.string(from: wholeHour)),
                                action: #selector(awakeUntil(_:)), keyEquivalent: "")
            it.target = self
            it.representedObject = wholeHour.timeIntervalSince1970
            um.addItem(it)
            foundCount += 1
        }
        untilItem.submenu = um
        km.addItem(untilItem)

        // Extend a running session. When none is running, act like a normal timer;
        // otherwise the item would be dead and need disabling for no useful reason.
        let extItem = NSMenuItem(title: T("Extend"), action: nil, keyEquivalent: "")
        let em = NSMenu()
        em.autoenablesItems = false
        for min in [15, 30, 60] {
            let it = NSMenuItem(title: String(format: T("Extend by %d min"), min),
                                action: #selector(awakeExtend(_:)), keyEquivalent: "")
            it.target = self
            it.representedObject = min
            em.addItem(it)
        }
        extItem.submenu = em
        km.addItem(extItem)
        km.addItem(.separator())

        // "While an app is running": list real running windowed applications.
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
                                target: self, action: #selector(toggleAwake), color: .systemGray)
        km.addItem(kaAuto)
        // Screen is separate from system wake: `caffeinate -is` keeps the system awake
        // but lets the display sleep. A lit panel costs more power and heat, so default off.
        let kaScreen = NSMenuItem()
        kaScreen.view = SwitchRow(T("Keep the screen on too (uses more power)"),
                                  on: GuardCfg.bool("keep_awake_display", false),
                                  target: self, action: #selector(toggleAwakeDisplay),
                                  color: .systemGray)
        km.addItem(kaScreen)
        ka.submenu = km
        m.addItem(ka)

        // checkboxes deciding what appears in the bar; state kept in heatbar.json
        let showItem = NSMenuItem(title: T("Show in the bar"), action: nil, keyEquivalent: "")
        showItem.image = img("eye")
        let sub = NSMenu()
        sub.autoenablesItems = false
        // At the top, so users do not click every item separately. Disabled when
        // everything is already visible; a dead click confuses more than it helps.
        // Three presets before the checkboxes. On a Mac with a notch the full
        // readout does not fit and macOS then draws NOTHING - no warning, no way
        // to ask why. Someone in that situation needs one click, not eleven.
        // The eye (watch-only) and the cup (keep-awake) stay outside the presets:
        // they say what the program is DOING and hiding them to save pixels would
        // trade a truth for a few points of width. Hence "no numbers", not "one icon".
        let iconOnly = NSMenuItem(title: T("Icon only, no numbers"),
                                  action: #selector(barIconOnly), keyEquivalent: "")
        iconOnly.target = self
        iconOnly.state = prefs.noneEnabled ? .on : .off
        sub.addItem(iconOnly)
        let iconAndChip = NSMenuItem(title: T("Icon and chip temperature"),
                                     action: #selector(barIconAndChip), keyEquivalent: "")
        iconAndChip.target = self
        iconAndChip.state = prefs.onlyChipEnabled ? .on : .off
        sub.addItem(iconAndChip)
        let showAll = NSMenuItem(title: T("Show all"), action: #selector(showAllItems),
                                  keyEquivalent: "")
        showAll.target = self
        showAll.state = prefs.allEnabled ? .on : .off
        showAll.isEnabled = !prefs.allEnabled
        sub.addItem(showAll)
        sub.addItem(.separator())
        for (i, it) in Item.allCases.enumerated() {
            let mi = NSMenuItem(title: it.label, action: #selector(toggleItem(_:)), keyEquivalent: "")
            mi.target = self
            mi.tag = i
            mi.state = prefs.enabled(it) ? .on : .off
            sub.addItem(mi)
        }
        showItem.submenu = sub
        m.addItem(showItem)

        // Settings panel: threshold sliders and switches. The daemon reads config.json
        // on every cycle, so changes apply immediately without restarting anything.
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
            title: T("CPU limit for heavy jobs"), min: 10, max: 100,
            current: GuardCfg.double("job_cpu_percent", 95), unit: "%", step: 5,
            describe: { v in
                // The limiter is a duty cycle on the whole job, so the percentage is
                // roughly how many of this machine's cores it may keep busy. Starting
                // the slider at 50 made the useful settings unreachable: safe-run maps
                // --cores 1 to 10% and --cores 4 to 29% on a 14 core Mac.
                let cores = Swift.max(1, Int((v / 100.0 * Double(ProcessInfo.processInfo.processorCount)).rounded()))
                if v >= 100 { return (T("no limit: a job may use the whole machine"), "") }
                return (String(format: T("about %d of %d cores; the job gets tiny micro-pauses (works for any program)"),
                               cores, ProcessInfo.processInfo.processorCount), "")
            }) { v in
            GuardCfg.set(["job_cpu_percent": Int(v)])
        }
        ss.addItem(cpuRow)
        ss.addItem(.separator())
        let chipRow = NSMenuItem()
        chipRow.view = SliderRow(
            // 70 at the bottom: an idle M series chip sits at 40 to 55 and ordinary work
            // reaches 70, so anything lower pauses on nothing. 98 at the top: the daemon
            // rewrites a pause threshold that reaches the kill threshold, and on this
            // machine the CPU side of the reading saturates near 98 anyway.
            title: T("Chip pause threshold"), min: 70, max: 98, current: pauseNow, unit: "°C", step: 1,
            describe: thresholdWarning,
            derive: { v in String(format: T("resume at %.0f °C, terminate at %.0f C"),
                                  v - 9, Swift.min(v + 5, 100)) }) { v in
            // Keep derived values consistent: hysteresis 9 C down, kill 5 C up (max 100).
            GuardCfg.set(["soc_pause_c": v,
                          "soc_resume_c": v - 9,
                          "soc_kill_c": Swift.min(v + 5, 100)])
        }
        ss.addItem(chipRow)
        ss.addItem(.separator())

        let battRow = NSMenuItem()
        // Above 30% "low battery" stops meaning low: the gate would pause long jobs on
        // a battery that is a third full and wait for a charger that may not be near.
        battRow.view = SliderRow(title: T("Battery gate"), min: 5, max: 30,
                                 current: GuardCfg.double("batt_pct_pause", 10), unit: "%",
                                 describe: { _ in (T("pause below this charge when unplugged"), "") }) { v in
            GuardCfg.set(["batt_pct_pause": Int(v), "batt_pct_resume": Int(v) + 15])
        }
        ss.addItem(battRow)
        ss.addItem(.separator())

        // HEAVY JOBS: core type + CPU limit (safe-run defaults saved to config.json).
        // Measurement interval: slower = cheaper, faster = quicker automatic reaction;
        // manual actions still react in ~1 s regardless.
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
                               target: self, action: #selector(toggleNotify), color: .systemBlue)
        ss.addItem(notif)
        func infoLine(_ text: String) {
            let it = NSMenuItem(title: "", action: nil, keyEquivalent: "")
            it.attributedTitle = NSAttributedString(
                string: text,
                attributes: [.font: NSFont.systemFont(ofSize: 11),
                             .foregroundColor: NSColor.secondaryLabelColor])
            it.isEnabled = false
            ss.addItem(it)
        }
        infoLine(T("Turns off banners, their sounds and phone push - one gate for all."))
        // Watch-only help lives in the popup shown when DISABLING protection.
        // Notifications / Sounds / Push form one compact section.

        let snd = NSMenuItem()
        snd.view = SwitchRow(T("Sounds"), on: GuardCfg.bool("sound", false),
                             target: self, action: #selector(toggleSound), color: .systemBlue)
        ss.addItem(snd)
        infoLine(T("Exception: the critical banner shouts regardless."))

        // "Keep awake while heavy jobs run" now lives in the Keep awake submenu.

        let ntfy = NSMenuItem()
        ntfy.view = SwitchRow(T("Phone push (ntfy.sh)…"),
                              on: !GuardCfg.string("ntfy_topic", "").isEmpty,
                              target: self, action: #selector(toggleNtfy), color: .systemBlue)
        ss.addItem(ntfy)

        ss.addItem(.separator())
        let flabel = NSMenuItem(title: "", action: #selector(fleetNameDialog), keyEquivalent: "")
        // After "|", show the current name in gray so fleet identity is visible at once.
        let fleetName = GuardCfg.string("fleet_label", "")
        let displayName = fleetName.isEmpty
            ? (Host.current().localizedName ?? "Mac")
            : fleetName
        let ft = NSMutableAttributedString(string: T("Name this Mac in the fleet…") + "  |  ",
                                           attributes: [.font: NSFont.menuFont(ofSize: 0)])
        ft.append(NSAttributedString(string: displayName,
                                     attributes: [.font: NSFont.menuFont(ofSize: 0),
                                                  .foregroundColor: NSColor.secondaryLabelColor]))
        flabel.attributedTitle = ft
        flabel.target = self
        flabel.state = GuardCfg.string("fleet_label", "").isEmpty ? .off : .on
        ss.addItem(flabel)

        setItem.submenu = ss
        m.addItem(setItem)

        // ABOUT MY MAC: hardware detected by the guard, battery health, and thresholds.
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
            // Pair fields by line: model+chip / cores+NE / RAM+disk /
            // macOS+setup date / fans+battery cycles.
            let chipName = (hw["chip"] as? String) ?? "?"
            arow(((hw["model_name"] as? String) ?? "?") + "  ·  " + chipName)
            // Cores and memory on one line, no Neural Engine (nothing here uses it) and
            // no disk (the card shows it when it matters, and this menu is an ID card:
            // what the machine IS, not what it is doing).
            arow(String(format: T("Cores:  %d performance + %d efficiency  ·  %d GB RAM"),
                        (hw["p_cores"] as? Int) ?? 0, (hw["e_cores"] as? Int) ?? 0,
                        (hw["ram_gb"] as? Int) ?? 0))
            // Marketing system name, as in "About This Mac" (Tahoe/Sequoia/...).
            let osVersion = (hw["macos"] as? String) ?? "?"
            let osName: String
            switch Int(osVersion.split(separator: ".").first.map(String.init) ?? "") ?? 0 {
            case 26: osName = "macOS Tahoe"
            case 15: osName = "macOS Sequoia"
            case 14: osName = "macOS Sonoma"
            case 13: osName = "macOS Ventura"
            case 12: osName = "macOS Monterey"
            case 11: osName = "macOS Big Sur"
            default: osName = "macOS"
            }
            var osLine = osName + " " + osVersion
            if let atr = try? FileManager.default.attributesOfItem(atPath: "/var/db/.AppleSetupDone"),
               let setupDoneDate = (atr[.creationDate] ?? atr[.modificationDate]) as? Date {
                let f = DateFormatter()
                f.dateFormat = "dd.MM.yyyy"
        f.locale = Locale(identifier: "en_US_POSIX")
        f.calendar = Calendar(identifier: .gregorian)
                osLine += "  ·  " + String(format: T("set up: %@"), f.string(from: setupDoneDate))
            }
            arow(osLine)
            abm.addItem(.separator())
            let fanCount = (hw["fan_count"] as? Int) ?? 0
            var fanLine = fanCount == 0
                ? T("Cooling:  passive, no fans")
                : String(format: T("Cooling:  %d fans"), fanCount)
            if let cyc = hw["battery_cycles"] as? Int {
                let warn = (hw["battery_failure"] as? Bool) == true ? " (!)" : ""
                fanLine += "  ·  " + String(format: T("Battery cycles:  %@"), "\(cyc)\(warn)")
            }
            if let capacity = hw["battery_max_capacity_pct"] as? Int {
                fanLine += "  ·  " + String(format: T("max capacity: %d%%"), capacity)
            }
            arow(fanLine)
            if let ser = hw["serial"] as? String, !ser.isEmpty {
                // No warranty guess here any more: it was a year counted from the first
                // system setup, which a reinstall or a migration resets, and Apple's own
                // term starts at purchase. A wrong date on a repair document is worse
                // than no date.
                arow(String(format: T("Serial:  %@"), ser))
            }
            // Show all measurement sources, not only macmon. If one fails, users can
            // immediately see what else is still watching the machine.
            // What the chip number IS, because every threshold in this app is set
            // against it: macmon averages the SMC keys it can read on the CPU side and
            // on the GPU side, and the guard takes whichever average is higher. It is a
            // relative index, not the hottest point on the die. The five-row list of
            // sensors that used to be here answered a question nobody asked; a missing
            // sensor is worth a row, a working one is not.
            abm.addItem(.separator())
            let chipRow = NSMenuItem(title: T("Chip reading:  the higher of the CPU and GPU average (macmon)"),
                                     action: nil, keyEquivalent: "")
            chipRow.toolTip = T("macmon averages every SMC key it can read: Tp/Te/Ts on the CPU side, Tg on the GPU side. The guard shows whichever average is higher, so during LLM or video work this is the GPU cluster. It is a relative index, not the hottest transistor, and the two averages saturate at different values on the same machine.")
            abm.addItem(chipRow)
            if (hw["chip_sensor"] as? Bool) != true {
                let miss = NSMenuItem(title: T("The chip reading is missing - is macmon installed?"),
                                      action: nil, keyEquivalent: "")
                miss.image = img("exclamationmark.triangle")
                abm.addItem(miss)
            }
        }
        about.submenu = abm
        m.addItem(about)
        if let sn = readSnap() {
            // "Load info": jobs, top CPU/RAM, state, thresholds, and daily counter all
            // live in a submenu so the main card stays compact.
            // "What is loading the Mac": the answer first, the evidence under it, and
            // a heading only when it has entries below it. CPU is shown in cores, not
            // percent: "985% CPU" means nothing next to "Load: 8.5 / 14 cores" on the
            // card, and a number over 100 reads like an error.
            let loadIt = NSMenuItem(title: T("What is loading the Mac"), action: nil, keyEquivalent: "")
            loadIt.image = img("chart.bar")
            let lo = NSMenu()
            lo.autoenablesItems = false
            func lrow(_ t: String) { lo.addItem(NSMenuItem(title: t, action: nil, keyEquivalent: "")) }
            func entry(_ t: String) {
                let it = NSMenuItem(title: t, action: nil, keyEquivalent: "")
                it.indentationLevel = 1
                lo.addItem(it)
            }
            func headline(_ symbol: String, _ text: String) {
                let it = NSMenuItem(title: "", action: nil, keyEquivalent: "")
                let a = NSMutableAttributedString(string: text)
                a.addAttribute(.font, value: NSFont.boldSystemFont(ofSize: NSFont.systemFontSize),
                               range: NSRange(location: 0, length: a.length))
                it.attributedTitle = a
                it.image = img(symbol)
                lo.addItem(it)
            }
            if !sn.paused.isEmpty {
                headline("pause.circle", String(format: T("Held: %d"), sn.paused.count)
                         + (sn.manualPause ? T("  (by hand)") : ""))
                for name in sn.paused { entry(name) }
            } else {
                let names = [T("Calm"), T("Warming up"), T("Hot"), T("Critical")]
                let symbols = ["checkmark.circle", "thermometer.medium", "flame", "exclamationmark.triangle"]
                let lvl = min(max(sn.level, 0), 3)
                headline(symbols[lvl], names[lvl] + (sn.reason.isEmpty ? "" : "  ·  \(sn.reason)"))
            }
            if !sn.jobs.isEmpty {
                lo.addItem(.separator())
                lrow(T("Under the guard (safe-run):"))
                for j in sn.jobs { entry("\(j.name)  ·  " + fmtDur(j.minutes)) }
            }
            if !sn.topCpuList.isEmpty {
                lo.addItem(.separator())
                lrow(T("Heating the most (CPU stands in for heat):"))
                for t in sn.topCpuList {
                    entry(String(format: "%@  ·  %.1f " + T("cores"), t.name, Double(t.cpu) / 100.0))
                }
            } else if let p = sn.topProc, let c = sn.topCPU {
                lo.addItem(.separator())
                lrow(String(format: "%@  ·  %.1f " + T("cores"), p, Double(c) / 100.0))
            }
            if !sn.topRamList.isEmpty {
                lo.addItem(.separator())
                lrow(T("Eating the most RAM:"))
                for t in sn.topRamList { entry(String(format: "%@  ·  %.1f GB", t.name, t.gb)) }
            }
            lo.addItem(.separator())
            if let pp = sn.thrPause, let pk = sn.thrKill {
                lrow(String(format: T("Chip thresholds:  pause %.0f °C, kill %.0f °C"), pp, pk))
            }
            if sn.pausesToday > 0 || sn.killsToday > 0 {
                lrow(String(format: T("Today: %d x pause"), sn.pausesToday)
                     + (sn.killsToday > 0 ? String(format: T(", %d x kill"), sn.killsToday) : ""))
            }
            loadIt.submenu = lo
            m.addItem(loadIt)
        }


        // AGENT ACTIVITY: what the AI sessions on THIS Mac started, from the
        // daemon's agent_activity.json. The file is local and tiny, so it is
        // read on open; the fleet-style background cache exists for slow
        // network folders, not for this.
        let actIt = NSMenuItem(title: T("Agent activity"), action: nil, keyEquivalent: "")
        actIt.image = img("sparkles")
        let amenu = NSMenu()
        amenu.autoenablesItems = false
        func actIcon(_ comm: String) -> String {
            let c = comm.lowercased()
            if c.hasPrefix("python") { return "chevron.left.forwardslash.chevron.right" }
            if c == "ffmpeg" || c.hasPrefix("x26") || c == "ab-av1" { return "film" }
            if c.contains("ollama") || c.contains("mlx") { return "cpu" }
            if c == "brew" { return "shippingbox" }
            if c == "sh" || c == "bash" || c == "zsh" { return "terminal" }
            if ["make", "cmake", "swiftc", "clang", "cargo", "xcodebuild", "ninja"].contains(c) {
                return "hammer"
            }
            if c == "node" || c == "bun" || c == "deno" { return "gearshape.2" }
            return "gearshape"
        }
        var actRows: [(String, String, Int)] = []
        var actTotal = 0
        // Rows and nodes stopped being the same thing once duplicates started folding:
        // "sleep ×3" is one row standing for three nodes. The "… N more" counter has to
        // compare nodes with nodes, or it reports hidden entries that are on screen.
        var actShown = 0
        // The same 180 s stale gate as the bar marker: after a daemon stop the
        // file freezes, and a menu listing yesterday's sessions as alive lies.
        let actFresh: Bool = {
            guard let attrs = try? FileManager.default.attributesOfItem(atPath: activityPath),
                  let mtime = attrs[.modificationDate] as? Date else { return false }
            return Date().timeIntervalSince(mtime) <= 180
        }()
        // Sessions get ONE honest line each; the full process trees moved to
        // their own "Process tree details" submenu. Three identical
        // zsh > bash > sleep chains on the first screen said nothing except
        // "there is a lot here" - which is the opposite of what a glance is
        // for. An idle session says "idle", not "0% CPU in its tree".
        var sessionRows: [String] = []
        if actFresh,
           let d = FileManager.default.contents(atPath: activityPath),
           let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
           let agents = j["agents"] as? [[String: Any]], !agents.isEmpty {
            // Identical siblings collapse into one row with a count. An agent that spawns
            // the same helper five times produced five identical lines, which pushed the
            // interesting branches off the visible list without adding one fact.
            // Only IDLE duplicates fold: anything burning CPU keeps its own row, because
            // that is the row someone opened this submenu to find.
            func walk(_ nodes: [[String: Any]], indent: Int) {
                var pending: (comm: String, count: Int)? = nil
                func flush() {
                    guard let p = pending else { return }
                    pending = nil
                    guard actRows.count < 40 else { return }
                    let title = p.count > 1 ? "\(p.comm) ×\(p.count)" : p.comm
                    actRows.append((title, actIcon(p.comm), indent))
                    actShown += p.count
                }
                for n in nodes {
                    actTotal += 1
                    let comm = (n["comm"] as? String) ?? "?"
                    let cpu = (n["cpu"] as? Double) ?? 0
                    let kids = (n["kids"] as? [[String: Any]]) ?? []
                    if cpu < 1, kids.isEmpty {
                        if pending?.comm == comm { pending?.count += 1 } else { flush(); pending = (comm, 1) }
                        continue
                    }
                    flush()
                    if actRows.count < 40 {
                        // Cores, like everywhere else in this menu: a helper at 630%
                        // means nothing next to "Load: 8.5 / 14 cores" on the card.
                        let cpuTxt = cpu >= 1 ? String(format: "  ·  %.1f " + T("cores"), cpu / 100.0) : ""
                        actRows.append((comm + cpuTxt, actIcon(comm), indent))
                        actShown += 1
                    }
                    walk(kids, indent: indent + 1)
                }
                flush()
            }
            for a in agents {
                actTotal += 1
                let label = (a["agent"] as? String ?? "?").capitalized
                let tree = (a["cpu_tree"] as? Double) ?? 0
                let line = tree < 1
                    ? String(format: T("%@  ·  idle"), label)
                    : String(format: T("%@  ·  %.1f cores in its tree"), label, tree / 100.0)
                sessionRows.append(line)
                if actRows.count < 40 {
                    actRows.append((line, "sparkles", 0))
                    actShown += 1
                }
                walk((a["children"] as? [[String: Any]]) ?? [], indent: 1)
            }
        }
        if sessionRows.isEmpty {
            amenu.addItem(NSMenuItem(title: T("no AI session is running right now"),
                                     action: nil, keyEquivalent: ""))
        } else {
            for title in sessionRows {
                let it = NSMenuItem(title: title, action: nil, keyEquivalent: "")
                it.image = img("sparkles")
                amenu.addItem(it)
            }
            let tmenu = NSMenu()
            tmenu.autoenablesItems = false
            for (title, ic, indent) in actRows {
                let it = NSMenuItem(title: title, action: nil, keyEquivalent: "")
                it.indentationLevel = indent
                it.image = img(ic)
                tmenu.addItem(it)
            }
            if actTotal > actShown {
                tmenu.addItem(NSMenuItem(title: String(format: T("… %d more"),
                                                       actTotal - actShown),
                                         action: nil, keyEquivalent: ""))
            }
            let treesIt = NSMenuItem(title: T("Process tree details"), action: nil, keyEquivalent: "")
            treesIt.image = img("list.bullet.indent")
            treesIt.submenu = tmenu
            amenu.addItem(treesIt)
        }
        // LIVE from the recorder's daily JSONL (when the hooks are wired): the
        // freshest event per session. Events carry session ids, processes carry
        // pids, and nothing links them - so this is its own honest block, not a
        // fake per-branch annotation. Only the file's tail is read: a busy day
        // grows the log, and a menu open must stay instant.
        let live = recorderLiveCached()
        if !live.isEmpty {
            amenu.addItem(NSMenuItem.separator())
            amenu.addItem(NSMenuItem(title: T("Live (from hooks):"), action: nil, keyEquivalent: ""))
            for row in live.prefix(8) {
                let it = NSMenuItem(title: row, action: nil, keyEquivalent: "")
                it.indentationLevel = 1
                it.image = img("dot.radiowaves.left.and.right")
                amenu.addItem(it)
            }
        }
        let usageRow = claudeUsageText()
        let costRow = ccusageTodayText()
        if usageRow != nil || costRow != nil {
            amenu.addItem(NSMenuItem.separator())
        }
        if let usage = usageRow {
            let it = NSMenuItem(title: usage, action: nil, keyEquivalent: "")
            it.image = img("gauge.with.needle")
            amenu.addItem(it)
        }
        if let cost = costRow {
            let it = NSMenuItem(title: cost, action: nil, keyEquivalent: "")
            it.image = img("dollarsign.circle")
            // The headline stays one line; the breakdown lives one level down, so the
            // menu does not grow for people who only want the number.
            let rows = ccusageDetailRows(etaPauseMin: readSnap()?.eta)
            if !rows.isEmpty {
                let sub = NSMenu()
                sub.autoenablesItems = false
                for (icon, text) in rows {
                    let r = NSMenuItem(title: text, action: nil, keyEquivalent: "")
                    if icon.isEmpty {
                        r.attributedTitle = NSAttributedString(
                            string: text,
                            attributes: [.font: NSFont.boldSystemFont(ofSize: NSFont.smallSystemFontSize)])
                    } else {
                        r.image = img(icon)
                        r.indentationLevel = 1
                    }
                    sub.addItem(r)
                }
                it.submenu = sub
            }
            amenu.addItem(it)
        }
        refreshCcusageCache()
        actIt.submenu = amenu
        m.addItem(actIt)

        // APPLE FLEET: all Macs publishing to the shared folder, using the same files
        // read by CLI `fleet`. "Live" updates at ~1 min cadence (agent tick + folder sync).
        let fleetIt = NSMenuItem(title: T("Apple fleet"), action: nil, keyEquivalent: "")
        fleetIt.image = img("laptopcomputer")
        let fmenu = NSMenu()
        fmenu.autoenablesItems = false
        func frow(_ t: String) { fmenu.addItem(NSMenuItem(title: t, action: nil, keyEquivalent: "")) }
        // The menu reads a SNAPSHOT from cache (zero main-thread I/O); age is adjusted
        // from the read time.
        let cacheDrift = max(0, Date().timeIntervalSince(fleetCacheAt))
        // Read counters ONCE per menu open, not once per host.
        var hostStats: [String: [String: Int]] = [:]
        for m in fleetStats() { hostStats[m.host] = m.sum }
        if let hosts = fleetCache {
            if hosts.isEmpty {
                frow(T("no agent snapshots yet (agents publish about once a minute)"))
            }
            // Read this Mac's serial ONCE, not once per host: hardwareInfo() is a full
            // disk file read and used to run inside the per-host loop on every menu open.
            let mySerial = (hardwareInfo()["serial"] as? String) ?? ""
            for h0 in hosts {
                let h = FleetHost(name: h0.name, model: h0.model, serial: h0.serial,
                                  age: h0.age + cacheDrift, chip: h0.chip,
                                  chipStale: h0.chipStale,
                                  fans: h0.fans, watts: h0.watts, ramPct: h0.ramPct,
                                  level: h0.level, paused: h0.paused, onAC: h0.onAC,
                                  battPct: h0.battPct, battC: h0.battC)
                if h.age > 300 {
                    // System symbol, not emoji: emoji has its own color and width, so in
                    // dark mode it looks like a sticker and shifts columns.
                    let a = NSMutableAttributedString()
                    a.append(icon("exclamationmark.triangle", fallback: "!"))
                    a.append(NSAttributedString(string: "  \(h.name) — " + T("STALE - not reporting")
                                                + "  (" + fleetAge(h.age) + ")"))
                    let it = NSMenuItem(title: "", action: nil, keyEquivalent: "")
                    it.attributedTitle = a
                    fmenu.addItem(it)
                    continue
                }
                // COMPACT row: marker + name + highest temperature + battery temperature.
                // Full details appear on CLICK.
                var bits: [String] = []
                if let c = h.chip {
                    bits.append(String(format: h.chipStale ? "~%.0f °C" : "%.0f °C", c))
                }
                if let b = h.battC { bits.append(T("Battery") + String(format: " %.0f °C", b)) }
                let a = NSMutableAttributedString()
                a.append(icon(h.level >= 3 ? "flame.fill"
                              : h.level >= 2 ? "exclamationmark.triangle.fill"
                              : "laptopcomputer", fallback: ">"))
                let isMe = !mySerial.isEmpty && h.serial == mySerial
                a.append(NSAttributedString(
                    string: "  " + h.name,
                    attributes: [.font: isMe ? NSFont.boldSystemFont(ofSize: 13)
                                             : NSFont.menuFont(ofSize: 0)]))
                a.append(NSAttributedString(string: "   " + bits.joined(separator: "  ·  "),
                                            attributes: [.font: NSFont.menuFont(ofSize: 0)]))
                let it = NSMenuItem(title: "", action: #selector(fleetDetails(_:)), keyEquivalent: "")
                it.target = self
                it.attributedTitle = a
                // Counters for this host, used by the click popup.
                let st = hostStats[h.name] ?? [:]
                it.representedObject = [
                    "stat_pauses": String(st["pauses"] ?? 0),
                    "stat_resumes": String(st["resumes"] ?? 0),
                    "stat_kills": String(st["kills"] ?? 0),
                    "stat_awake": String(st["awake_released_hot"] ?? 0),
                    "name": h.name, "model": h.model, "serial": h.serial,
                    "age": fleetAge(h.age),
                    "chip": h.chip.map { String(format: h.chipStale ? "~%.1f °C" : "%.1f °C", $0) } ?? "-",
                    "batt": h.battC.map { String(format: "%.1f °C", $0) } ?? "-",
                    "fans": h.fans.map { "\($0) rpm" } ?? "-",
                    "watts": h.watts.map { String(format: "%.1f W", $0) } ?? "-",
                    "ram": h.ramPct.map { "\($0)%" } ?? "-",
                    "power": h.onAC ? T("AC adapter")
                                    : T("Battery") + (h.battPct.map { " \($0)%" } ?? ""),
                    "state": [T("Calm"), T("Warming up"), T("Hot"), T("Critical")][min(max(h.level, 0), 3)],
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
        // Keep the star action outside the submenu: the cheapest open-source currency
        // should be visible, not hidden in a nested menu.
        let pg = m.addItem(withTitle: T("Star it on GitHub…"), action: #selector(shareStar), keyEquivalent: "")
        pg.target = self
        pg.image = img("star")
        // suppi.pl works only in Polish (BLIK/bank transfers, no English version):
        // espresso in the Polish menu, the rest of the world goes to GitHub Sponsors.
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

        // Share note in the LANGUAGE SELECTED IN MENU, plus the UTM share link.
        // No Facebook: its sharer cuts text and requires login.
        let shareItem = NSMenuItem(title: T("Like the paladin? Pass it on!"), action: nil, keyEquivalent: "")
        shareItem.image = img("square.and.arrow.up")
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
        shareItem.submenu = pd
        m.addItem(shareItem)

        m.addItem(.separator())

        // FOOTER: color company logo, signature, and centered Quit.
        // Autostart moved up under the protection switch.
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

        // Separator divides credits from the exit action.
        m.addItem(.separator())
        // A person who cannot get the app working has to be able to leave without
        // hunting for a command in the README. That is the worst possible moment
        // for friction, so the way out sits in the menu, above the way to stop it.
        let uninstallIt = NSMenuItem(title: T("Uninstall coffee-paladin…"),
                                     action: #selector(uninstall), keyEquivalent: "")
        uninstallIt.target = self
        uninstallIt.image = img("trash")
        m.addItem(uninstallIt)
        // Left-aligned like every other item; no more centering.
        let quitIt = NSMenuItem(title: T("Quit coffee-paladin (protection stops)"),
                                action: #selector(quit), keyEquivalent: "q")
        quitIt.target = self
        quitIt.image = img("power")
        m.addItem(quitIt)
    }

    // --- keep awake (record request; daemon executes it with thermal fuse overriding)

    @objc func awakeOff() { Awake.set(nil); refreshAfterAction() }

    @objc func awakeTimer(_ sender: NSMenuItem) {
        guard let min = sender.representedObject as? Int else { return }
        let t = Date().timeIntervalSince1970
        Awake.set(["mode": "timer", "until": t + Double(min * 60), "set_at": t])
        refreshAfterAction()
    }

    @objc func awakeForever() { Awake.set(["mode": "forever"]); refreshAfterAction() }

    @objc func awakeUntil(_ sender: NSMenuItem) {
        guard let until = sender.representedObject as? Double else { return }
        let t = Date().timeIntervalSince1970
        guard until > t else { return }        // past hour = no-op
        Awake.set(["mode": "timer", "until": until, "set_at": t])
        refreshAfterAction()
    }

    /// Extend a RUNNING timer session, or start a new one for that many minutes.
    /// Count from the session end, not from "now"; otherwise adding 15 min could
    /// SHORTEN a session with an hour still left.
    @objc func awakeExtend(_ sender: NSMenuItem) {
        guard let min = sender.representedObject as? Int else { return }
        let t = Date().timeIntervalSince1970
        let cur = Awake.read()
        var baseTime = t
        if (cur["mode"] as? String) == "timer", let until = cur["until"] as? Double, until > t {
            baseTime = until
        }
        Awake.set(["mode": "timer", "until": baseTime + Double(min * 60), "set_at": t])
        refreshAfterAction()
    }

    @objc func awakeApp(_ sender: NSMenuItem) {
        guard let app = sender.representedObject as? String else { return }
        Awake.set(["mode": "app", "app": app])
        refreshAfterAction()
    }

    @objc func awakeDownload() { Awake.set(["mode": "download"]); refreshAfterAction() }

    // --- heavy jobs

    @objc func coresEfficiency() {
        GuardCfg.set(["job_cores_mode": "efficiency"])
        refreshAfterAction()
    }
    @objc func coresAll() {
        GuardCfg.set(["job_cores_mode": "all"])
        refreshAfterAction()
    }

    // --- phone push

    private var ntfyField: NSTextField?

    @objc func ntfyGenerate() { ntfyField?.stringValue = randomTopic() }

    @objc func toggleNtfy() {
        // Switch ON means topic is required (dialog); OFF clears topic and silences push.
        if GuardCfg.string("ntfy_topic", "").isEmpty {
            showModally { self.ntfyDialog() }
        } else {
            GuardCfg.set(["ntfy_topic": ""])
        }
    }

    /// Show a custom modal window from a custom-view menu item such as SwitchRow.
    /// That menu does NOT close itself and keeps tracking the mouse, so runModal
    /// conflicts with its event loop. This uses the same trick as HeaderRow.mouseUp.
    /// The paladin is CENTERED, with icon, title, body, optional custom view
    /// (text field, list), and button row. Return the clicked button index.
    ///
    /// Do not use NSAlert: a bare binary without an .app bundle has no app icon, so
    /// the alert falls back to a system icon that looks like an empty folder. Even after
    /// swapping in the paladin, NSAlert pins the icon to the left edge and will not center
    /// it. Since the paladin must stand centered everywhere, these windows are custom.
    ///
    /// Title and body wrap with margins, and their measured heights count toward window
    /// height. A one-line full-width title clipped sentence endings; the Polish quit
    /// title needed 338 pt with only 300 pt available.
    func paladinWindow(title: String, body: String, buttons: [String],
                      defaultIndex: Int = 0, accessoryView: NSView? = nil,
                      width windowWidth: CGFloat = 380) -> Int {
        let margin: CGFloat = 22

        func wrappedLabel(_ t: String, _ size: CGFloat, _ bold: Bool,
                      _ color: NSColor) -> (NSTextField, CGFloat) {
            // Non-breaking space before the hyphen: without it, wrapping could break
            // EXACTLY before " - " and the next line started with only the hyphen
            // ("OFF" / "- coffee-paladin entered mode...").
            let nonBreakingText = t.replacingOccurrences(of: " - ", with: "\u{00A0}- ")
            let p = NSTextField(wrappingLabelWithString: nonBreakingText)
            p.font = bold ? .boldSystemFont(ofSize: size) : .systemFont(ofSize: size)
            p.textColor = color
            p.alignment = .center
            p.preferredMaxLayoutWidth = windowWidth - 2 * margin
            return (p, p.sizeThatFits(NSSize(width: windowWidth - 2 * margin, height: 600)).height)
        }

        let (titleLabel, titleHeight) = wrappedLabel(title, 13, true, .labelColor)
        let (bodyLabel, bodyHeight) = wrappedLabel(body, 11, false, .secondaryLabelColor)
        let accessoryHeight: CGFloat = accessoryView.map { $0.frame.height + 14 } ?? 0

        let windowHeight = 18 + 44 + 8 + titleHeight + 10 + bodyHeight + accessoryHeight + 18 + 32 + 18
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: windowWidth, height: windowHeight),
                           styleMask: [.titled, .fullSizeContentView],
                           backing: .buffered, defer: false)
        win.titlebarAppearsTransparent = true
        win.titleVisibility = .hidden
        win.isMovableByWindowBackground = true
        win.level = .modalPanel
        win.center()
        let backgroundView = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: windowWidth, height: windowHeight))
        backgroundView.material = .popover
        backgroundView.state = .active
        win.contentView = backgroundView

        var y = windowHeight - 18 - 44
        let iconView = NSImageView(frame: NSRect(x: (windowWidth - 44) / 2, y: y, width: 44, height: 44))
        if let img = NSImage(contentsOfFile: base + "/paladin_welcome.png") { iconView.image = img }
        iconView.imageScaling = .scaleProportionallyUpOrDown
        backgroundView.addSubview(iconView)

        y -= 8 + titleHeight
        titleLabel.frame = NSRect(x: margin, y: y, width: windowWidth - 2 * margin, height: titleHeight)
        backgroundView.addSubview(titleLabel)

        y -= 10 + bodyHeight
        bodyLabel.frame = NSRect(x: margin, y: y, width: windowWidth - 2 * margin, height: bodyHeight)
        backgroundView.addSubview(bodyLabel)

        if let d = accessoryView {
            y -= 14 + d.frame.height
            d.frame = NSRect(x: (windowWidth - d.frame.width) / 2, y: y,
                             width: d.frame.width, height: d.frame.height)
            backgroundView.addSubview(d)
        }

        y -= 18 + 32
        let gap: CGFloat = 10
        // Width from CONTENT, not a constant. The Russian localized Quit anyway label
        // needs 162 pt; a fixed 130 pt clipped it halfway on the button that disables
        // thermal protection, the most serious decision in the program.
        let trialWidths = buttons.map { t -> CGFloat in
            let b = NSButton(title: t, target: nil, action: nil)
            b.bezelStyle = .rounded
            b.sizeToFit()
            return b.frame.width + 20
        }
        let buttonWidth = min(max(trialWidths.max() ?? 90, 90), 170)
        let xB = (windowWidth - (buttonWidth * CGFloat(buttons.count)
                          + gap * CGFloat(buttons.count - 1))) / 2
        // ORDER: macOS keeps the confirming button at the far RIGHT, and people
        // instinctively click the lower-right corner. Callers pass the list as "most
        // important first" because that reads naturally in code; draw it reversed.
        for (i, t) in buttons.enumerated() {
            let b = NSButton(title: t, target: self, action: #selector(closePaladinWindow(_:)))
            b.bezelStyle = .rounded
            b.tag = i
            let position = buttons.count - 1 - i          // 0 = far left
            b.frame = NSRect(x: xB + CGFloat(position) * (buttonWidth + gap), y: y,
                             width: buttonWidth, height: 32)
            if i == defaultIndex { b.keyEquivalent = "\r" }
            // Escape closes the window like Cancel, or like OK when there is only OK.
            if buttons.count == 1 || i == buttons.count - 1 { b.keyEquivalent = "\u{1b}" }
            if i == defaultIndex { b.keyEquivalent = "\r" }
            backgroundView.addSubview(b)
        }

        NSApp.activate(ignoringOtherApps: true)
        let result = NSApp.runModal(for: win)
        win.orderOut(nil)
        return result.rawValue
    }

    /// Add a button row.
    /// Width comes from CONTENT; Russian labels are about half longer than Polish ones.
    /// The confirming button stays far RIGHT per macOS, and Escape maps to Cancel.
    func buttonRow(_ backgroundView: NSView, _ windowWidth: CGFloat, _ y: CGFloat,
                        _ titles: [String], defaultIndex: Int, action: Selector) {
        let gap: CGFloat = 10
        let trialWidths = titles.map { t -> CGFloat in
            let b = NSButton(title: t, target: nil, action: nil)
            b.bezelStyle = .rounded
            b.sizeToFit()
            return b.frame.width + 20
        }
        let buttonWidth = min(max(trialWidths.max() ?? 90, 90), 170)
        let xB = (windowWidth - (buttonWidth * CGFloat(titles.count) + gap * CGFloat(titles.count - 1))) / 2
        for (i, t) in titles.enumerated() {
            let b = NSButton(title: t, target: self, action: action)
            b.bezelStyle = .rounded
            b.tag = i
            let position = titles.count - 1 - i
            b.frame = NSRect(x: xB + CGFloat(position) * (buttonWidth + gap), y: y, width: buttonWidth, height: 32)
            if i == titles.count - 1 { b.keyEquivalent = "\u{1b}" }
            if i == defaultIndex { b.keyEquivalent = "\r" }
            backgroundView.addSubview(b)
        }
    }

    @objc func closePaladinWindow(_ sender: NSButton) {
        NSApp.stopModal(withCode: NSApplication.ModalResponse(rawValue: sender.tag))
    }

    func showModally(_ action: @escaping () -> Void) {
        item.menu?.cancelTracking()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.12) { action() }
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
        let result = paladinWindow(
            title: T("Phone push (ntfy.sh)…"),
            body: T("The topic name is the ONLY protection: anyone who knows or guesses it can read your alerts and send fake ones. Click Generate for a random unguessable name. On your phone install the ntfy.sh app (from ntfy.sh - mind the lookalike apps) and subscribe to the same topic. Leave empty to disable."),
            buttons: ["OK", T("Cancel")], accessoryView: box)
        ntfyField = nil
        if result == 0 {
            // Topic goes straight into the URL. A space or newline makes curl send
            // nothing at all, silently; "#" and "?" publish to a SHORTER topic than the
            // user sees in the field, making it easier to guess. Reject immediately
            // instead of failing silently for weeks.
            let topic = field.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
            let allowedChars = CharacterSet(charactersIn:
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
            if !topic.isEmpty &&
                (topic.count > 64 || topic.rangeOfCharacter(from: allowedChars.inverted) != nil) {
                _ = paladinWindow(
                    title: T("This topic will not work"),
                    body: T("Use only letters, digits, _ and -, up to 64 characters. "
                        + "A space stops the push silently, and # or ? publish to a shorter topic "
                        + "than the one you typed."),
                    buttons: ["OK"])
                return
            }
            GuardCfg.set(["ntfy_topic": topic])
        }
    }

    // --- fleet name

    @objc func fleetNameDialog() {
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 300, height: 24))
        field.stringValue = GuardCfg.string("fleet_label", "")
        field.placeholderString = T("e.g. render-01, studio-mini, mbp-14")
        if paladinWindow(title: T("Name this Mac in the fleet…"),
                        body: T("With five identical MacBooks the system hostname says nothing. This name shows in the fleet table and menu on every machine. Empty = system hostname."),
                        buttons: ["OK", T("Cancel")], accessoryView: field) == 0 {
            GuardCfg.set(["fleet_label": field.stringValue.trimmingCharacters(in: .whitespaces)])
        }
    }

    // --- autostart

    @objc func toggleAutostart() { Autostart.set(!Autostart.enabled()) }

    /// Explain watch-only mode plainly before someone grants process-control authority.
    /// This is the key option for users who are cautious about letting the tool control
    /// their processes.
    /// One sentence per switch, said the moment it is flipped. Four paragraphs of
    /// explanation were read once and skipped forever; what the user needs is the
    /// consequence of the click he just made.
    @objc func explainDry() {
        _ = paladinWindow(title: T("Watch only"),
                          body: T("The paladin keeps measuring and writes to the log what it would pause, but it stops nothing until you switch this back on."),
                          buttons: ["OK"])
    }

    /// The numbers come from the daemon's own snapshot, not from the config file: the
    /// daemon clamps values it considers unsafe, so the file can promise a threshold
    /// that is not in force. With no snapshot there is nothing to promise at all.
    @objc func explainProtectionOn() {
        let s = readSnap()
        if s == nil || s!.stale {
            _ = paladinWindow(title: T("Thermal protection is on"),
                              body: T("no data - is coffee-paladin running?"), buttons: ["OK"])
            return
        }
        let pause = s!.thrPause ?? GuardCfg.double("soc_pause_c", 85)
        let resume = s!.thrResume ?? (pause - 9)
        _ = paladinWindow(title: T("Thermal protection is on"),
                          body: String(format: T("Above %.0f °C the paladin pauses heavy jobs and starts them again by itself at %.0f °C."),
                                       pause, resume),
                          buttons: ["OK"])
    }

    @objc func enableProtection() {
        GuardCfg.set(["dry_run": false])
        expectDryRun(false)
    }

    @objc func toggleNotify() { GuardCfg.set(["notify": !GuardCfg.bool("notify", true)]) }
    @objc func toggleDry() {
        let watchOnlyNow = !GuardCfg.bool("dry_run", true)
        // Turning protection OFF asks first. It used to write the config on the click and
        // explain afterwards, which left nothing to decide: by the time the window was up
        // the Mac was already unguarded. Turning it back ON needs no permission, only the
        // thresholds that are now in force.
        if watchOnlyNow {
            showModally {
                let kill = readSnap()?.thrKill ?? GuardCfg.double("soc_kill_c", 90)
                let answer = self.paladinWindow(
                    title: T("Turn thermal protection off?"),
                    body: String(format: T("The paladin will keep measuring and writing down what it would have paused, and will stop nothing at all, even above %.0f °C."), kill),
                    buttons: [T("Turn protection off"), T("Keep it on")],
                    defaultIndex: 1)
                guard answer == 0 else { return }
                GuardCfg.set(["dry_run": true])
                self.expectDryRun(true)
                self.refreshAfterAction()
            }
            return
        }
        GuardCfg.set(["dry_run": false])
        expectDryRun(false)
        showModally { self.explainProtectionOn() }
    }

    @objc func toggleSound() { GuardCfg.set(["sound": !GuardCfg.bool("sound", false)]) }
    @objc func toggleAwake() {
        GuardCfg.set(["keep_awake_auto": !GuardCfg.bool("keep_awake_auto", false)])
        refreshAfterAction()
    }

    @objc func toggleAwakeDisplay() {
        GuardCfg.set(["keep_awake_display": !GuardCfg.bool("keep_awake_display", false)])
        refreshAfterAction()
    }

    /// Restart the bar after a language change.
    /// The dictionary is selected once at startup. Exit with failure so launchd
    /// (KeepAlive.SuccessfulExit=false) brings us back.
    @objc func setLang(_ sender: NSMenuItem) {
        guard let code = sender.representedObject as? String, code != lang else { return }
        GuardCfg.set(["lang": code])
        exit(1)
    }

    @objc func barIconOnly() {
        prefs.enableNone()
        refreshAfterAction()
    }

    @objc func barIconAndChip() {
        prefs.enableChipOnly()
        refreshAfterAction()
    }

    @objc func showAllItems() {
        prefs.enableAll()
        refresh()
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
        // The daemon wakes on a command file in ~0.5 s, but the bar would wait until
        // the next fixed tick (5 s) before showing the effect. One narrow path handles
        // ALL commands, so every command gets quick confirmation for free.
        refreshAfterAction()
    }

    @objc func freeze() { send("freeze") }
    @objc func toggleFreeze(_ sender: Any?) {
        // Take state from the snapshot, not the click: the daemon executes the command,
        // so only its snapshot is proof. The daemon wakes on a command file in ~0.5 s,
        // and `send` schedules an extra quick bar refresh, so confirmation arrives in
        // about a second instead of after the full tick.
        let s = readSnap()
        if let s = s, !s.paused.isEmpty {
            let held = s.paused.count
            send("resume")
            // Resuming is not the end of the story: a chip still above the threshold
            // gets the same jobs paused again on the next reading, and without this
            // line that looks like the switch failed.
            showModally {
                _ = self.paladinWindow(title: T("Jobs resumed"),
                                       body: String(format: T("Held jobs (%d) are running again; if the chip is still hot the paladin pauses them again on its next reading."),
                                                    held),
                                       buttons: ["OK"])
            }
            return
        }
        // Manual freeze is the one place where users consciously stop THEIR work.
        // Before doing that, they must see exactly WHAT will stop and what to expect;
        // otherwise the switch is a blind shot.
        showModally { [weak self] in
            guard let self = self else { return }
            guard let selected = self.confirmFreeze(s) else { return }   // canceled
            if selected.isEmpty {
                self.send("freeze")                       // nothing selectable
            } else {
                self.send("freeze:" + selected.map(String.init).joined(separator: ","))
            }
        }
    }

    /// Confirm manual freeze with the exact processes that will stop.
    /// Users can uncheck individual processes. The list comes from `freeze_candidates`
    /// in the snapshot, the same set the daemon will act on, not from "top CPU".
    ///
    /// Custom window, not NSAlert: alert pins the icon to the left edge and reserves a
    /// header strip for it. The paladin must stand centered above the title.
    /// Return nil on cancel, or PID list; empty list means freeze every eligible process.
    func confirmFreeze(_ s: Snap?) -> [Int]? {
        let candidates = s?.freezeCandidates ?? []
        let windowWidth: CGFloat = 360
        let margin: CGFloat = 20
        let rowHeight: CGFloat = 20

        func paragraph(_ text: String, _ size: CGFloat, _ color: NSColor) -> (NSTextField, CGFloat) {
            let p = NSTextField(wrappingLabelWithString: text)
            p.font = .systemFont(ofSize: size)
            p.textColor = color
            p.alignment = .left
            p.preferredMaxLayoutWidth = windowWidth - 2 * margin
            return (p, p.sizeThatFits(NSSize(width: windowWidth - 2 * margin, height: 400)).height)
        }

        let (a1, h1) = paragraph(T("A freeze is not a kill. The process stops between two "
            + "instructions, keeps its memory and its open files, and carries on from the "
            + "same place when you switch this off. It is safe."), 11, .labelColor)
        let (a2, h2) = paragraph(T("What a freeze does NOT protect: anything waiting on the "
            + "network or watching a clock will notice the gap. A download or an upload can "
            + "drop, a server can disconnect you, a video call freezes, a game stops "
            + "responding."), 11, .secondaryLabelColor)
        let (a3, h3) = paragraph(T("The paladin will NEVER touch the system, Finder, your "
            + "terminal or your AI agent."), 11, .labelColor)

        let listHeight: CGFloat = candidates.isEmpty ? 0
            : rowHeight * CGFloat(candidates.count + 1) + 8
        let (emptyMessage, emptyHeight) = paragraph(T("Nothing heavy is running right now. Anything that "
            + "gets heavy will be frozen until you switch this back off."), 11, .secondaryLabelColor)
        let emptyBlockHeight: CGFloat = candidates.isEmpty ? emptyHeight + 10 : 0

        let title = NSTextField(wrappingLabelWithString: T("Freeze heavy jobs now?"))
        title.font = .boldSystemFont(ofSize: 13)
        title.alignment = .center
        title.preferredMaxLayoutWidth = windowWidth - 2 * margin
        let titleHeight = title.sizeThatFits(NSSize(width: windowWidth - 2 * margin, height: 200)).height

        let windowHeight = 18 + 44 + 8 + titleHeight + 12 + listHeight + emptyBlockHeight
                  + h1 + 10 + h2 + 10 + h3 + 16 + 32 + 18
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: windowWidth, height: windowHeight),
                           styleMask: [.titled, .fullSizeContentView],
                           backing: .buffered, defer: false)
        win.titlebarAppearsTransparent = true
        win.titleVisibility = .hidden
        win.isMovableByWindowBackground = true
        win.level = .modalPanel
        win.center()
        let backgroundView = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: windowWidth, height: windowHeight))
        backgroundView.material = .popover
        backgroundView.state = .active
        win.contentView = backgroundView

        var y = windowHeight - 18 - 44
        let iconView = NSImageView(frame: NSRect(x: (windowWidth - 44) / 2, y: y, width: 44, height: 44))
        if let img = NSImage(contentsOfFile: base + "/paladin_welcome.png") { iconView.image = img }
        iconView.imageScaling = .scaleProportionallyUpOrDown
        backgroundView.addSubview(iconView)

        y -= 8 + titleHeight
        title.frame = NSRect(x: margin, y: y, width: windowWidth - 2 * margin, height: titleHeight)
        backgroundView.addSubview(title)

        var toggles: [NSButton] = []
        y -= 12
        if candidates.isEmpty {
            y -= emptyHeight + 10
            emptyMessage.frame = NSRect(x: margin, y: y, width: windowWidth - 2 * margin, height: emptyHeight)
            backgroundView.addSubview(emptyMessage)
        } else {
            y -= rowHeight
            let allToggle = NSButton(checkboxWithTitle: T("Freeze all of them"),
                                     target: self, action: #selector(toggleAll(_:)))
            allToggle.state = .on
            allToggle.font = .systemFont(ofSize: 12, weight: .medium)
            allToggle.frame = NSRect(x: margin, y: y, width: windowWidth - 2 * margin, height: rowHeight)
            backgroundView.addSubview(allToggle)
            for k in candidates {
                y -= rowHeight
                let c = NSButton(checkboxWithTitle: "\(k.name)   \(k.cpu)% CPU   pid \(k.pid)",
                                 target: nil, action: nil)
                c.state = .on
                c.tag = k.pid
                c.font = .systemFont(ofSize: 11)
                // Gray, so process selection does not shout louder than the decision.
                c.contentTintColor = .secondaryLabelColor
                c.frame = NSRect(x: margin + 16, y: y, width: windowWidth - 2 * margin - 16, height: rowHeight)
                backgroundView.addSubview(c)
                toggles.append(c)
            }
            y -= 8
            processCheckboxes = toggles
        }

        for (p, h) in [(a1, h1), (a2, h2), (a3, h3)] {
            y -= h
            p.frame = NSRect(x: margin, y: y, width: windowWidth - 2 * margin, height: h)
            backgroundView.addSubview(p)
            y -= 10
        }

        y -= 6 + 32
        buttonRow(backgroundView, windowWidth, y, [T("Freeze"), T("Cancel")], defaultIndex: 0,
                       action: #selector(closeFreezeDialog(_:)))

        NSApp.activate(ignoringOtherApps: true)
        let result = NSApp.runModal(for: win)
        win.orderOut(nil)
        defer { processCheckboxes = [] }
        guard result.rawValue == 0 else { return nil }
        if toggles.isEmpty { return [] }
        return toggles.filter { $0.state == .on }.map { $0.tag }
    }

    @objc func closeFreezeDialog(_ sender: NSButton) {
        NSApp.stopModal(withCode: NSApplication.ModalResponse(rawValue: sender.tag))
    }

    @objc func toggleAll(_ sender: NSButton) {
        for c in processCheckboxes { c.state = sender.state }
    }
    @objc func resume() { send("resume") }

    @objc func reportDialog() {
        // Custom window, not NSAlert: alert reserves a header strip even with empty text,
        // leaving a large blank rectangle at the top.
        let windowWidth: CGFloat = 300
        let note = NSTextField(wrappingLabelWithString:
            T("Included: hardware, battery, sudden shutdowns, interventions, measurement timeline."))
        note.font = .systemFont(ofSize: 11)
        note.textColor = .secondaryLabelColor
        note.alignment = .center
        note.preferredMaxLayoutWidth = windowWidth - 32
        let noteHeight = note.sizeThatFits(NSSize(width: windowWidth - 32, height: 200)).height

        let windowHeight: CGFloat = 16 + 44 + 6 + 18 + 4 + 15 + 12 + 24 + 6 + 24 + 10 + 20
                            + 8 + noteHeight + 14 + 32 + 16
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: windowWidth, height: windowHeight),
                           styleMask: [.titled, .fullSizeContentView],
                           backing: .buffered, defer: false)
        win.titlebarAppearsTransparent = true
        win.titleVisibility = .hidden
        win.isMovableByWindowBackground = true
        win.level = .modalPanel
        win.center()
        let backgroundView = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: windowWidth, height: windowHeight))
        backgroundView.material = .popover
        backgroundView.state = .active
        win.contentView = backgroundView

        var y = windowHeight - 16 - 44
        let iconView = NSImageView(frame: NSRect(x: (windowWidth - 44) / 2, y: y, width: 44, height: 44))
        if let img = NSImage(contentsOfFile: base + "/paladin_welcome.png") { iconView.image = img }
        iconView.imageScaling = .scaleProportionallyUpOrDown
        backgroundView.addSubview(iconView)

        y -= 6 + 18
        let title = NSTextField(labelWithString: T("Export report for a repair shop"))
        title.font = .boldSystemFont(ofSize: 13)
        title.alignment = .center
        title.frame = NSRect(x: 0, y: y, width: windowWidth, height: 18)
        backgroundView.addSubview(title)

        y -= 4 + 15
        let subtitle = NSTextField(labelWithString: T("Pick the report period."))
        subtitle.font = .systemFont(ofSize: 11)
        subtitle.textColor = .secondaryLabelColor
        subtitle.alignment = .center
        subtitle.frame = NSRect(x: 0, y: y, width: windowWidth, height: 15)
        backgroundView.addSubview(subtitle)

        let pairWidth: CGFloat = 42 + 4 + 118
        let x0 = (windowWidth - pairWidth) / 2
        y -= 12 + 24
        let fromPicker = NSDatePicker(frame: NSRect(x: x0 + 46, y: y, width: 118, height: 24))
        fromPicker.datePickerStyle = .textFieldAndStepper
        fromPicker.datePickerElements = .yearMonthDay
        fromPicker.dateValue = Date().addingTimeInterval(-14 * 86400)
        backgroundView.addSubview(fromPicker)
        let fromLabel = NSTextField(labelWithString: T("From:"))
        fromLabel.frame = NSRect(x: x0, y: y + 4, width: 42, height: 16)
        fromLabel.alignment = .right
        backgroundView.addSubview(fromLabel)

        y -= 6 + 24
        let toPicker = NSDatePicker(frame: NSRect(x: x0 + 46, y: y, width: 118, height: 24))
        toPicker.datePickerStyle = .textFieldAndStepper
        toPicker.datePickerElements = .yearMonthDay
        toPicker.dateValue = Date()
        // Without this, a reversed range went straight to thermal-report and returned empty.
        toPicker.maxDate = Date()
        fromPicker.maxDate = Date()
        backgroundView.addSubview(toPicker)
        let toLabel = NSTextField(labelWithString: T("To:"))
        toLabel.frame = NSRect(x: x0, y: y + 4, width: 42, height: 16)
        toLabel.alignment = .right
        backgroundView.addSubview(toLabel)

        y -= 10 + 20
        let allHistory = NSButton(checkboxWithTitle: T("Everything on record"), target: nil, action: nil)
        allHistory.sizeToFit()
        allHistory.frame = NSRect(x: (windowWidth - allHistory.frame.width) / 2, y: y,
                              width: allHistory.frame.width, height: 20)
        backgroundView.addSubview(allHistory)

        y -= 8 + noteHeight
        note.frame = NSRect(x: 16, y: y, width: windowWidth - 32, height: noteHeight)
        backgroundView.addSubview(note)

        y -= 14 + 32
        let buttonWidth: CGFloat = 80, gap: CGFloat = 8
        let xB = (windowWidth - (3 * buttonWidth + 2 * gap)) / 2
        for (i, buttonTitle) in ["PDF", "TXT", T("Cancel")].enumerated() {
            let b = NSButton(title: buttonTitle, target: self, action: #selector(closeReportDialog(_:)))
            b.bezelStyle = .rounded
            b.tag = i
            b.frame = NSRect(x: xB + CGFloat(i) * (buttonWidth + gap), y: y, width: buttonWidth, height: 32)
            if i == 0 { b.keyEquivalent = "\r" }
            backgroundView.addSubview(b)
        }

        NSApp.activate(ignoringOtherApps: true)
        let result = NSApp.runModal(for: win)
        win.orderOut(nil)
        guard result.rawValue != 2 else { return }
        let f = DateFormatter()
        // en_US_POSIX is required: Thai region would output Buddhist-calendar dates
        // (2569-08-02), while Saudi region would output Arabic digits. The report would
        // receive an unreadable range and fall back to default 7 days or return empty.
        f.locale = Locale(identifier: "en_US_POSIX")
        f.calendar = Calendar(identifier: .gregorian)
        f.timeZone = TimeZone.current
        f.dateFormat = "yyyy-MM-dd"
        let rangeArgs: [String] = allHistory.state == .on
            ? ["--all"]
            : ["--from", f.string(from: fromPicker.dateValue), "--to", f.string(from: toPicker.dateValue)]
        report(pdf: result.rawValue == 0, rangeArgs: rangeArgs)
    }

    @objc func fleetDetails(_ sender: NSMenuItem) {
        // Custom window instead of NSAlert: everything centered, no empty reserved strips.
        guard let d = sender.representedObject as? [String: String] else { return }
        var lines: [String] = []
        if let m = d["model"], !m.isEmpty { lines.append(m) }
        if let s = d["serial"], !s.isEmpty { lines.append("SN " + s) }
        lines.append(T("Chip") + ": " + (d["chip"] ?? "-") + "   ·   "
                     + T("Battery") + ": " + (d["batt"] ?? "-"))
        lines.append(T("Fans") + ": " + (d["fans"] ?? "-") + "   ·   "
                     + T("draw") + ": " + (d["watts"] ?? "-"))
        lines.append("RAM: " + (d["ram"] ?? "-") + "   ·   " + (d["power"] ?? "-"))
        lines.append(T("State") + ": " + (d["state"] ?? "-"))
        if let p = d["paused"], !p.isEmpty { lines.append(T("paused") + ": " + p) }
        lines.append(T("Snapshot") + ": " + (d["age"] ?? "-"))
        let counts = ["stat_pauses", "stat_resumes", "stat_kills", "stat_awake"].map { d[$0] ?? "0" }
        if counts.contains(where: { $0 != "0" }) {
            lines.append("")
            lines.append(T("What the guard did here (total)"))
            lines.append(T("Heavy jobs paused") + ": " + counts[0])
            lines.append(T("Jobs resumed after cooling") + ": " + counts[1])
            lines.append(T("Jobs terminated at the kill threshold") + ": " + counts[2])
            lines.append(T("Sleep-lock releases due to heat") + ": " + counts[3])
        }

        let windowWidth: CGFloat = 240
        let text = NSTextField(wrappingLabelWithString: lines.joined(separator: "\n"))
        text.font = .systemFont(ofSize: 12)
        text.alignment = .center
        text.preferredMaxLayoutWidth = windowWidth - 24
        let textHeight = text.sizeThatFits(NSSize(width: windowWidth - 24, height: 400)).height

        let windowHeight: CGFloat = 16 + 44 + 6 + 18 + 8 + textHeight + 14 + 32 + 16
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: windowWidth, height: windowHeight),
                           styleMask: [.titled, .fullSizeContentView],
                           backing: .buffered, defer: false)
        win.titlebarAppearsTransparent = true
        win.titleVisibility = .hidden
        win.isMovableByWindowBackground = true
        win.level = .modalPanel
        win.center()
        let backgroundView = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: windowWidth, height: windowHeight))
        backgroundView.material = .popover
        backgroundView.state = .active
        win.contentView = backgroundView

        var y = windowHeight - 16 - 44
        let iconView = NSImageView(frame: NSRect(x: (windowWidth - 44) / 2, y: y, width: 44, height: 44))
        if let img = NSImage(contentsOfFile: base + "/paladin_welcome.png") { iconView.image = img }
        iconView.imageScaling = .scaleProportionallyUpOrDown
        backgroundView.addSubview(iconView)

        y -= 6 + 18
        let title = NSTextField(labelWithString: d["name"] ?? "?")
        title.font = .boldSystemFont(ofSize: 13)
        title.alignment = .center
        title.frame = NSRect(x: 0, y: y, width: windowWidth, height: 18)
        backgroundView.addSubview(title)

        y -= 8 + textHeight
        text.frame = NSRect(x: 12, y: y, width: windowWidth - 24, height: textHeight)
        backgroundView.addSubview(text)

        y -= 14 + 32
        let ok = NSButton(title: "OK", target: self, action: #selector(closeReportDialog(_:)))
        ok.bezelStyle = .rounded
        ok.tag = 0
        ok.keyEquivalent = "\r"
        ok.frame = NSRect(x: (windowWidth - 90) / 2, y: y, width: 90, height: 32)
        backgroundView.addSubview(ok)

        NSApp.activate(ignoringOtherApps: true)
        NSApp.runModal(for: win)
        win.orderOut(nil)
    }

    @objc func closeReportDialog(_ sender: NSButton) {
        NSApp.stopModal(withCode: NSApplication.ModalResponse(rawValue: sender.tag))
    }

    func report(pdf: Bool, rangeArgs: [String] = ["--days", "14"]) {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: reportBin)
        p.arguments = rangeArgs + (pdf ? ["--pdf"] : [])
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

    /// Restart the daemon through launchd from the "no data" rescue menu item.
    @objc func restartGuard() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        p.arguments = ["kickstart", "-k", "gui/\(getuid())/pl.pawel.coffee-paladin"]
        try? p.run()
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self] in self?.refresh() }
    }

    @objc func openLog() { NSWorkspace.shared.open(URL(fileURLWithPath: logPath)) }

    // Share note in the current menu language; one key, translations in DICTS.
    private var shareNote: String {
        T("Is your Mac heating up with AI and renders? coffee-paladin watches the battery (temperature and charge), the chip (CPU) and the GPU. It pauses heavy jobs when the system overheats and resumes them by itself once the temperature drops, so you can sleep peacefully (literally!). Open source, free, for you:")
    }

    @objc func shareX() {
        // Separate shorter text for X because of the 280-character limit.
        var c = URLComponents(string: "https://x.com/intent/post")!
        // URLComponents handles percent-encoding; localized characters do not break links.
        c.queryItems = [URLQueryItem(name: "text",
                                     value: String(format: T("Is your Mac heating up with AI and renders? coffee-paladin watches battery, chip and GPU temperatures. It pauses heavy jobs and resumes them by itself once the temperature drops.\n\nOpen source, free, for you:\n%@\n\n#panbookovsky #macbook #protect #temperature #guard"),
                                                   shareLink()))]
        if let u = c.url { NSWorkspace.shared.open(u) }
    }

    @objc func shareMail() {
        // Personal "to a colleague" tone with paladin GIF attached. mailto cannot attach
        // files, so compose through Mail.app (osascript).
        // Arguments go through argv, avoiding quote-escaping trouble.
        let topic = T("you have to see this: coffee-paladin")
        let body = String(format: T("Hey,\n\nI found something you need on your Mac: coffee-paladin. It watches the chip, GPU and battery temperatures, and when things get hot it pauses heavy jobs and resumes them by itself once the machine cools down.\n\nIt is damn good, because the pause is lossless (the process freezes and continues from the same spot), it sends nothing anywhere, and it is free, open source:\n%@\n\nThe knight with the coffee in the attachment is its mascot.\n\nCheers!"), shareLink())
            .replacingOccurrences(of: "\\n", with: "\n")
        let gif = base + "/paladin_welcome.gif"
        var script = [
            "on run argv",
            "tell application \"Mail\"",
            "set msg to make new outgoing message with properties {subject:(item 1 of argv), content:(item 2 of argv), visible:true}",
        ]
        if FileManager.default.fileExists(atPath: gif) {
            script.append("tell msg to make new attachment with properties {file name:(POSIX file (item 3 of argv))} at after the last paragraph of content")
        }
        script += ["activate", "end tell", "end run"]
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        var argumentsList: [String] = []
        for line in script { argumentsList += ["-e", line] }
        argumentsList += [topic, body, gif]
        p.arguments = argumentsList
        try? p.run()
    }

    @objc func shareCopy() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(shareNote + "\n" + shareLink(), forType: .string)
    }

    @objc func sponsorGithub() {
        if let u = urlWithUTM("https://github.com/sponsors/pawelkwaczynski") { NSWorkspace.shared.open(u) }
    }

    @objc func shareStar() {
        if let u = urlWithUTM("https://github.com/pawelkwaczynski/coffee-paladin", medium: "share") {
            NSWorkspace.shared.open(u)
        }
    }

    /// Show inverse stats versus keep-awake competitors.
    /// Count not "how long the Mac stayed awake", but how many times the safety net
    /// acted. This is the one statistic an app without a thermal fuse cannot have.
    @objc func openStats() {
        let snap = readSnap()
        let labels: [(String, String)] = [
            (T("Heavy jobs paused"), "pauses"),
            (T("Jobs resumed after cooling"), "resumes"),
            (T("Jobs terminated at the kill threshold"), "kills"),
            (T("Sleep-lock releases due to heat"), "awake_released_hot"),
        ]
        func dateText(_ epoch: Int?) -> String {
            guard let e = epoch, e > 0 else { return "?" }
            let f = DateFormatter()
            f.dateStyle = .short
            f.timeStyle = .short
            return f.string(from: Date(timeIntervalSince1970: Double(e)))
        }

        var lines: [String] = []
        let ses = snap?.statsSession ?? [:]
        let sum = snap?.statsTotal ?? [:]

        let sessionEmpty = labels.allSatisfy { (ses[$0.1] ?? 0) == 0 }
        let totalEmpty = !labels.contains { (sum[$0.1] ?? 0) > 0 }
        // "Nothing here" is TRUE only when history agrees. A fresh daemon
        // session over months of counters used to print the good news right
        // above 584 interventions - a dialog contradicting itself two lines
        // apart (caught by the owner on a screenshot).
        if sessionEmpty && totalEmpty {
            lines.append(T("Nothing here - and that is good news: your Mac has not been overheating."))
        } else if sessionEmpty {
            // The date belongs here too: "no interventions yet" reads very
            // differently after two minutes and after two days.
            lines.append(String(format: T("Since the guard started (%@): no interventions yet."),
                                dateText(ses["since"])))
        } else {
            lines.append(String(format: T("Since the guard started (%@)"), dateText(ses["since"])))
            lines.append("")
            lines.append(contentsOf: labels.map { "\($0.0):  \(ses[$0.1] ?? 0)" })
        }
        if !totalEmpty {
            lines.append("")
            // "counting since", not "since install": the counter starts at the first
            // event it books, and pauses logged before that are not in these numbers.
            lines.append(String(format: T("All time on this Mac, counting since %@"), dateText(sum["since"])))
            lines.append("")
            lines.append(contentsOf: labels.map { "\($0.0):  \(sum[$0.1] ?? 0)" })
            // The books must balance: paused minus resumed minus killed leaves
            // pauses that ended some other way, and an unexplained 12 reads
            // like a bug even when it is not one.
            let other = (sum["pauses"] ?? 0) - (sum["resumes"] ?? 0) - (sum["kills"] ?? 0)
            if other > 0 {
                lines.append(String(format:
                    T("Pause ended another way (manual resume, job exited, daemon restart): %d"), other))
            }
        }

        // FLEET: one line per other Mac, never a sum. Adding the machines together
        // reprinted this Mac's own numbers under a second heading when the other
        // machine had nothing to report, which is how the window ended up saying the
        // same four figures twice.
        // Which entry is THIS Mac: the daemon publishes fleet_label when the user set
        // one, and the hostname otherwise (guard.py, fleet snapshot). Comparing only
        // against the system hostname put a named local Mac under "Other Macs" and
        // printed its numbers twice, which is the very thing this block exists to stop.
        let myLabel = GuardCfg.string("fleet_label", "").trimmingCharacters(in: .whitespaces)
        let myNames = Set([myLabel, Host.current().localizedName ?? "",
                           ProcessInfo.processInfo.hostName].filter { !$0.isEmpty })
        let others = fleetStats().filter { !myNames.contains($0.host) }
        if !others.isEmpty {
            let speaking = others.filter { m in labels.contains { (m.sum[$0.1] ?? 0) > 0 } }
            lines.append("")
            lines.append(T("Other Macs"))
            lines.append("")
            if speaking.isEmpty {
                lines.append(T("no interventions there yet"))
            } else {
                for m in speaking {
                    let counts = labels.map { "\(m.sum[$0.1] ?? 0)" }.joined(separator: " / ")
                    lines.append(m.age > 300
                        ? String(format: T("%@:  %@  (last report %@ ago)"), m.host, counts,
                                 fmtDur(max(1, Int(m.age / 60))))
                        : "\(m.host):  \(counts)")
                }
                lines.append(T("paused / resumed / terminated / sleep-lock released"))
            }
        }

        showModally { [weak self] in
            _ = self?.paladinWindow(title: T("Guard statistics"),
                                   body: lines.joined(separator: "\n"),
                                   buttons: ["OK"], width: 460)
        }
    }

    @objc func openGuide() { Guide.shared.show() }

    @objc func openIssues() {
        if let u = urlWithUTM("https://github.com/pawelkwaczynski/coffee-paladin/issues") { NSWorkspace.shared.open(u) }
    }

    @objc func buyCoffee() {
        if let u = urlWithUTM("https://suppi.pl/panbookovsky") { NSWorkspace.shared.open(u) }
    }

    /// Quit means END THE PROGRAM, not just hide the icon.
    /// Stop both daemon and menu bar. "Close the bar" used to leave the daemon alive,
    /// which misled people in the opposite direction: they thought protection was off
    /// while it still ran. Now label and effect match, and we ask before the irreversible
    /// step.
    /// Remove the whole thing, with the data question asked separately.
    ///
    /// Two windows, not three buttons in one: "Uninstall" and "Uninstall and
    /// delete everything" side by side are one slip apart, and the second one
    /// destroys the black box - the measurement history that is the only
    /// evidence left after a Mac dies under load.
    @objc func uninstall() {
        let windowWidth: CGFloat = 380, margin: CGFloat = 20
        let title = NSTextField(wrappingLabelWithString: T("Uninstall coffee-paladin?"))
        title.font = .boldSystemFont(ofSize: 13)
        title.alignment = .center
        title.preferredMaxLayoutWidth = windowWidth - 2 * margin
        let titleHeight = title.sizeThatFits(NSSize(width: windowWidth - 2 * margin, height: 200)).height

        let body = NSTextField(wrappingLabelWithString: T(
            "Goes away: the daemon and the menu bar (they stop starting at login), the app, "
            + "the heat, safe-run, thermal-report and fleet commands, and the skill for AI agents.\n\n"
            + "Stays: the measurement history and the black box in ~/.coffee-paladin. That is what "
            + "a service centre asks for when a Mac dies under load."))
        body.font = .systemFont(ofSize: 11)
        body.textColor = .secondaryLabelColor
        body.preferredMaxLayoutWidth = windowWidth - 2 * margin
        let bodyHeight = body.sizeThatFits(NSSize(width: windowWidth - 2 * margin, height: 400)).height

        let purgeBox = NSButton(checkboxWithTitle: T("Delete the history and the black box too"),
                                target: nil, action: nil)
        purgeBox.state = .off
        purgeBox.font = .systemFont(ofSize: 12)

        let windowHeight = 18 + 44 + 8 + titleHeight + 10 + bodyHeight + 14 + 20 + 18 + 32 + 18
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: windowWidth, height: windowHeight),
                           styleMask: [.titled, .fullSizeContentView], backing: .buffered, defer: false)
        win.titlebarAppearsTransparent = true
        win.titleVisibility = .hidden
        win.isMovableByWindowBackground = true
        win.level = .modalPanel
        win.center()
        let backgroundView = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: windowWidth, height: windowHeight))
        backgroundView.material = .popover
        backgroundView.state = .active
        win.contentView = backgroundView

        var y = windowHeight - 18 - 44
        let iconView = NSImageView(frame: NSRect(x: (windowWidth - 44) / 2, y: y, width: 44, height: 44))
        if let img = NSImage(contentsOfFile: base + "/paladin_welcome.png") { iconView.image = img }
        iconView.imageScaling = .scaleProportionallyUpOrDown
        backgroundView.addSubview(iconView)

        y -= 8 + titleHeight
        title.frame = NSRect(x: margin, y: y, width: windowWidth - 2 * margin, height: titleHeight)
        backgroundView.addSubview(title)

        y -= 10 + bodyHeight
        body.frame = NSRect(x: margin, y: y, width: windowWidth - 2 * margin, height: bodyHeight)
        backgroundView.addSubview(body)

        y -= 14 + 20
        purgeBox.frame = NSRect(x: margin, y: y, width: windowWidth - 2 * margin, height: 20)
        backgroundView.addSubview(purgeBox)

        y -= 18 + 32
        // Enter must not uninstall anything.
        buttonRow(backgroundView, windowWidth, y, [T("Uninstall"), T("Cancel")], defaultIndex: 1,
                  action: #selector(closeFreezeDialog(_:)))
        NSApp.activate(ignoringOtherApps: true)
        let result = NSApp.runModal(for: win)
        win.orderOut(nil)
        guard result.rawValue == 0 else { return }

        let purge = purgeBox.state == .on
        if purge && !confirmPurge() { return }
        runUninstaller(purge: purge)
    }

    /// The second question, asked only when the first one was answered with the
    /// box ticked. Deleting the history is the one step nothing can undo.
    private func confirmPurge() -> Bool {
        let windowWidth: CGFloat = 380, margin: CGFloat = 20
        let title = NSTextField(wrappingLabelWithString: T("Delete the black box as well?"))
        title.font = .boldSystemFont(ofSize: 13)
        title.alignment = .center
        title.preferredMaxLayoutWidth = windowWidth - 2 * margin
        let titleHeight = title.sizeThatFits(NSSize(width: windowWidth - 2 * margin, height: 200)).height

        let body = NSTextField(wrappingLabelWithString: T(
            "Every measurement, every pause and every hard shutdown this Mac recorded goes with it. "
            + "This cannot be undone, and it is the record a service centre or a warranty claim asks "
            + "for. Uninstalling without this leaves the files untouched and costs nothing."))
        body.font = .systemFont(ofSize: 11)
        body.textColor = .secondaryLabelColor
        body.preferredMaxLayoutWidth = windowWidth - 2 * margin
        let bodyHeight = body.sizeThatFits(NSSize(width: windowWidth - 2 * margin, height: 400)).height

        let windowHeight = 18 + 44 + 8 + titleHeight + 10 + bodyHeight + 18 + 32 + 18
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: windowWidth, height: windowHeight),
                           styleMask: [.titled, .fullSizeContentView], backing: .buffered, defer: false)
        win.titlebarAppearsTransparent = true
        win.titleVisibility = .hidden
        win.isMovableByWindowBackground = true
        win.level = .modalPanel
        win.center()
        let backgroundView = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: windowWidth, height: windowHeight))
        backgroundView.material = .popover
        backgroundView.state = .active
        win.contentView = backgroundView

        var y = windowHeight - 18 - 44
        let iconView = NSImageView(frame: NSRect(x: (windowWidth - 44) / 2, y: y, width: 44, height: 44))
        iconView.image = NSImage(systemSymbolName: "exclamationmark.triangle.fill", accessibilityDescription: nil)
        iconView.contentTintColor = .systemOrange
        iconView.imageScaling = .scaleProportionallyUpOrDown
        backgroundView.addSubview(iconView)

        y -= 8 + titleHeight
        title.frame = NSRect(x: margin, y: y, width: windowWidth - 2 * margin, height: titleHeight)
        backgroundView.addSubview(title)

        y -= 10 + bodyHeight
        body.frame = NSRect(x: margin, y: y, width: windowWidth - 2 * margin, height: bodyHeight)
        backgroundView.addSubview(body)

        y -= 18 + 32
        buttonRow(backgroundView, windowWidth, y, [T("Delete everything"), T("Cancel")], defaultIndex: 1,
                  action: #selector(closeFreezeDialog(_:)))
        NSApp.activate(ignoringOtherApps: true)
        let result = NSApp.runModal(for: win)
        win.orderOut(nil)
        return result.rawValue == 0
    }

    /// Start the uninstaller in a session of its own.
    ///
    /// Its first act is to boot out this very job, and launchd takes the whole
    /// job down, children included. A plain child would therefore die halfway
    /// through and leave a Mac with no daemon and half the files still in place.
    private func runUninstaller(purge: Bool) {
        let script = base + "/uninstall.sh"
        guard FileManager.default.isReadableFile(atPath: script) else {
            FileHandle.standardError.write(
                "uninstall.sh not found at \(script)\n".data(using: .utf8)!)
            return
        }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        p.arguments = ["-c",
                       "import os, subprocess, sys; os.setsid(); "
                       + "subprocess.Popen(['/bin/bash'] + sys.argv[1:])",
                       script]
        if purge { p.arguments?.append("--purge") }
        try? p.run()
    }

    @objc func quit() {
        // Custom window, as with manual freeze: this is the most serious decision in
        // the menu, so the paladin stands centered instead of pinned to the left edge
        // like in NSAlert.
        let windowWidth: CGFloat = 340, margin: CGFloat = 20
        let body = NSTextField(wrappingLabelWithString:
            T("The daemon and the menu bar both stop. Nothing will pause hot jobs until you start it again."))
        body.font = .systemFont(ofSize: 11)
        body.textColor = .secondaryLabelColor
        body.alignment = .center
        body.preferredMaxLayoutWidth = windowWidth - 2 * margin
        let bodyHeight = body.sizeThatFits(NSSize(width: windowWidth - 2 * margin, height: 300)).height

        // Title MUST wrap and have margins. A one-line label across the full window
        // clipped sentence endings; longer Russian and Spanish translations would lose
        // even more.
        let title = NSTextField(wrappingLabelWithString:
            T("Turn off thermal protection for this Mac?"))
        title.font = .boldSystemFont(ofSize: 13)
        title.alignment = .center
        title.preferredMaxLayoutWidth = windowWidth - 2 * margin
        let titleHeight = title.sizeThatFits(NSSize(width: windowWidth - 2 * margin, height: 200)).height

        let windowHeight = 18 + 44 + 8 + titleHeight + 10 + bodyHeight + 18 + 32 + 18
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: windowWidth, height: windowHeight),
                           styleMask: [.titled, .fullSizeContentView],
                           backing: .buffered, defer: false)
        win.titlebarAppearsTransparent = true
        win.titleVisibility = .hidden
        win.isMovableByWindowBackground = true
        win.level = .modalPanel
        win.center()
        let backgroundView = NSVisualEffectView(frame: NSRect(x: 0, y: 0, width: windowWidth, height: windowHeight))
        backgroundView.material = .popover
        backgroundView.state = .active
        win.contentView = backgroundView

        var y = windowHeight - 18 - 44
        let iconView = NSImageView(frame: NSRect(x: (windowWidth - 44) / 2, y: y, width: 44, height: 44))
        if let img = NSImage(contentsOfFile: base + "/paladin_welcome.png") { iconView.image = img }
        iconView.imageScaling = .scaleProportionallyUpOrDown
        backgroundView.addSubview(iconView)

        y -= 8 + titleHeight
        title.frame = NSRect(x: margin, y: y, width: windowWidth - 2 * margin, height: titleHeight)
        backgroundView.addSubview(title)

        y -= 10 + bodyHeight
        body.frame = NSRect(x: margin, y: y, width: windowWidth - 2 * margin, height: bodyHeight)
        backgroundView.addSubview(body)

        y -= 18 + 32
        // Default key is CANCEL; Enter must not disable protection.
        buttonRow(backgroundView, windowWidth, y, [T("Quit anyway"), T("Cancel")], defaultIndex: 1,
                       action: #selector(closeFreezeDialog(_:)))

        NSApp.activate(ignoringOtherApps: true)
        let result = NSApp.runModal(for: win)
        win.orderOut(nil)
        guard result.rawValue == 0 else { return }

        // Daemon goes first: if the bar died earlier, the user would be left with active
        // protection and no way to see it.
        let uid = String(getuid())
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        p.arguments = ["bootout", "gui/\(uid)/pl.pawel.coffee-paladin"]
        try? p.run()
        p.waitUntilExit()

        let b = Process()
        b.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        b.arguments = ["bootout", "gui/\(uid)/pl.pawel.coffee-paladin-bar"]
        try? b.run()          // Do not wait: this command kills us.
        NSApp.terminate(nil)
    }
}

// Agents and scripts instinctively call `heatbar --once`/`--json`. Without this handler,
// the menu bar app waits with no window and blocks automation until timeout. Print the
// guard snapshot, the same data the bar reads every 5 s, and exit immediately.
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

// The status item must be created in applicationDidFinishLaunching, not before
// app.run(): created earlier it never appeared in the menu bar on macOS 14
// (field report: Sonoma 14.2.1, M1 Pro - process alive, windows fine, no item),
// while macOS 26 tolerated both orders.
final class AppDelegate: NSObject, NSApplicationDelegate {
    var bar: Bar?
    func applicationDidFinishLaunching(_ note: Notification) {
        bar = Bar()
        // One line of truth in heatbar.err: does the SYSTEM consider the item
        // visible? Distinguishes "never attached" from "hidden by the notch or
        // a menu bar manager" without another debugging round-trip with a user.
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self] in
            guard let item = self?.bar?.item else { return }
            let line = "statusitem: visible=\(item.isVisible) length=\(item.length) button=\(item.button != nil)\n"
            FileHandle.standardError.write(line.data(using: .utf8)!)
        }
    }
}

// ONE bar per Mac. A second copy puts a second identical thermometer into a
// menu bar that may already have no room for the first, and the two then fight
// over it. It happens easily: the app is in /Applications, so a person clicks
// it - from the Dock, from Launchpad, from Finder - while the launch agent has
// been running it since login.
//
// That click is not a mistake to punish, it is a request to see the program.
// Hand it to the instance that is already running, which opens its panel, and
// leave. `flock` and not a pid file: a pid file survives a crash and locks the
// bar out of its own machine, a lock dies with the process that held it.
let instanceLock = open(base + "/heatbar.lock", O_CREAT | O_RDWR, 0o600)
if instanceLock >= 0 && flock(instanceLock, LOCK_EX | LOCK_NB) != 0 {
    try? "panel".write(toFile: base + "/show_window", atomically: true, encoding: .utf8)
    FileHandle.standardError.write(
        "another menu bar is already running - asked it to open the panel\n".data(using: .utf8)!)
    exit(0)
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)   // no Dock icon, no window
let appDelegate = AppDelegate()
app.delegate = appDelegate
app.run()
