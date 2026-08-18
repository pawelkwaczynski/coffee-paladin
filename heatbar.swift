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

let VERSION = "3.2.4"
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
    "!": "!",
    "no data - is coffee-paladin running?": "brak danych - czy coffee-paladin działa?",
    "data is stale (%@) - the guard may have died": "dane nieświeże (%@) - guard mógł paść",
    " (remembered)": " (zapamiętany)",
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
    "Heating the most now (CPU ≈ heat):": "Największe źródła ciepła teraz (wg CPU):",
    "Eating the most RAM:": "Najwięcej RAM używają:",
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
    "no AI session is running right now": "żadna sesja AI teraz nie działa",
    "… %d more": "… jeszcze %d",
    "%@ session — %.0f%% CPU in its tree": "sesja %@ — %.0f%% CPU w jej drzewie",
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
    "Load info": "Co obciąża Maca",
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
    "WHAT IT CAN DO\n• The paladin watches the chip, the battery, the fans and the power source - by default a reading every 15 seconds.\n• When things get too hot, it FREEZES heavy processes instead of letting the Mac cook itself. The pause destroys nothing: the process stops mid-instruction and continues once the chip cools. Example? Measured: 89 °C → 60 °C in 19 seconds, no loss.\n• It finds the real culprit: CPU is counted across the whole process tree, so it also sees a script that spawns hundreds of short jobs while using almost nothing itself.\n• On battery below 10% it pauses long jobs - they resume when you plug in.\n• It keeps a black box: after a hard failure the last 8 readings survive. One click turns them into a report for a repair shop (should you ever need it).\n• Keep-awake - works like the well-known Caffeine or Amphetamine, but unlike them it comes with a fuse: the sleep lock is released the moment things run hot. Sleep is the fastest cooling there is.": "CO POTRAFI\n• Paladyn pilnuje chipa, baterii, wentylatorów i zasilania – domyślny pomiar co 15 sekund.\n• Gdy robi się za gorąco, ZAMRAŻA ciężkie procesy zamiast pozwolić Macowi się ugotować. Pauza niczego nie niszczy: proces staje w miejscu i rusza dalej, gdy chip ostygnie. Przykład? Zmierzone: 89 °C → 60 °C w 19 sekund, obliczenia bez strat.\n• Znajduje prawdziwego winowajcę: liczy CPU całego drzewa procesów, więc widzi też skrypt, który odpala setki krótkich zadań i sam prawie nic nie zużywa.\n• Na baterii poniżej 10% wstrzymuje długie obliczenia - wznowi po podpięciu ładowarki.\n• Prowadzi czarną skrzynkę: po twardej awarii zostaje 8 ostatnich pomiarów. Jednym kliknięciem złożysz z tego raport dla serwisu (w razie potrzeby).\n• „Nie usypiaj Maca\" – działa jak znane programy Caffeine czy Amphetamine, ale w odróżnieniu od nich robi to z bezpiecznikiem: blokada snu puszcza w momencie, gdy robi się gorąco. Sen chłodzi najszybciej.",
    "WHAT WILL HAPPEN\n• Your choice in the welcome window decides how you start.\n\n\"Watch only\" mode: the paladin measures, logs and alerts, but PAUSES NOTHING.\n\n\"Enable protection\" mode: it pauses at the defined thresholds.\n\nSwitching is easy - one switch at the top of the menu.\n\n• Default thresholds: pause at 85 °C, resume at 76 °C, gentle closing of processes at 90 °C - and only after 4 critical readings in a row. Above 90 °C for over a minute is an emergency: despite the pauses the chip still holds critical (something we could not pause is heating, or pausing was not enough to cool the chip). The process is then woken up and gets SIGTERM - a polite \"shut down\": it has a chance to save its state, close its files, clean up. That is why we call this termination \"gentle\".\n\nA fanless Mac (e.g. an Air or Neo) gets more careful parameters. The thresholds are always picked for YOUR machine: see menu > \"About my Mac\".\n\n• Notifications: on. Sounds: off (enable them in Settings). At the critical level a system banner breaks through everything - Focus and full-screen included.\n• The system, Finder, your terminal and your AI agent are on the never-touch list. The guard will not freeze the session working next to it.": "CO SIĘ BĘDZIE DZIAŁO\n• Twój wybór z okna powitalnego decyduje o starcie.\n\nTryb „Tylko obserwuj\": paladyn mierzy, loguje i alarmuje, ale NICZEGO NIE WSTRZYMUJE.\n\nTryb „Włącz ochronę\": pauzuje na zdefiniowanych progach.\n\nTryby przełączysz łatwo – to jeden switch na górze menu.\n\n• Domyślne progi: pauza przy 85 °C, wznowienie przy 76 °C, łagodne zamknięcie procesów przy 90 °C - i to dopiero po 4 krytycznych odczytach z rzędu. Ponad 90 °C przez ponad 1 minutę to sytuacja awaryjna: mimo pauzowania chip dalej trzyma poziom krytyczny (czyli grzeje coś, czego nie mogliśmy zapauzować, albo pauza nie wystarczyła do chłodzenia chipa). Wtedy proces jest budzony i dostaje SIGTERM — grzeczne „zamknij się\": ma szansę zapisać stan, domknąć pliki, posprzątać. Dlatego ubicie go traktujemy jako „łagodne\".\n\nMac bez wentylatora (np. Air lub Neo) dostaje ostrożniejsze parametry. Progi zawsze są dobrane dla TWOJEJ maszyny: zobacz w menu > „O moim Macu\".\n\n• Powiadomienia: włączone. Dźwięki: wyłączone (włączysz w Ustawieniach). Przy poziomie krytycznym baner systemowy przebija się zawsze - nawet przez Skupienie i pełny ekran.\n• System, Finder, terminal i Twój agent AI są na liście nietykalnych. Strażnik nie zamrozi sesji, która przy nim pracuje.",
    "WHAT YOU CAN SET\n• Chip pause threshold - a slider; resume and terminate recalculate themselves.\n• Measurement interval 5-30 s: more often = faster reaction, but costlier in CPU use.\n• Heavy jobs (safe-run): all cores (fast) or efficiency cores only (cool and quiet), plus a CPU limit of 50-100%.\n• Battery gate, signals, keep-awake, this Mac's name in the fleet.": "CO MOŻESZ USTAWIĆ\n• Próg pauzy chipa - suwak; wznowienie i ubicie przeliczają się same.\n• Interwał pomiaru 5-30 s: częściej = szybsza reakcja, ale drożej w użyciu CPU.\n• Ciężkie zadania (safe-run): wszystkie rdzenie (szybko) albo tylko E-cores (chłodno i cicho), do tego limit CPU 50-100%.\n• Bramka baterii, sygnały, „Nie usypiaj\", nazwa tego Maca we flocie.",
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
    "Keeping the Mac awake (heavy job running)": "Nie usypiam Maca, bo działa ciężkie zadanie",
    "Right now: keeping the Mac awake": "Teraz: czuwanie trzymane",
    "Keep the screen on too (uses more power)": "Nie gaś też ekranu (więcej prądu i ciepła)",
    "Keep-awake time left": "Ile zostało czuwania",
    "Session statistics": "Statystyki sesji",
    "Across the fleet (%d machines)": "Cała flota (%d maszyny)",
    "%d machine(s) not reporting - their numbers may be old": "%d maszyna nie raportuje - jej liczby mogą być stare",
    "per machine: menu > Apple fleet > click a Mac": "rozbicie na maszyny: menu > Flota Apple > kliknij Maca",
    "What the guard did here (total)": "Co bezpiecznik zrobił na tej maszynie (od zawsze)",
    "in this session (since %@)": "w tej sesji (od %@)",
    "total since %@": "łącznie od %@",
    "Nothing here - and that is good news: your Mac has not been overheating.": "Nic tu nie ma - to dobrze, znaczy, że twoja maszyna się nie przegrzewała.",
    "In this session: no interventions yet.": "W tej sesji: jeszcze bez interwencji.",
    "Pause ended another way (manual resume, job exited, daemon restart): %d": "Pauza zakończona inaczej (ręczne wznowienie, proces sam się skończył, restart demona): %d",
    "Hardware details": "Szczegóły sprzętu",
    "Hot - the guard is on it": "Gorąco - strażnik reaguje",
    "Getting warm - watching closely": "Ciepło - obserwuję uważnie",
    "Hot - %d job(s) paused": "Gorąco - wstrzymane zadania: %d",
    "Watch-only mode - measuring, pausing nothing": "Tryb obserwacji - mierzę, niczego nie wstrzymuję",
    "%@ session — idle": "sesja %@ — bez obciążenia",
    "Process tree details": "Szczegóły drzew procesów",
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
    "Keeping the Mac awake (heavy job running)": "Держу Mac в бодрствовании (идёт тяжёлая задача)",
    "Right now: keeping the Mac awake": "Сейчас: бодрствование удерживается",
    "Keep the screen on too (uses more power)": "Не гасить и экран (больше энергии и тепла)",
    "Keep-awake time left": "Сколько осталось бодрствования",
    "Session statistics": "Статистика сессии",
    "Across the fleet (%d machines)": "Весь парк (%d машин)",
    "%d machine(s) not reporting - their numbers may be old": "%d машин(а) не отчитывается - её числа могут быть старыми",
    "per machine: menu > Apple fleet > click a Mac": "по машинам: меню > Парк Apple > нажмите на Mac",
    "What the guard did here (total)": "Что защита сделала на этой машине (за всё время)",
    "in this session (since %@)": "в этой сессии (с %@)",
    "total since %@": "всего с %@",
    "Nothing here - and that is good news: your Mac has not been overheating.": "Здесь пусто - и это хорошо: ваш Mac не перегревался.",
    "In this session: no interventions yet.": "В этой сессии: вмешательств пока нет.",
    "Pause ended another way (manual resume, job exited, daemon restart): %d": "Пауза завершилась иначе (ручное возобновление, процесс сам завершился, перезапуск демона): %d",
    "Hardware details": "Сведения об оборудовании",
    "Hot - the guard is on it": "Жарко - страж действует",
    "Getting warm - watching closely": "Теплеет - слежу внимательно",
    "Hot - %d job(s) paused": "Горячо - приостановлено задач: %d",
    "Watch-only mode - measuring, pausing nothing": "Режим наблюдения - измеряю, ничего не останавливаю",
    "%@ session — idle": "сессия %@ — без нагрузки",
    "Process tree details": "Деревья процессов подробно",
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
    "no AI session is running right now": "сейчас не работает ни одна сессия ИИ",
    "… %d more": "… ещё %d",
    "%@ session — %.0f%% CPU in its tree": "сессия %@ — %.0f%% CPU в её дереве",
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
    "Phone notifications…": "Уведомления на телефон…",
    "First steps…": "Первые шаги...",
    "WHAT IT CAN DO\n• The paladin watches the chip, the battery, the fans and the power source - by default a reading every 15 seconds.\n• When things get too hot, it FREEZES heavy processes instead of letting the Mac cook itself. The pause destroys nothing: the process stops mid-instruction and continues once the chip cools. Example? Measured: 89 °C → 60 °C in 19 seconds, no loss.\n• It finds the real culprit: CPU is counted across the whole process tree, so it also sees a script that spawns hundreds of short jobs while using almost nothing itself.\n• On battery below 10% it pauses long jobs - they resume when you plug in.\n• It keeps a black box: after a hard failure the last 8 readings survive. One click turns them into a report for a repair shop (should you ever need it).\n• Keep-awake - works like the well-known Caffeine or Amphetamine, but unlike them it comes with a fuse: the sleep lock is released the moment things run hot. Sleep is the fastest cooling there is.": "ЧТО ОН УМЕЕТ\n• Паладин следит за чипом, батареей, вентиляторами и питанием - по умолчанию замер каждые 15 секунд.\n• Когда становится слишком горячо, ЗАМОРАЖИВАЕТ тяжёлые процессы, вместо того чтобы дать Mac свариться. Пауза ничего не разрушает: процесс замирает и продолжает с того же места, когда чип остынет. Пример? Измерено: 89 °C → 60 °C за 19 секунд, без потерь.\n• Находит настоящего виновника: CPU считается по всему дереву процессов, поэтому виден и скрипт, порождающий сотни коротких задач.\n• На батарее ниже 10% длинные задачи ставятся на паузу - возобновятся после подключения зарядки.\n• Ведёт чёрный ящик: после жёсткого сбоя остаются 8 последних замеров. Один клик - и из них готов отчёт для сервиса (если понадобится).\n• «Не усыплять Mac» - работает как известные Caffeine или Amphetamine, но в отличие от них с предохранителем: блокировка сна снимается, как только становится горячо. Сон охлаждает быстрее всего.",
    "WHAT WILL HAPPEN\n• Your choice in the welcome window decides how you start.\n\n\"Watch only\" mode: the paladin measures, logs and alerts, but PAUSES NOTHING.\n\n\"Enable protection\" mode: it pauses at the defined thresholds.\n\nSwitching is easy - one switch at the top of the menu.\n\n• Default thresholds: pause at 85 °C, resume at 76 °C, gentle closing of processes at 90 °C - and only after 4 critical readings in a row. Above 90 °C for over a minute is an emergency: despite the pauses the chip still holds critical (something we could not pause is heating, or pausing was not enough to cool the chip). The process is then woken up and gets SIGTERM - a polite \"shut down\": it has a chance to save its state, close its files, clean up. That is why we call this termination \"gentle\".\n\nA fanless Mac (e.g. an Air or Neo) gets more careful parameters. The thresholds are always picked for YOUR machine: see menu > \"About my Mac\".\n\n• Notifications: on. Sounds: off (enable them in Settings). At the critical level a system banner breaks through everything - Focus and full-screen included.\n• The system, Finder, your terminal and your AI agent are on the never-touch list. The guard will not freeze the session working next to it.": "ЧТО БУДЕТ ПРОИСХОДИТЬ\n• Ваш выбор в окне приветствия определяет старт.\n\nРежим «Только наблюдать»: паладин измеряет, ведёт журнал и предупреждает, но НИЧЕГО НЕ ОСТАНАВЛИВАЕТ.\n\nРежим «Включить защиту»: ставит на паузу по заданным порогам.\n\nПереключиться легко - один переключатель вверху меню.\n\n• Пороги по умолчанию: пауза при 85 °C, возобновление при 76 °C, мягкое закрытие процессов при 90 °C - и только после 4 критических замеров подряд. Выше 90 °C дольше минуты - аварийная ситуация: несмотря на паузы чип держит критический уровень (греет то, что мы не могли поставить на паузу, или паузы не хватило для охлаждения). Тогда процесс будят, и он получает SIGTERM - вежливое «завершись»: есть шанс сохранить состояние, закрыть файлы, прибраться. Поэтому такое завершение мы называем «мягким».\n\nMac без вентилятора (например, Air или Neo) получает более осторожные параметры. Пороги всегда подобраны для ВАШЕЙ машины: см. меню > «Об этом Mac».\n\n• Уведомления: включены. Звуки: выключены (включаются в Настройках). На критическом уровне системный баннер пробивается всегда - даже через Фокусирование и полный экран.\n• Система, Finder, терминал и ваш ИИ-агент - в списке неприкасаемых. Страж не заморозит сессию, которая работает рядом с ним.",
    "WHAT YOU CAN SET\n• Chip pause threshold - a slider; resume and terminate recalculate themselves.\n• Measurement interval 5-30 s: more often = faster reaction, but costlier in CPU use.\n• Heavy jobs (safe-run): all cores (fast) or efficiency cores only (cool and quiet), plus a CPU limit of 50-100%.\n• Battery gate, signals, keep-awake, this Mac's name in the fleet.": "ЧТО МОЖНО НАСТРОИТЬ\n• Порог паузы чипа - ползунок; возобновление и завершение пересчитываются сами.\n• Интервал замеров 5-30 с: чаще = быстрее реакция, но дороже по CPU.\n• Тяжёлые задачи (safe-run): все ядра (быстро) или только E-ядра (тихо), плюс лимит CPU 50-100%.\n• Порог батареи, сигналы, keep-awake, имя этого Mac в парке.",
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
    "Keeping the Mac awake (heavy job running)": "正在保持 Mac 唤醒（繁重任务运行中）",
    "Right now: keeping the Mac awake": "当前：正在保持唤醒",
    "Keep the screen on too (uses more power)": "屏幕也不熄灭（更耗电、更热）",
    "Keep-awake time left": "唤醒剩余时间",
    "Session statistics": "本次会话统计",
    "Across the fleet (%d machines)": "整个机群（%d 台）",
    "%d machine(s) not reporting - their numbers may be old": "%d 台未上报 - 其数字可能过时",
    "per machine: menu > Apple fleet > click a Mac": "按机器查看：菜单 > Apple 机群 > 点击某台 Mac",
    "What the guard did here (total)": "守护在这台机器上做过什么（累计）",
    "in this session (since %@)": "本次会话（自 %@）",
    "total since %@": "累计自 %@",
    "Nothing here - and that is good news: your Mac has not been overheating.": "这里是空的 - 这是好消息：你的 Mac 没有过热。",
    "In this session: no interventions yet.": "本次会话:尚无干预。",
    "Pause ended another way (manual resume, job exited, daemon restart): %d": "暂停以其他方式结束(手动恢复、进程自行退出、守护进程重启):%d",
    "Hardware details": "硬件详情",
    "Hot - the guard is on it": "过热 - 守卫正在处理",
    "Getting warm - watching closely": "变热了 - 正在密切关注",
    "Hot - %d job(s) paused": "过热 - 已暂停任务:%d",
    "Watch-only mode - measuring, pausing nothing": "仅观察模式 - 只测量,不暂停",
    "%@ session — idle": "%@ 会话 — 空闲",
    "Process tree details": "进程树详情",
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
    "no AI session is running right now": "当前没有运行中的 AI 会话",
    "… %d more": "… 还有 %d 个",
    "%@ session — %.0f%% CPU in its tree": "%@ 会话 — 其进程树占 %.0f%% CPU",
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
    "Phone notifications…": "手机通知…",
    "First steps…": "入门指南...",
    "WHAT IT CAN DO\n• The paladin watches the chip, the battery, the fans and the power source - by default a reading every 15 seconds.\n• When things get too hot, it FREEZES heavy processes instead of letting the Mac cook itself. The pause destroys nothing: the process stops mid-instruction and continues once the chip cools. Example? Measured: 89 °C → 60 °C in 19 seconds, no loss.\n• It finds the real culprit: CPU is counted across the whole process tree, so it also sees a script that spawns hundreds of short jobs while using almost nothing itself.\n• On battery below 10% it pauses long jobs - they resume when you plug in.\n• It keeps a black box: after a hard failure the last 8 readings survive. One click turns them into a report for a repair shop (should you ever need it).\n• Keep-awake - works like the well-known Caffeine or Amphetamine, but unlike them it comes with a fuse: the sleep lock is released the moment things run hot. Sleep is the fastest cooling there is.": "它能做什么\n• 圣骑士监控芯片、电池、风扇和电源 - 默认每15秒测量一次。\n• 过热时会冻结繁重进程,而不是让 Mac 煮熟自己。暂停不会破坏任何东西:进程原地停住,芯片冷却后从同一处继续。例子?实测:89 °C → 60 °C 只用19秒,零损失。\n• 找到真正的元凶:按整个进程树统计 CPU,连派生数百个短任务的脚本也看得见。\n• 电量低于10%时暂停长任务 - 插上电源后自动恢复。\n• 黑匣子:硬故障后保留最后8次测量,一键生成维修报告(以备不时之需)。\n• 保持唤醒 - 像知名的 Caffeine 或 Amphetamine 一样,但不同的是它带保险丝:一旦过热立即释放睡眠锁。睡眠是最快的降温方式。",
    "WHAT WILL HAPPEN\n• Your choice in the welcome window decides how you start.\n\n\"Watch only\" mode: the paladin measures, logs and alerts, but PAUSES NOTHING.\n\n\"Enable protection\" mode: it pauses at the defined thresholds.\n\nSwitching is easy - one switch at the top of the menu.\n\n• Default thresholds: pause at 85 °C, resume at 76 °C, gentle closing of processes at 90 °C - and only after 4 critical readings in a row. Above 90 °C for over a minute is an emergency: despite the pauses the chip still holds critical (something we could not pause is heating, or pausing was not enough to cool the chip). The process is then woken up and gets SIGTERM - a polite \"shut down\": it has a chance to save its state, close its files, clean up. That is why we call this termination \"gentle\".\n\nA fanless Mac (e.g. an Air or Neo) gets more careful parameters. The thresholds are always picked for YOUR machine: see menu > \"About my Mac\".\n\n• Notifications: on. Sounds: off (enable them in Settings). At the critical level a system banner breaks through everything - Focus and full-screen included.\n• The system, Finder, your terminal and your AI agent are on the never-touch list. The guard will not freeze the session working next to it.": "将会发生什么\n• 欢迎窗口的选择决定起点。\n\n「仅观察」模式:圣骑士测量、记录、警报,但不暂停任何进程。\n\n「启用保护」模式:按设定的阈值暂停。\n\n切换很简单 - 菜单顶部的一个开关。\n\n• 默认阈值:85 °C 暂停,76 °C 恢复,90 °C 温和关闭进程 - 且需连续4次危险读数。超过 90 °C 持续一分钟以上属于紧急情况:尽管已暂停,芯片仍处于危险级别(发热的是我们无法暂停的东西,或暂停不足以降温)。此时进程会被唤醒并收到 SIGTERM - 礼貌的「请关闭」:它有机会保存状态、关闭文件、清理现场。所以我们称这种终止为「温和」。\n\n无风扇的 Mac(如 Air 或 Neo)获得更保守的参数。阈值总是为你的机器挑选:见菜单 >「关于我的 Mac」。\n\n• 通知:开。声音:关(可在设置中打开)。危险级别时系统横幅总会弹出 - 专注模式和全屏也不例外。\n• 系统、Finder、终端和你的 AI 代理都在不可触碰清单上。守卫不会冻结在它身边工作的会话。",
    "WHAT YOU CAN SET\n• Chip pause threshold - a slider; resume and terminate recalculate themselves.\n• Measurement interval 5-30 s: more often = faster reaction, but costlier in CPU use.\n• Heavy jobs (safe-run): all cores (fast) or efficiency cores only (cool and quiet), plus a CPU limit of 50-100%.\n• Battery gate, signals, keep-awake, this Mac's name in the fleet.": "你可以设置\n• 芯片暂停阈值 - 滑块;恢复和终止自动换算。\n• 测量间隔 5-30 秒:更频繁 = 反应更快,但 CPU 开销更大。\n• 繁重任务(safe-run):全部核心(快)或仅能效核心(安静),外加 50-100% CPU 限制。\n• 电池阈值、信号、保持唤醒、这台 Mac 在机群中的名字。",
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
    "Keeping the Mac awake (heavy job running)": "Manteniendo el Mac despierto (tarea pesada en curso)",
    "Right now: keeping the Mac awake": "Ahora: manteniendo el Mac despierto",
    "Keep the screen on too (uses more power)": "Mantener también la pantalla encendida (más consumo y calor)",
    "Keep-awake time left": "Tiempo restante de vigilia",
    "Session statistics": "Estadísticas de la sesión",
    "Across the fleet (%d machines)": "Toda la flota (%d máquinas)",
    "%d machine(s) not reporting - their numbers may be old": "%d máquina(s) sin reportar: sus números pueden ser antiguos",
    "per machine: menu > Apple fleet > click a Mac": "por máquina: menú > Flota Apple > pulsa un Mac",
    "What the guard did here (total)": "Lo que hizo el guardián en esta máquina (histórico)",
    "in this session (since %@)": "en esta sesión (desde %@)",
    "total since %@": "total desde %@",
    "Nothing here - and that is good news: your Mac has not been overheating.": "Aquí no hay nada, y es buena noticia: tu Mac no se ha sobrecalentado.",
    "In this session: no interventions yet.": "En esta sesión: aún sin intervenciones.",
    "Pause ended another way (manual resume, job exited, daemon restart): %d": "La pausa terminó de otra forma (reanudación manual, el proceso terminó solo, reinicio del demonio): %d",
    "Hardware details": "Detalles del hardware",
    "Hot - the guard is on it": "Caliente: el guardián actúa",
    "Getting warm - watching closely": "Se calienta: vigilando de cerca",
    "Hot - %d job(s) paused": "Caliente: tareas en pausa: %d",
    "Watch-only mode - measuring, pausing nothing": "Modo observación: mido, no pauso nada",
    "%@ session — idle": "sesión %@ — sin carga",
    "Process tree details": "Detalles de árboles de procesos",
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
    "no AI session is running right now": "ninguna sesión de IA está activa ahora",
    "… %d more": "… %d más",
    "%@ session — %.0f%% CPU in its tree": "sesión %@ — %.0f%% CPU en su árbol",
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
    "Phone notifications…": "Notificaciones en el móvil…",
    "First steps…": "Primeros pasos...",
    "WHAT IT CAN DO\n• The paladin watches the chip, the battery, the fans and the power source - by default a reading every 15 seconds.\n• When things get too hot, it FREEZES heavy processes instead of letting the Mac cook itself. The pause destroys nothing: the process stops mid-instruction and continues once the chip cools. Example? Measured: 89 °C → 60 °C in 19 seconds, no loss.\n• It finds the real culprit: CPU is counted across the whole process tree, so it also sees a script that spawns hundreds of short jobs while using almost nothing itself.\n• On battery below 10% it pauses long jobs - they resume when you plug in.\n• It keeps a black box: after a hard failure the last 8 readings survive. One click turns them into a report for a repair shop (should you ever need it).\n• Keep-awake - works like the well-known Caffeine or Amphetamine, but unlike them it comes with a fuse: the sleep lock is released the moment things run hot. Sleep is the fastest cooling there is.": "QUÉ SABE HACER\n• El paladín vigila el chip, la batería, los ventiladores y la fuente de alimentación: por defecto una medición cada 15 segundos.\n• Cuando la cosa se calienta demasiado, CONGELA los procesos pesados en vez de dejar que el Mac se cueza. La pausa no destruye nada: el proceso se detiene a mitad de instrucción y sigue en cuanto el chip se enfría. ¿Un ejemplo? Medido: 89 °C → 60 °C en 19 segundos, sin pérdidas.\n• Encuentra al culpable de verdad: la CPU se cuenta en todo el árbol de procesos, así que también ve el script que lanza cientos de tareas cortas sin apenas consumir por sí mismo.\n• Con la batería por debajo del 10% pausa los trabajos largos, y los reanuda al enchufar la corriente.\n• Lleva una caja negra: tras un apagón brusco sobreviven las 8 últimas mediciones. Con un clic se convierten en un informe para el servicio técnico (por si algún día hace falta).\n• Mantener despierto: funciona como los conocidos Caffeine o Amphetamine, pero a diferencia de ellos viene con fusible: el bloqueo del sueño se suelta en cuanto sube la temperatura. Dormir es la forma más rápida de enfriar.",
    "WHAT WILL HAPPEN\n• Your choice in the welcome window decides how you start.\n\n\"Watch only\" mode: the paladin measures, logs and alerts, but PAUSES NOTHING.\n\n\"Enable protection\" mode: it pauses at the defined thresholds.\n\nSwitching is easy - one switch at the top of the menu.\n\n• Default thresholds: pause at 85 °C, resume at 76 °C, gentle closing of processes at 90 °C - and only after 4 critical readings in a row. Above 90 °C for over a minute is an emergency: despite the pauses the chip still holds critical (something we could not pause is heating, or pausing was not enough to cool the chip). The process is then woken up and gets SIGTERM - a polite \"shut down\": it has a chance to save its state, close its files, clean up. That is why we call this termination \"gentle\".\n\nA fanless Mac (e.g. an Air or Neo) gets more careful parameters. The thresholds are always picked for YOUR machine: see menu > \"About my Mac\".\n\n• Notifications: on. Sounds: off (enable them in Settings). At the critical level a system banner breaks through everything - Focus and full-screen included.\n• The system, Finder, your terminal and your AI agent are on the never-touch list. The guard will not freeze the session working next to it.": "QUÉ VA A PASAR\n• Tu elección en la ventana de bienvenida decide cómo empiezas.\n\nModo «Solo observar»: el paladín mide, registra y avisa, pero NO PAUSA NADA.\n\nModo «Activar protección»: pausa en los umbrales definidos.\n\nCambiar de uno a otro es fácil: un interruptor en lo alto del menú.\n\n• Umbrales por defecto: pausa a 85 °C, reanudación a 76 °C, cierre suave de procesos a 90 °C, y solo tras 4 lecturas críticas seguidas. Más de 90 °C durante más de un minuto es una emergencia: pese a las pausas el chip sigue en crítico (algo que no pudimos pausar está calentando, o pausar no bastó para enfriarlo). Entonces el proceso se despierta y recibe SIGTERM, un «ciérrate» educado: tiene ocasión de guardar su estado, cerrar sus archivos y limpiar. Por eso llamamos «suave» a esta terminación.\n\nUn Mac sin ventilador (por ejemplo un Air) recibe parámetros más prudentes. Los umbrales se eligen siempre para TU máquina: míralo en el menú > «Sobre mi Mac».\n\n• Notificaciones: activadas. Sonidos: desactivados (se activan en Ajustes). En el nivel crítico un aviso del sistema atraviesa todo, incluidos Concentración y la pantalla completa.\n• El sistema, el Finder, tu terminal y tu agente de IA están en la lista de intocables. El guardián no congelará la sesión que trabaja a su lado.",
    "WHAT YOU CAN SET\n• Chip pause threshold - a slider; resume and terminate recalculate themselves.\n• Measurement interval 5-30 s: more often = faster reaction, but costlier in CPU use.\n• Heavy jobs (safe-run): all cores (fast) or efficiency cores only (cool and quiet), plus a CPU limit of 50-100%.\n• Battery gate, signals, keep-awake, this Mac's name in the fleet.": "QUÉ PUEDES CONFIGURAR\n• Umbral de pausa del chip: un deslizador; la reanudación y el cierre se recalculan solos.\n• Intervalo de medición de 5 a 30 s: más a menudo = reacción más rápida, pero más gasto de CPU.\n• Trabajos pesados (safe-run): todos los núcleos (rápido) o solo los de eficiencia (fresco y silencioso), más un límite de CPU del 50 al 100%.\n• Puerta de batería, señales, mantener despierto y el nombre de este Mac en la flota.",
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
        ntfyBtn.frame = NSRect(x: 16, y: 12, width: 210, height: 24)
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
let GUIDE_CAN = "WHAT IT CAN DO\n• The paladin watches the chip, the battery, the fans and the power source - by default a reading every 15 seconds.\n• When things get too hot, it FREEZES heavy processes instead of letting the Mac cook itself. The pause destroys nothing: the process stops mid-instruction and continues once the chip cools. Example? Measured: 89 °C → 60 °C in 19 seconds, no loss.\n• It finds the real culprit: CPU is counted across the whole process tree, so it also sees a script that spawns hundreds of short jobs while using almost nothing itself.\n• On battery below 10% it pauses long jobs - they resume when you plug in.\n• It keeps a black box: after a hard failure the last 8 readings survive. One click turns them into a report for a repair shop (should you ever need it).\n• Keep-awake - works like the well-known Caffeine or Amphetamine, but unlike them it comes with a fuse: the sleep lock is released the moment things run hot. Sleep is the fastest cooling there is."
let GUIDE_WILL = "WHAT WILL HAPPEN\n• Your choice in the welcome window decides how you start.\n\n\"Watch only\" mode: the paladin measures, logs and alerts, but PAUSES NOTHING.\n\n\"Enable protection\" mode: it pauses at the defined thresholds.\n\nSwitching is easy - one switch at the top of the menu.\n\n• Default thresholds: pause at 85 °C, resume at 76 °C, gentle closing of processes at 90 °C - and only after 4 critical readings in a row. Above 90 °C for over a minute is an emergency: despite the pauses the chip still holds critical (something we could not pause is heating, or pausing was not enough to cool the chip). The process is then woken up and gets SIGTERM - a polite \"shut down\": it has a chance to save its state, close its files, clean up. That is why we call this termination \"gentle\".\n\nA fanless Mac (e.g. an Air or Neo) gets more careful parameters. The thresholds are always picked for YOUR machine: see menu > \"About my Mac\".\n\n• Notifications: on. Sounds: off (enable them in Settings). At the critical level a system banner breaks through everything - Focus and full-screen included.\n• The system, Finder, your terminal and your AI agent are on the never-touch list. The guard will not freeze the session working next to it."
let GUIDE_SET = "WHAT YOU CAN SET\n• Chip pause threshold - a slider; resume and terminate recalculate themselves.\n• Measurement interval 5-30 s: more often = faster reaction, but costlier in CPU use.\n• Heavy jobs (safe-run): all cores (fast) or efficiency cores only (cool and quiet), plus a CPU limit of 50-100%.\n• Battery gate, signals, keep-awake, this Mac's name in the fleet."
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
func thresholdWarning(_ v: Double) -> (String, String) {
    if v < 60 { return (T("TOO LOW - an idle M-series chip already sits at 40-55 C, the guard would pause constantly"), "nosign") }
    if v < 70 { return (T("very conservative - a quiet, cool Mac, but long jobs will crawl"), "exclamationmark.triangle") }
    if v < 80 { return (T("conservative - good for a fanless Mac (Air, 12-inch)"), "lightbulb") }
    if v <= 92 { return (T("recommended - well below Apple's own throttling point (~100-108 C)"), "checkmark.circle") }
    return (T("aggressive - close to the temperature at which macOS throttles by itself"), "exclamationmark.triangle")
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
    var thrPause: Double?, thrKill: Double?
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

        var tip = s.reason.isEmpty ? "coffee-paladin: " + T("calm") : s.reason
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

        if s.stale { row(T("!") + " " + String(format: T("data is stale (%@) - the guard may have died"), s.stamp)) }
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

        // THE ANSWER, before any numbers: is it safe, and what is the guard
        // doing about it. Every reading below is evidence; this line is the
        // verdict, and the card was hard to read with the verdict missing.
        if !s.stale {
            let verdict: (String, String)
            // Order matters: frozen jobs are a fact regardless of mode, so
            // they outrank the dry-run line; a hot level without pauses
            // (nothing pausable, or a pause failed) must still say HOT, not
            // "warm" - understating the state is the one lie this line can
            // tell (caught by the Codex review round).
            if !s.paused.isEmpty {
                verdict = ("flame", String(format: T("Hot - %d job(s) paused"), s.paused.count))
            } else if s.dryRun {
                verdict = ("eye", T("Watch-only mode - measuring, pausing nothing"))
            } else if s.level >= 2 {
                verdict = ("flame", T("Hot - the guard is on it"))
            } else if s.level == 1 {
                verdict = ("thermometer.high", T("Getting warm - watching closely"))
            } else {
                // Calm needs no headline. The verdict earns its row when there is a
                // verdict to give - paused jobs, watch-only mode, heat - and "all safe"
                // was a line whose only content was that nothing was happening, in a menu
                // built on the rule that an element appears when it carries news.
                verdict = ("", "")
            }
            if !verdict.1.isEmpty {
                let head = NSMutableAttributedString(string: verdict.1)
                head.addAttribute(.font, value: NSFont.boldSystemFont(ofSize: NSFont.systemFontSize),
                                  range: NSRange(location: 0, length: head.length))
                rowI(verdict.0, head)
            }
        }

        rowI("thermometer.medium",
             txt("Chip:  " + (s.chip.map { String(format: "%.1f °C", $0) + (s.chipStale ? T(" (remembered)") : "") } ?? na)
                 + (s.gpu != nil ? String(format: "     GPU: %.1f °C", s.gpu!) : "")
                 + "     " + String(format: T("Battery:  %@"),
                                    s.batt.map { String(format: "%.1f °C", $0) } ?? na)))
        // Load and fans MUST be in separate rows, and the unit must not repeat for every
        // fan. In one line this row measured 328 pt with stopped fans and 446 pt with
        // spinning fans. Custom views (chart, switches, languages) hold 360 pt, so any
        // wider text stretches the menu: it widened by 118 pt when fans started and
        // shrank when they stopped. Russian was worse (439 pt). Split rows without the
        // repeated unit fit in 150-213 pt across all five languages, so menu width is
        // CONSTANT.
        rowI("gauge", txt(String(format: T("Load:  %.2f / %d cores"),
                                 s.load, ProcessInfo.processInfo.processorCount)))
        // Fans, RAM, disk and power moved off the main card into "Hardware
        // details": they are context, not verdict, and eight dense lines were
        // exactly why the owner could not tell what mattered. A reading comes
        // BACK to the main card only while it is alarming - a value worth
        // interrupting for must not hide in a submenu.
        let hw = NSMenu()
        hw.autoenablesItems = false
        if !s.fans.isEmpty {
            // Unit once at the end, but show ALL values. Filtering zeros would hide a fan
            // that stopped while another runs, exactly the symptom the cooling-failure
            // alarm exists for. Zero must be visible.
            let fanTxt = s.fans.allSatisfy { $0 == 0 }
                ? T("stopped")
                : String(format: T("%@ rpm"), s.fans.map(String.init).joined(separator: ", "))
            rowI("fan", txt(String(format: T("Fans:  %@"), fanTxt)), into: hw)
        }
        if let u = s.ramUsed, let t = s.ramTotal, t > 0 {
            var line = String(format: T("RAM:  %.1f / %.1f GB (%d%%)"), u, t, Int(100 * u / t))
            if let sw = s.swap, sw > 0.01 { line += "     " + String(format: T("swap %.2f GB"), sw) }
            rowI("memorychip", txt(line), into: hw)
            if Int(100 * u / t) >= 75 {
                rowI("memorychip", txt(line))
            }
        }
        if let du = s.diskUsed, let dt = s.diskTotal, let dp = s.diskPct {
            let line = String(format: T("Disk:  %d / %d GB used (%d%%)"), du, dt, dp)
            rowI("internaldrive", txt(line), into: hw)
            if dp >= 85 {
                rowI("internaldrive", txt(line))
            }
        }
        // No battery percentage here; macOS already shows it in the system bar. Keep
        // AC/battery itself because it changes guard behavior (battery gate). Percentage
        // remains in fleet, where you inspect another machine without its menu bar.
        // The icon says it faster than text: plug = AC, battery = battery.
        let pw = NSMutableAttributedString()
        pw.append(txt(String(format: T("Power:  %@"), s.onAC ? T("AC adapter") : T("Battery"))))
        if let w = s.watts {
            pw.append(txt("     "))
            pw.append(icon("bolt.fill", fallback: ""))
            pw.append(txt(" " + String(format: T("Draw:  %.1f W"), w)))
        }
        rowI(s.onAC ? "powerplug" : "battery.100", pw, into: hw)
        if hw.items.isEmpty == false {
            let hwIt = NSMenuItem(title: T("Hardware details"), action: nil, keyEquivalent: "")
            hwIt.image = img("cpu")
            hwIt.submenu = hw
            m.addItem(hwIt)
        }
        // "CPU available: 100%" was misleading: this is CPU_Speed_Limit from pmset
        // (clock throttling), not free capacity. Show the row ONLY when throttling is
        // real; at 100% it is noise, and the label now states the meaning directly.
        if s.cpuLimit < 100 {
            row(String(format: T("Throttling: CPU capped at %d%% speed"), s.cpuLimit))
        }
        if s.keepAwake {
            let a = Awake.read()
            switch a["mode"] as? String {
            case "timer":
                let left = max(0, (a["until"] as? Double ?? 0) - Date().timeIntervalSince1970)
                // Clock + plain language: caffeinate (built into macOS) is holding
                // keep-awake. The counter decreases on each card refresh; an open menu
                // does not tick every second because a constant menu timer would heat
                // the CPU we are protecting.
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
                                 fixedSubtitle: String(format: T("Heavy processes right now: %d"),
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
        let statsIt = m.addItem(withTitle: T("Session statistics"),
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
            // Keep derived values consistent: hysteresis 9 C down, kill 5 C up (max 100).
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
            // Neural Engine has no public read API. Derive ANE cores from chip model:
            // Ultra = 2x die = 32; every other M chip = 16.
            let ane = chipName.contains("Ultra") ? 32 : 16
            arow(String(format: T("Cores:  %d performance + %d efficiency  ·  Neural Engine: %d"),
                        (hw["p_cores"] as? Int) ?? 0, (hw["e_cores"] as? Int) ?? 0, ane))
            var ramLine = String(format: T("RAM:  %d GB"), (hw["ram_gb"] as? Int) ?? 0)
            let diskSnap = readSnap()
            if let dt = diskSnap?.diskTotal, let dp = diskSnap?.diskPct {
                ramLine += "  ·  " + String(format: T("Disk: %d GB (%d%% free)"), dt, 100 - dp)
            }
            arow(ramLine)
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
            var setupDate: Date?
            if let atr = try? FileManager.default.attributesOfItem(atPath: "/var/db/.AppleSetupDone"),
               let setupDoneDate = (atr[.creationDate] ?? atr[.modificationDate]) as? Date {
                setupDate = setupDoneDate
                let f = DateFormatter()
                f.dateFormat = "dd.MM.yyyy"
        f.locale = Locale(identifier: "en_US_POSIX")
        f.calendar = Calendar(identifier: .gregorian)
                osLine += "  ·  " + String(format: T("set up: %@"), f.string(from: setupDoneDate))
            }
            arow(osLine)
            var fanLine = String(format: T("Fans:  %d"), (hw["fan_count"] as? Int) ?? 0)
            if let cyc = hw["battery_cycles"] as? Int {
                let warn = (hw["battery_failure"] as? Bool) == true ? " (!)" : ""
                fanLine += "  ·  " + String(format: T("Battery cycles:  %@"), "\(cyc)\(warn)")
            }
            if let capacity = hw["battery_max_capacity_pct"] as? Int {
                fanLine += "  ·  " + String(format: T("max capacity: %d%%"), capacity)
            }
            arow(fanLine)
            if let ser = hw["serial"] as? String, !ser.isEmpty {
                var serialLine = String(format: T("Serial:  %@"), ser)
                // Warranty: macOS does not expose it programmatically. Estimate one year
                // from first system setup and state clearly that it is an estimate.
                if let ds = setupDate {
                    let f = DateFormatter()
                    f.dateFormat = "dd.MM.yyyy"
        f.locale = Locale(identifier: "en_US_POSIX")
        f.calendar = Calendar(identifier: .gregorian)
                    let warrantyEnd = ds.addingTimeInterval(365 * 86400)
                    serialLine += "  ·  " + String(format: T("limited warranty (est.): until %@"),
                                                 f.string(from: warrantyEnd))
                }
                arow(serialLine)
            }
            // Show all measurement sources, not only macmon. If one fails, users can
            // immediately see what else is still watching the machine.
            let ok = T("yes"), noText = T("no")
            let mac = (hw["chip_sensor"] as? Bool) == true
            let thermalStateOK = FileManager.default.isExecutableFile(atPath:
                NSHomeDirectory() + "/.local/bin/thermalstate")
            let sensorSnap = readSnap()
            let battOK = sensorSnap?.batt != nil
            let thrOK = (sensorSnap?.cpuLimit ?? 0) > 0
            arow(T("Sensors:"))
            arow("   - " + String(format: T("chip and GPU (macmon/IOReport):  %@"), mac ? ok : noText))
            arow("   - " + String(format: T("thermal state (Apple API):  %@"), thermalStateOK ? ok : noText))
            arow("   - " + String(format: T("battery (ioreg):  %@"), battOK ? ok : noText))
            arow("   - " + String(format: T("CPU throttling (pmset):  %@"), thrOK ? ok : noText))
            let sp = GuardCfg.double("soc_pause_c", 85), sk = GuardCfg.double("soc_kill_c", 90)
            arow(String(format: T("Chip thresholds:  pause %.0f C, kill %.0f C"), sp, sk))
        }
        about.submenu = abm
        m.addItem(about)
        if let sn = readSnap() {
            // "Load info": jobs, top CPU/RAM, state, thresholds, and daily counter all
            // live in a submenu so the main card stays compact.
            let loadIt = NSMenuItem(title: T("Load info"), action: nil, keyEquivalent: "")
            loadIt.image = img("chart.bar")
            let lo = NSMenu()
            lo.autoenablesItems = false
            func lrow(_ t: String) { lo.addItem(NSMenuItem(title: t, action: nil, keyEquivalent: "")) }
            if !sn.jobs.isEmpty {
                lrow(T("Supervised jobs (safe-run):"))
                for j in sn.jobs { lrow("   - \(j.name) — \(j.minutes) min") }
            }
            // "What heats / eats RAM" lists: CPU approximates heat because per-process
            // temperatures do not exist, and the label says so. If an older daemon has
            // not published the lists yet, keep the older single Top CPU row.
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
                        let cpuTxt = cpu >= 1 ? String(format: " — %.0f%% CPU", cpu) : ""
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
                    ? String(format: T("%@ session — idle"), label)
                    : String(format: T("%@ session — %.0f%% CPU in its tree"), label, tree)
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
    @objc func explainDry() {
        let body = T("""
Protection is now OFF\n- coffee-paladin has entered watch-only mode.

It still measures everything (chip, GPU, battery, fans) and writes to the event log exactly \
what it WOULD do - "would pause ffmpeg (630% CPU)" - but it sends no signal and never touches \
a single process.

Use it to see whether the thresholds suit your machine before you let the paladin freeze real \
work. Open "Show the guard log" after a heavy job and you will know if it would have interfered \
too eagerly, or not soon enough.

Remember: while this switch is off, NOTHING protects the Mac.\nFlip it back on when you are done.
""")
        _ = paladinWindow(title: T("Watch only (dry run)"), body: body,
                         buttons: ["OK"], width: 440)
    }

    @objc func enableProtection() {
        GuardCfg.set(["dry_run": false])
        expectDryRun(false)
    }

    @objc func toggleNotify() { GuardCfg.set(["notify": !GuardCfg.bool("notify", true)]) }
    @objc func toggleDry() {
        let watchOnlyNow = !GuardCfg.bool("dry_run", true)
        GuardCfg.set(["dry_run": watchOnlyNow])
        expectDryRun(watchOnlyNow)
        // Disabling protection is a serious decision; explain what it means immediately.
        if watchOnlyNow { showModally { self.explainDry() } }
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
        if let s = s, !s.paused.isEmpty { send("resume"); return }
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
            lines.append(T("In this session: no interventions yet."))
        } else {
            lines.append(String(format: T("in this session (since %@)"), dateText(ses["since"])))
            lines.append("")
            lines.append(contentsOf: labels.map { "\($0.0):  \(ses[$0.1] ?? 0)" })
        }
        if !totalEmpty {
            lines.append("")
            lines.append(String(format: T("total since %@"), dateText(sum["since"])))
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

        // FLEET: ONE number per category. Per-machine breakdown lives in the "Apple
        // fleet" submenu after clicking a Mac, where users already look when they want
        // to know which machine is cooking.
        let fleet = fleetStats()
        if fleet.count > 1 {
            var totals: [String: Int] = [:]
            for m in fleet {
                for (_, k) in labels { totals[k] = (totals[k] ?? 0) + (m.sum[k] ?? 0) }
            }
            if labels.contains(where: { (totals[$0.1] ?? 0) > 0 }) {
                lines.append("")
                lines.append(String(format: T("Across the fleet (%d machines)"), fleet.count))
                lines.append("")
                lines.append(contentsOf: labels.map { "\($0.0):  \(totals[$0.1] ?? 0)" })
                // Stale snapshots must be visible; otherwise the total hides that part
                // of the fleet has been silent for a long time.
                let staleHosts = fleet.filter { $0.age > 300 }
                if !staleHosts.isEmpty {
                    lines.append("")
                    lines.append(String(format: T("%d machine(s) not reporting - their numbers may be old"),
                                        staleHosts.count))
                }
                lines.append(T("per machine: menu > Apple fleet > click a Mac"))
            }
        }

        showModally { [weak self] in
            _ = self?.paladinWindow(title: T("Session statistics"),
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
