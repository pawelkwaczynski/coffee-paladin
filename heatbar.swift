// heatbar.swift - thermal state of the Mac in the menu bar.
//
// It measures nothing on its own: it reads ~/.thermal-guard/status.json, which thermal-guard
// writes on every cycle (every 15 s). That is why it costs no CPU and can never disagree with
// the guard. Manual commands are passed back through a file and executed by the daemon, so
// exactly one process ever decides what gets paused.
//
// In the bar:  thermometer C67 G64 B33 fan3.3k 42W RAM62% DISK46%
//   C/G/B - chip, GPU, battery;  fan - rpm (warning when stopped while hot);  W - power draw;
//   brain - RAM used;  disk - disk used;  bolt - macOS is throttling;  pause - something paused.
//
// Pick what is shown: menu > Show in the bar (checkboxes), stored in ~/.thermal-guard/heatbar.json.
// Language: TG_LANG=en|pl, or "lang" in ~/.thermal-guard/config.json. Default: en.
//
// Build:  swiftc -O -o ~/.local/bin/heatbar heatbar.swift

import Cocoa

let VERSION = "1.9.0"
let APPNAME = "coffee-paladin"
let CODENAME = "Double Espresso"
let SIGNATURE = "\(APPNAME) v\(VERSION) \u{201E}\(CODENAME)\u{201D}  ·  FOCUS FRAME 2026"

// Katalog roboczy. TG_BASE pozwala uruchomic pasek w izolacji (testy UI, demo)
// bez ryzyka, ze klikniecie w oknie powitalnym przestawi konfiguracje zywej
// instalacji. Uwaga: expandingTildeInPath NIE slucha podmienionego HOME -
// dlatego potrzebna jest osobna zmienna, a nie sztuczka z katalogiem domowym.
let base = ProcessInfo.processInfo.environment["TG_BASE"].map {
    NSString(string: $0).expandingTildeInPath
} ?? NSString(string: "~/.thermal-guard").expandingTildeInPath
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
    "no data - is thermal-guard running?": "brak danych - czy thermal-guard działa?",
    "data is stale (%@) - the guard may have died": "dane nieświeże (%@) - guard mógł paść",
    "the Mac shut down without warning: %@": "Mac zgasł bez ostrzeżenia: %@",
    "Battery:  %@": "Bateria:  %@",
    "Fans:  %@": "Wentylatory:  %@",
    "stopped": "stoi", "%d rpm": "%d obr/min", "n/a": "n/d",
    "Draw:  %.1f W": "Pobór:  %.1f W",
    "RAM:  %.1f / %.1f GB (%d%%)": "RAM:  %.1f / %.1f GB (%d%%)",
    "swap %.2f GB": "swap %.2f GB",
    "Disk:  %d / %d GB used (%d%%)": "Dysk:  %d / %d GB zajęte (%d%%)",
    "Power:  %@": "Zasilanie:  %@",
    "AC adapter": "zasilacz", "battery %@": "bateria %@",
    "Load:  %.2f / %d cores    CPU available: %d%%": "Obciążenie:  %.2f / %d rdzeni    CPU dostępne: %d%%",
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
    "Pause jobs when the Mac overheats": "Włącz pauzowanie przy przegrzaniu",
    "OFF - the Mac is only being watched": "WYŁĄCZONE — Mac jest tylko obserwowany",
    "Show in the bar": "Pokaż na pasku",
    "Export report for a repair shop": "Raport dla serwisu",
    "As PDF...": "Jako PDF...",
    "As plain text (TXT)...": "Jako tekst (TXT)...",
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
    "Name this Mac in the fleet...": "Nazwij tego Maca we flocie...",
    "With five identical MacBooks the system hostname says nothing. This name shows in the fleet table and menu on every machine. Empty = system hostname.":
        "Przy pięciu identycznych MacBookach nazwa systemowa nic nie mówi. Ta nazwa pokazuje się w tabeli floty i w menu na każdej maszynie. Puste = nazwa systemowa.",
    "Buy me a double espresso...": "Postaw mi podwójne espresso...",
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
    "Keep-awake: while %@ is running": "Czuwanie: dopóki działa %@",
    "Keep-awake: while downloading": "Czuwanie: dopóki trwa pobieranie",
    "Keep-awake: indefinitely": "Czuwanie: bezterminowo",
    "Heavy jobs (safe-run)": "Ciężkie zadania (safe-run)",
    "Efficiency cores only (cool and quiet)": "Tylko rdzenie energooszczędne (chłodno i cicho)",
    "All cores (fast - the guard still watches the temperature)":
        "Wszystkie rdzenie (szybko — temperatury i tak pilnuje guard)",
    "CPU limit for heavy jobs": "Limit CPU dla ciężkich zadań",
    "below 100% the whole job gets tiny micro-pauses (works for any program)":
        "poniżej 100% całe zadanie dostaje mikropauzy (działa z każdym programem)",
    "Start at login": "Uruchamiaj przy starcie komputera",
    "About my Mac": "O moim Macu",
    "Phone push (ntfy.sh)...": "Push na telefon (ntfy.sh)...",
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
    "Keep the Mac awake while heavy jobs run": "Nie usypiaj Maca, gdy działają ciężkie zadania",
    "Keeping the Mac awake (heavy job running)": "Trzymam Maca w czuwaniu (działa ciężkie zadanie)",
    "resume at %.0f C, terminate at %.0f C": "wznowienie przy %.0f C, ubicie przy %.0f C",
    "no fans (fanless Mac)": "brak wentylatorów (Mac bez wentylatorów)",
    "What does watch-only mode do?": "Co daje tryb „tylko obserwuj”?",
    "Report a problem (GitHub)...": "Zgłoś problem lub pomysł (GitHub)...",
    "Write to the author...": "Napisz do autora...",
    "Watch only (dry run)": "Tylko obserwuj (dry run)",
    "WATCH-ONLY MODE - measuring and alerting, pausing nothing":
        "TRYB OBSERWACJI - mierzę i alarmuję, niczego nie wstrzymuję",
    "Enable protection (pause heavy jobs when hot)":
        "Włącz ochronę (wstrzymuj ciężkie zadania, gdy gorąco)",
    """
With this on, thermal-guard measures everything and writes to its log exactly what it WOULD do \
- "would pause Python (595% CPU)" - but sends no signal and never touches a single process.

Use it to see whether the thresholds suit your machine before you let the tool freeze real work. \
Open "Show the guard log" after a heavy job and you will know if it would have interfered too \
eagerly, or not soon enough.

Remember to switch it off afterwards: in this mode nothing protects the Mac.
""": """
Przy włączonym trybie thermal-guard mierzy wszystko i zapisuje w logu dokładnie to, co ZROBIŁBY \
- „pauza Python (595% CPU)” - ale nie wysyła żadnego sygnału i nie rusza ani jednego procesu.

Służy do sprawdzenia, czy progi pasują do Twojej maszyny, zanim pozwolisz narzędziu zamrażać \
realną pracę. Po ciężkim zadaniu otwórz „Pokaż log guarda” i zobaczysz, czy wtrącałby się za \
gorliwie, czy odwrotnie - za późno.

Pamiętaj potem wyłączyć: w tym trybie nic nie chroni Maca.
""",
]

let RU: [String: String] = [
    "Keep the Mac awake while heavy jobs run": "Не давать Mac засыпать, пока идут тяжёлые задачи",
    "Keeping the Mac awake (heavy job running)": "Держу Mac в бодрствовании (идёт тяжёлая задача)",
    "no data - is thermal-guard running?": "нет данных - работает ли thermal-guard?",
    "data is stale (%@) - the guard may have died": "данные устарели (%@) - демон мог упасть",
    "the Mac shut down without warning: %@": "Mac выключился без предупреждения: %@",
    "Battery:  %@": "Батарея:  %@",
    "Fans:  %@": "Вентиляторы:  %@",
    "stopped": "стоит",
    "%d rpm": "%d об/мин",
    "n/a": "н/д",
    "Draw:  %.1f W": "Мощность:  %.1f Вт",
    "RAM:  %.1f / %.1f GB (%d%%)": "RAM:  %.1f / %.1f ГБ (%d%%)",
    "swap %.2f GB": "своп %.2f ГБ",
    "Disk:  %d / %d GB used (%d%%)": "Диск:  занято %d / %d ГБ (%d%%)",
    "Power:  %@": "Питание:  %@",
    "AC adapter": "адаптер питания",
    "battery %@": "батарея %@",
    "Load:  %.2f / %d cores    CPU available: %d%%": "Нагрузка:  %.2f / %d ядер    CPU доступно: %d%%",
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
    "Pause jobs when the Mac overheats": "Приостанавливать задачи при перегреве",
    "OFF - the Mac is only being watched": "ВЫКЛЮЧЕНО — Mac только под наблюдением",
    "Show in the bar": "Показывать в строке меню",
    "Export report for a repair shop": "Отчёт для сервисного центра",
    "As PDF...": "В PDF...",
    "As plain text (TXT)...": "Текстом (TXT)...",
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
    "resume at %.0f C, terminate at %.0f C": "возобновление при %.0f C, завершение при %.0f C",
    "What does watch-only mode do?": "Что делает режим наблюдения?",
    "Report a problem (GitHub)...": "Сообщить о проблеме (GitHub)...",
    "Write to the author...": "Написать автору...",
    "Watch only (dry run)": "Только наблюдение (dry run)",
    "WATCH-ONLY MODE - measuring and alerting, pausing nothing": "РЕЖИМ НАБЛЮДЕНИЯ - измеряю и предупреждаю, ничего не приостанавливаю",
    "Enable protection (pause heavy jobs when hot)": "Включить защиту (пауза тяжёлых задач при нагреве)",
    "Language": "Язык",
    "Sounds": "Звуки",
    "Name this Mac in the fleet...": "Имя этого Mac в парке...",
    "With five identical MacBooks the system hostname says nothing. This name shows in the fleet table and menu on every machine. Empty = system hostname.":
        "Когда MacBook пять одинаковых, системное имя ничего не говорит. Это имя видно в таблице парка и в меню на каждой машине. Пустое = системное имя.",
    "Buy me a double espresso...": "Угостить двойным эспрессо...",
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
    "Keep-awake: while %@ is running": "Бодрствование: пока работает %@",
    "Keep-awake: while downloading": "Бодрствование: пока идёт загрузка",
    "Keep-awake: indefinitely": "Бодрствование: бессрочно",
    "Heavy jobs (safe-run)": "Тяжёлые задачи (safe-run)",
    "Efficiency cores only (cool and quiet)": "Только энергоэффективные ядра (холодно и тихо)",
    "All cores (fast - the guard still watches the temperature)":
        "Все ядра (быстро — за температурой всё равно следит guard)",
    "CPU limit for heavy jobs": "Лимит CPU для тяжёлых задач",
    "below 100% the whole job gets tiny micro-pauses (works for any program)":
        "ниже 100% вся задача получает микропаузы (работает с любой программой)",
    "Start at login": "Запускать при входе в систему",
    "About my Mac": "Об этом Mac",
    "Phone push (ntfy.sh)...": "Push на телефон (ntfy.sh)...",
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
    "no data - is thermal-guard running?": "没有数据 - thermal-guard 在运行吗？",
    "data is stale (%@) - the guard may have died": "数据已过期（%@）- 守护进程可能已停止",
    "the Mac shut down without warning: %@": "Mac 毫无预警地关机了：%@",
    "Battery:  %@": "电池：  %@",
    "Fans:  %@": "风扇：  %@",
    "stopped": "停转",
    "%d rpm": "%d 转/分",
    "n/a": "无",
    "Draw:  %.1f W": "功耗：  %.1f W",
    "RAM:  %.1f / %.1f GB (%d%%)": "内存：  %.1f / %.1f GB（%d%%）",
    "swap %.2f GB": "交换 %.2f GB",
    "Disk:  %d / %d GB used (%d%%)": "磁盘：  已用 %d / %d GB（%d%%）",
    "Power:  %@": "电源：  %@",
    "AC adapter": "电源适配器",
    "battery %@": "电池 %@",
    "Load:  %.2f / %d cores    CPU available: %d%%": "负载：  %.2f / %d 核    CPU 可用：%d%%",
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
    "Pause jobs when the Mac overheats": "过热时暂停任务",
    "OFF - the Mac is only being watched": "已关闭 —— 仅在观察这台 Mac",
    "Show in the bar": "菜单栏显示内容",
    "Export report for a repair shop": "导出维修报告",
    "As PDF...": "PDF 格式...",
    "As plain text (TXT)...": "纯文本（TXT）...",
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
    "resume at %.0f C, terminate at %.0f C": "%.0f C 时恢复，%.0f C 时终止",
    "What does watch-only mode do?": "「仅观察」模式是什么？",
    "Report a problem (GitHub)...": "报告问题（GitHub）...",
    "Write to the author...": "给作者写信...",
    "Watch only (dry run)": "仅观察（dry run）",
    "WATCH-ONLY MODE - measuring and alerting, pausing nothing": "仅观察模式 - 只测量和提醒，不暂停任何任务",
    "Enable protection (pause heavy jobs when hot)": "启用保护（过热时暂停繁重任务）",
    "Language": "语言",
    "Sounds": "提示音",
    "Name this Mac in the fleet...": "为此 Mac 设置机群名称...",
    "With five identical MacBooks the system hostname says nothing. This name shows in the fleet table and menu on every machine. Empty = system hostname.":
        "五台一样的 MacBook,系统主机名毫无意义。此名称会显示在每台机器的机群表和菜单中。留空 = 系统主机名。",
    "Buy me a double espresso...": "请我喝双份浓缩咖啡...",
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
    "Keep-awake: while %@ is running": "保持唤醒:%@ 运行期间",
    "Keep-awake: while downloading": "保持唤醒:下载期间",
    "Keep-awake: indefinitely": "保持唤醒:无限期",
    "Heavy jobs (safe-run)": "繁重任务(safe-run)",
    "Efficiency cores only (cool and quiet)": "仅能效核心(凉爽安静)",
    "All cores (fast - the guard still watches the temperature)":
        "全部核心(快 - 温度仍由 guard 监控)",
    "CPU limit for heavy jobs": "繁重任务的 CPU 限制",
    "below 100% the whole job gets tiny micro-pauses (works for any program)":
        "低于 100% 时整个任务会得到微暂停(适用于任何程序)",
    "Start at login": "登录时启动",
    "About my Mac": "关于我的 Mac",
    "Phone push (ntfy.sh)...": "手机推送(ntfy.sh)...",
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
    "no data - is thermal-guard running?": "sin datos - ¿está funcionando thermal-guard?",
    "data is stale (%@) - the guard may have died": "datos obsoletos (%@) - el guardián pudo detenerse",
    "the Mac shut down without warning: %@": "el Mac se apagó sin aviso: %@",
    "Battery:  %@": "Batería:  %@",
    "Fans:  %@": "Ventiladores:  %@",
    "stopped": "parado",
    "%d rpm": "%d rpm",
    "n/a": "n/d",
    "Draw:  %.1f W": "Consumo:  %.1f W",
    "RAM:  %.1f / %.1f GB (%d%%)": "RAM:  %.1f / %.1f GB (%d%%)",
    "swap %.2f GB": "swap %.2f GB",
    "Disk:  %d / %d GB used (%d%%)": "Disco:  %d / %d GB usados (%d%%)",
    "Power:  %@": "Alimentación:  %@",
    "AC adapter": "adaptador de corriente",
    "battery %@": "batería %@",
    "Load:  %.2f / %d cores    CPU available: %d%%": "Carga:  %.2f / %d núcleos    CPU disponible: %d%%",
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
    "Pause jobs when the Mac overheats": "Pausar tareas cuando el Mac se recalienta",
    "OFF - the Mac is only being watched": "DESACTIVADO: el Mac solo está siendo observado",
    "Show in the bar": "Mostrar en la barra",
    "Export report for a repair shop": "Informe para el servicio técnico",
    "As PDF...": "Como PDF...",
    "As plain text (TXT)...": "Como texto (TXT)...",
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
    "resume at %.0f C, terminate at %.0f C": "reanuda a %.0f C, termina a %.0f C",
    "What does watch-only mode do?": "¿Qué hace el modo de solo observación?",
    "Report a problem (GitHub)...": "Informar de un problema (GitHub)...",
    "Write to the author...": "Escribir al autor...",
    "Watch only (dry run)": "Solo observación (dry run)",
    "WATCH-ONLY MODE - measuring and alerting, pausing nothing": "MODO OBSERVACIÓN - mido y aviso, no pauso nada",
    "Enable protection (pause heavy jobs when hot)": "Activar la protección (pausar tareas pesadas al calentarse)",
    "Language": "Idioma",
    "Sounds": "Sonidos",
    "Name this Mac in the fleet...": "Nombra este Mac en la flota...",
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
    "Buy me a double espresso...": "Invítame a un espresso doble...",
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
    "Keep-awake: while %@ is running": "Despierto: mientras corre %@",
    "Keep-awake: while downloading": "Despierto: mientras se descarga",
    "Keep-awake: indefinitely": "Despierto: indefinidamente",
    "Heavy jobs (safe-run)": "Tareas pesadas (safe-run)",
    "Efficiency cores only (cool and quiet)": "Solo núcleos de eficiencia (frío y silencioso)",
    "All cores (fast - the guard still watches the temperature)":
        "Todos los núcleos (rápido - el guard sigue vigilando la temperatura)",
    "CPU limit for heavy jobs": "Límite de CPU para tareas pesadas",
    "below 100% the whole job gets tiny micro-pauses (works for any program)":
        "por debajo del 100% la tarea recibe micropausas (funciona con cualquier programa)",
    "Start at login": "Iniciar al iniciar sesión",
    "About my Mac": "Acerca de mi Mac",
    "Phone push (ntfy.sh)...": "Push al teléfono (ntfy.sh)...",
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

/// Wlasne logo uzytkownika: ~/.thermal-guard/logo.png (czarny znak na przezroczystym tle).
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
        let W: CGFloat = 440, H: CGFloat = 470
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: W, height: H),
                           styleMask: [.titled, .fullSizeContentView], backing: .buffered, defer: false)
        win.titlebarAppearsTransparent = true
        win.titleVisibility = .hidden
        win.isMovableByWindowBackground = true
        win.level = .floating
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
            battPct: numInt(j["battery_pct"])))
    }
    return out
}

func fleetAge(_ s: TimeInterval) -> String {
    // podloga, nie zaokraglenie: 95 s to "1 min temu", nie "2 min temu"
    if s < 60 { return T("now") }
    if s < 7200 { return String(format: T("%d min ago"), max(1, Int(s / 60))) }
    return String(format: T("%d h ago"), Int(s / 3600))
}

/// Stopka: kolorowe logo z ~/.thermal-guard/logo_footer.png (w ciemnym motywie wariant
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
            NSWorkspace.shared.open(url)
        }
    }

    required init?(coder: NSCoder) { fatalError() }
}

/// Naglowek menu: logo + nazwa + wersja, wszystko WYSRODKOWANE. Gdy w ~/.thermal-guard
/// lezy logo.png (u Pawla: znak AIrON), pokazujemy je; bez pliku rysujemy wlasny squircle.
final class HeaderRow: NSView {
    init() {
        super.init(frame: NSRect(x: 0, y: 0, width: 400, height: 88))
        let W: CGFloat = 400
        if let logo = customLogo() {
            // znak poziomy (wordmark): srodek, wysokosc 22, szerokosc wg proporcji
            let ratio = logo.size.width / max(logo.size.height, 1)
            let h: CGFloat = 24
            let w = min(h * ratio, 330)
            let iv = NSImageView(frame: NSRect(x: (W - w) / 2, y: 58, width: w, height: h))
            iv.image = logo
            iv.imageScaling = .scaleProportionallyUpOrDown
            iv.contentTintColor = .labelColor
            addSubview(iv)
        } else {
            let iv = NSImageView(frame: NSRect(x: (W - 22) / 2, y: 58, width: 22, height: 22))
            iv.image = makeLogo(22)
            addSubview(iv)
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
        app.frame = NSRect(x: 0, y: 38, width: W, height: 18)
        addSubview(app)

        let motto = NSTextField(labelWithString: MOTTO)
        motto.font = .systemFont(ofSize: 11, weight: .regular)
        motto.textColor = .labelColor
        motto.alignment = .center
        motto.frame = NSRect(x: 0, y: 22, width: W, height: 14)
        addSubview(motto)

        let name = NSTextField(labelWithString: T("A project of the AIrON student research club."))
        name.font = .systemFont(ofSize: 11)
        name.textColor = .secondaryLabelColor
        name.alignment = .center
        name.frame = NSRect(x: 0, y: 6, width: W, height: 14)
        addSubview(name)

        // Nazwa produktu jest klikalna: otwiera paladyna przypietego pod paskiem.
        // Klikalny jest sam napis, nie caly nagłówek - zeby przypadkowe klikniecie
        // w logo albo w motto nie wywolywalo okna.
        nazwaKlikalna = app.frame
        addTrackingArea(NSTrackingArea(rect: app.frame,
                                       options: [.mouseEnteredAndExited, .activeAlways, .cursorUpdate],
                                       owner: self, userInfo: nil))
    }
    required init?(coder: NSCoder) { fatalError() }

    private var nazwaKlikalna: NSRect = .zero

    override func cursorUpdate(with event: NSEvent) {
        NSCursor.pointingHand.set()
    }

    override func mouseUp(with event: NSEvent) {
        let p = convert(event.locationInWindow, from: nil)
        guard nazwaKlikalna.contains(p) else { return }
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
        (wlaczony ? NSColor.systemGreen : NSColor.tertiaryLabelColor).setFill()
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
        wlaczony.toggle()
        if let a = action { NSApp.sendAction(a, to: target, from: self) }
    }
}


/// Wiersz menu z przelacznikiem: etykieta po lewej, przelacznik po prawej.
/// Dwie rzeczy wlaczane najczesciej - pauzowanie przy przegrzaniu i autostart -
/// zasluguja na element, ktorego stan widac bez czytania.
final class SwitchRow: NSView {
    init(_ tytul: String, on: Bool, target: AnyObject, action: Selector,
         opis: String? = nil, opisNaCzerwono: Bool = false) {
        let W: CGFloat = 400, H: CGFloat = opis == nil ? 30 : 44
        super.init(frame: NSRect(x: 0, y: 0, width: W, height: H))
        let etykieta = NSTextField(labelWithString: tytul)
        etykieta.font = .menuFont(ofSize: 13)
        etykieta.textColor = .labelColor
        etykieta.frame = NSRect(x: 21, y: H - 21, width: W - 90, height: 17)
        addSubview(etykieta)
        if let opis = opis {
            let pod = NSTextField(labelWithString: opis)
            pod.font = .systemFont(ofSize: 11, weight: opisNaCzerwono ? .medium : .regular)
            pod.textColor = opisNaCzerwono ? .systemRed : .secondaryLabelColor
            pod.frame = NSRect(x: 21, y: 6, width: W - 90, height: 14)
            addSubview(pod)
        }
        let sw = Przelacznik(on: on, target: target, action: action)
        sw.frame = NSRect(x: W - 62, y: (H - 22) / 2, width: 38, height: 22)
        addSubview(sw)
    }
    required init?(coder: NSCoder) { fatalError() }
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
    case chip, gpu, battery, fans, watts, ram, disk, throttle, paused

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
        }
    }

    /// Safety-related items are on by default; RAM and disk are an extra.
    var byDefault: Bool {
        switch self {
        case .ram, .disk: return false
        default: return true
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
}

let prefs = Prefs()

// MARK: - guard configuration (thresholds live in config.json, the daemon re-reads it every cycle)

/// Odczyt i zapis config.json guarda. Zawsze scalamy z istniejaca trescia — plik nalezy do
/// demona i zawiera znacznie wiecej niz to, co pokazuje pasek.
enum GuardCfg {
    static func all() -> [String: Any] {
        guard let d = FileManager.default.contents(atPath: configPath),
              let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return [:] }
        return j
    }

    static func double(_ key: String, _ fallback: Double) -> Double {
        (all()[key] as? Double) ?? Double((all()[key] as? Int) ?? 0).nonZero ?? fallback
    }

    static func bool(_ key: String, _ fallback: Bool) -> Bool { (all()[key] as? Bool) ?? fallback }
    static func string(_ key: String, _ fallback: String) -> String { (all()[key] as? String) ?? fallback }

    static func set(_ values: [String: Any]) {
        var j = all()
        for (k, v) in values { j[k] = v }
        if let d = try? JSONSerialization.data(withJSONObject: j, options: [.prettyPrinted, .sortedKeys]) {
            // .atomic: plik dzieli z nami demon Pythona — uciety zapis = config na DEFAULTS
            try? d.write(to: URL(fileURLWithPath: configPath), options: .atomic)
        }
    }
}

extension Double { var nonZero: Double? { self == 0 ? nil : self } }

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
    static let services = ["pl.pawel.thermal-guard", "pl.pawel.heatbar"]
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

        var y = height - 26

        let label = NSTextField(labelWithString: title)
        label.font = .menuFont(ofSize: 13)
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

/// Chip temperature graph from the history file - block characters, no drawing needed.
func sparkline(limit: Int = 40) -> (String, Double, Double)? {
    guard let text = try? String(contentsOfFile: historyPath, encoding: .utf8) else { return nil }
    var values: [Double] = []
    for line in text.split(separator: "\n").suffix(limit + 1) {
        let c = line.split(separator: ",", omittingEmptySubsequences: false)
        if c.count > 2, let v = Double(c[2]) { values.append(v) }
    }
    guard values.count >= 3 else { return nil }
    let blocks = Array("▁▂▃▄▅▆▇█")
    let lo = values.min()!, hi = values.max()!
    let span = max(hi - lo, 1.0)
    let line = values.map { v -> Character in
        let i = Int(((v - lo) / span) * Double(blocks.count - 1))
        return blocks[min(max(i, 0), blocks.count - 1)]
    }
    return (String(line), lo, hi)
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

    init() {
        super.init(frame: NSRect(x: 0, y: 0, width: 400, height: 30))
        let w: CGFloat = 66, gap: CGFloat = 6
        // wysrodkowane: 5 przyciskow + 4 odstepy w osi karty
        var x: CGFloat = (400 - (5 * w + 4 * gap)) / 2
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
            b.frame = NSRect(x: x, y: 3, width: w, height: 22)
            addSubview(b)
            x += w + gap
        }
    }

    required init?(coder: NSCoder) { fatalError() }

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
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in
            guard let self = self else { return }
            self.refresh()
            self.tick += 1
            if self.tick % 6 == 0 { self.refreshFleet() }   // flota co ~30 s, w tle
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
        switch s.level {
        case 3: return .systemRed
        case 2: return .systemOrange
        case 1: return .systemYellow
        default: return .labelColor
        }
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
        if prefs.enabled(.watts), let w = s.watts, w >= 1 {
            gap(); out.append(icon("bolt.fill", fallback: "W")); text(String(format: " %.0fW", w))
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
        if s.dryRun { gap(); out.append(icon("eye", fallback: "obs")) }
        if s.keepAwake { gap(); out.append(icon(MUG_FILL, fallback: "awake")) }
        if prefs.enabled(.paused), !s.paused.isEmpty {
            gap(); out.append(icon("pause.circle.fill", fallback: "||"))
        }

        out.addAttributes([.foregroundColor: tint(s), .font: bold],
                          range: NSRange(location: 0, length: out.length))
        item.button?.attributedTitle = out

        var tip = s.reason.isEmpty ? "thermal-guard: " + T("calm") : s.reason
        if let e = s.eta { tip += String(format: "\n%.0f min", e) }
        item.button?.toolTip = tip
    }

    func menuNeedsUpdate(_ m: NSMenu) {
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
            m.addItem(NSMenuItem(title: T("no data - is thermal-guard running?"), action: nil, keyEquivalent: ""))
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

        row("Chip:  " + (s.chip.map { String(format: "%.1f °C", $0) } ?? na)
            + (s.gpu != nil ? String(format: "     GPU: %.1f °C", s.gpu!) : ""))
        row(String(format: T("Battery:  %@"), s.batt.map { String(format: "%.1f °C", $0) } ?? na))
        let fanTxt = s.fans.isEmpty ? na
            : s.fans.map { $0 == 0 ? T("stopped") : String(format: T("%d rpm"), $0) }.joined(separator: ", ")
        row(String(format: T("Fans:  %@"), fanTxt))
        if let w = s.watts { row(String(format: T("Draw:  %.1f W"), w)) }
        if let u = s.ramUsed, let t = s.ramTotal, t > 0 {
            var line = String(format: T("RAM:  %.1f / %.1f GB (%d%%)"), u, t, Int(100 * u / t))
            if let sw = s.swap, sw > 0.01 { line += "     " + String(format: T("swap %.2f GB"), sw) }
            row(line)
        }
        if let du = s.diskUsed, let dt = s.diskTotal, let dp = s.diskPct {
            row(String(format: T("Disk:  %d / %d GB used (%d%%)"), du, dt, dp))
        }
        row(String(format: T("Power:  %@"),
                   s.onAC ? T("AC adapter")
                          : String(format: T("battery %@"), s.pct.map { "\($0)%" } ?? "?")))
        row(String(format: T("Load:  %.2f / %d cores    CPU available: %d%%"),
                  s.load, ProcessInfo.processInfo.processorCount,
                  s.cpuLimit))
        if s.keepAwake {
            let a = Awake.read()
            switch a["mode"] as? String {
            case "timer":
                let left = max(0, (a["until"] as? Double ?? 0) - Date().timeIntervalSince1970)
                row(String(format: T("Keep-awake: %@ left"), fmtDur(Int(left / 60))))
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

        if let (line, lo, hi) = sparkline() {
            m.addItem(.separator())
            mono("  " + line)
            row(String(format: T("   readings: %.0f-%.0f C"), lo, hi))
        }
        if let t = s.trend, t > 0.5 {
            if let e = s.eta {
                row(String(format: T("rising %.1f C/min - about %.0f min to pause"), t, e))
            } else {
                row(String(format: T("rising %.1f C/min"), t))
            }
        }

        // akcja zamrozenia TUZ POD odczytami i wykresem — tam, gdzie patrzysz, gdy jest goraco
        m.addItem(.separator())
        // WLACZNIK OCHRONY - najwazniejsza decyzja w calej aplikacji, wiec nie chowamy jej
        // w Ustawieniach. Przelacznik ON = ochrona dziala (dry_run = false).
        let obserwuje = GuardCfg.bool("dry_run", true)
        let ochrona = NSMenuItem()
        ochrona.view = SwitchRow(T("Pause jobs when the Mac overheats"),
                                 on: !obserwuje,
                                 target: self, action: #selector(toggleDry),
                                 opis: obserwuje ? T("OFF - the Mac is only being watched") : nil,
                                 opisNaCzerwono: obserwuje)
        m.addItem(ochrona)
        m.addItem(.separator())
        if !s.paused.isEmpty {
            let it = m.addItem(withTitle: T("Resume paused jobs"),
                               action: #selector(resume), keyEquivalent: "")
            it.target = self
            it.image = img("play.circle")
        } else {
            let it = m.addItem(withTitle: T("Freeze all heavy jobs now"),
                               action: #selector(freeze), keyEquivalent: "")
            it.target = self
            it.image = img("pause.circle")
        }

        m.addItem(.separator())
        // "Informacje o obciazeniu": zadania, top CPU/RAM, stan, progi, licznik dnia —
        // wszystko w rozwijanym podmenu, zeby glowna karta zostala zwarta
        let loadIt = NSMenuItem(title: T("Load info"), action: nil, keyEquivalent: "")
        loadIt.image = img("chart.bar")
        let lo = NSMenu()
        lo.autoenablesItems = false
        func lrow(_ t: String) { lo.addItem(NSMenuItem(title: t, action: nil, keyEquivalent: "")) }
        if !s.jobs.isEmpty {
            lrow(T("Supervised jobs (safe-run):"))
            for j in s.jobs { lrow("   - \(j.name) — \(j.minutes) min") }
        }
        // listy "co grzeje / co zjada RAM": CPU jest przyblizeniem ciepla (per-proces
        // temperatur nie ma) i tak to opisujemy. Gdy guard jeszcze nie opublikowal list
        // (stara wersja demona), zostaje dawny pojedynczy wiersz Top CPU.
        if !s.topCpuList.isEmpty {
            lrow(T("Heating the most now (CPU ≈ heat):"))
            for t in s.topCpuList { lrow("   - \(t.name) — \(t.cpu)% CPU") }
        } else if let p = s.topProc, let c = s.topCPU {
            lrow(String(format: T("Top CPU:  %@ (%d%%)"), p, c))
        }
        if !s.topRamList.isEmpty {
            lrow(T("Eating the most RAM:"))
            for t in s.topRamList { lrow(String(format: "   - %@ — %.1f GB", t.name, t.gb)) }
        }
        if !s.paused.isEmpty {
            lrow(String(format: T("Paused: %@"), s.paused.joined(separator: ", "))
                 + (s.manualPause ? T("  (manual)") : ""))
        } else {
            let names = [T("calm"), T("warm"), T("HOT - paused"), T("CRITICAL")]
            lrow(String(format: T("State: %@"), names[min(s.level, 3)])
                 + (s.reason.isEmpty ? "" : " — \(s.reason)"))
        }
        if let pp = s.thrPause, let pk = s.thrKill {
            lrow(String(format: T("Chip thresholds:  pause %.0f C, kill %.0f C"), pp, pk))
        }
        if s.pausesToday > 0 || s.killsToday > 0 {
            lrow(String(format: T("Today: %d x pause"), s.pausesToday)
                 + (s.killsToday > 0 ? String(format: T(", %d x kill"), s.killsToday) : ""))
        }
        loadIt.submenu = lo
        m.addItem(loadIt)
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
        let chipRow = NSMenuItem()
        chipRow.view = SliderRow(
            title: T("Chip pause threshold"), min: 55, max: 100, current: pauseNow, unit: "°C",
            describe: thresholdWarning,
            derive: { v in String(format: T("resume at %.0f C, terminate at %.0f C"),
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
        let jobsHdr = NSMenuItem(title: T("Heavy jobs (safe-run)"), action: nil, keyEquivalent: "")
        jobsHdr.isEnabled = false
        ss.addItem(jobsHdr)
        let mode = GuardCfg.string("job_cores_mode", "efficiency")
        let eff = NSMenuItem(title: T("Efficiency cores only (cool and quiet)"),
                             action: #selector(coresEfficiency), keyEquivalent: "")
        eff.target = self
        eff.state = mode == "all" ? .off : .on
        ss.addItem(eff)
        let allc = NSMenuItem(title: T("All cores (fast - the guard still watches the temperature)"),
                              action: #selector(coresAll), keyEquivalent: "")
        allc.target = self
        allc.state = mode == "all" ? .on : .off
        ss.addItem(allc)
        let cpuRow = NSMenuItem()
        cpuRow.view = SliderRow(
            title: T("CPU limit for heavy jobs"), min: 50, max: 100,
            current: GuardCfg.double("job_cpu_percent", 95), unit: "%",
            describe: { _ in (T("below 100% the whole job gets tiny micro-pauses (works for any program)"), "") }) { v in
            GuardCfg.set(["job_cpu_percent": Int(v)])
        }
        ss.addItem(cpuRow)
        ss.addItem(.separator())

        let notif = NSMenuItem(title: T("Notifications"), action: #selector(toggleNotify), keyEquivalent: "")
        notif.target = self
        notif.state = GuardCfg.bool("notify", true) ? .on : .off
        ss.addItem(notif)

        let help = NSMenuItem(title: T("What does watch-only mode do?"), action: #selector(explainDry), keyEquivalent: "")
        help.target = self
        ss.addItem(help)
        ss.addItem(.separator())

        let snd = NSMenuItem(title: T("Sounds"), action: #selector(toggleSound), keyEquivalent: "")
        snd.target = self
        snd.state = GuardCfg.bool("sound", true) ? .on : .off
        ss.addItem(snd)

        let kaAuto = NSMenuItem(title: T("Keep the Mac awake while heavy jobs run"),
                                action: #selector(toggleAwake), keyEquivalent: "")
        kaAuto.target = self
        kaAuto.state = GuardCfg.bool("keep_awake_auto", false) ? .on : .off
        ss.addItem(kaAuto)

        let ntfy = NSMenuItem(title: T("Phone push (ntfy.sh)..."),
                              action: #selector(ntfyDialog), keyEquivalent: "")
        ntfy.target = self
        ntfy.state = GuardCfg.string("ntfy_topic", "").isEmpty ? .off : .on
        ss.addItem(ntfy)

        let flabel = NSMenuItem(title: T("Name this Mac in the fleet..."),
                                action: #selector(fleetNameDialog), keyEquivalent: "")
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
            arow(T("no data - is thermal-guard running?"))
        } else {
            arow(String(format: T("Model:  %@"), (hw["model_name"] as? String) ?? "?"))
            arow(String(format: T("Chip:  %@"), (hw["chip"] as? String) ?? "?"))
            arow(String(format: T("Cores:  %d performance + %d efficiency"),
                        (hw["p_cores"] as? Int) ?? 0, (hw["e_cores"] as? Int) ?? 0))
            arow(String(format: T("RAM:  %d GB"), (hw["ram_gb"] as? Int) ?? 0))
            arow(String(format: T("Fans:  %d"), (hw["fan_count"] as? Int) ?? 0))
            arow(String(format: T("macOS:  %@"), (hw["macos"] as? String) ?? "?"))
            if let ser = hw["serial"] as? String, !ser.isEmpty {
                arow(String(format: T("Serial:  %@"), ser))
            }
            if let cyc = hw["battery_cycles"] as? Int {
                let warn = (hw["battery_failure"] as? Bool) == true ? "  (!)" : ""
                arow(String(format: T("Battery cycles:  %@"), "\(cyc)\(warn)"))
            }
            arow(String(format: T("Chip sensor (macmon):  %@"),
                        (hw["chip_sensor"] as? Bool) == true ? T("yes") : T("no")))
            let sp = GuardCfg.double("soc_pause_c", 85), sk = GuardCfg.double("soc_kill_c", 90)
            arow(String(format: T("Chip thresholds:  pause %.0f C, kill %.0f C"), sp, sk))
        }
        about.submenu = abm
        m.addItem(about)

        // eksport: uzytkownik wybiera format, nie my
        let rep = NSMenuItem(title: T("Export report for a repair shop"), action: nil, keyEquivalent: "")
        rep.image = img("wrench.and.screwdriver")
        let rm = NSMenu()
        rm.autoenablesItems = false
        rm.addItem(withTitle: T("As PDF..."), action: #selector(reportPDF), keyEquivalent: "").target = self
        rm.addItem(withTitle: T("As plain text (TXT)..."), action: #selector(reportTXT), keyEquivalent: "").target = self
        rep.submenu = rm
        m.addItem(rep)
        let logIt = m.addItem(withTitle: T("Show the guard log"), action: #selector(openLog), keyEquivalent: "")
        logIt.target = self
        logIt.image = img("text.alignleft")

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
            for h0 in hosts {
                let h = FleetHost(name: h0.name, model: h0.model, serial: h0.serial,
                                  age: h0.age + cacheDrift, chip: h0.chip,
                                  fans: h0.fans, watts: h0.watts, ramPct: h0.ramPct,
                                  level: h0.level, paused: h0.paused, onAC: h0.onAC,
                                  battPct: h0.battPct)
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
                var bits: [String] = []
                if let c = h.chip { bits.append(String(format: "%.0f °C", c)) }
                if let f = h.fans {
                    bits.append(f >= 1000 ? String(format: "%.1fk rpm", Double(f) / 1000.0)
                                          : "\(f) rpm")
                }
                if let w = h.watts { bits.append(String(format: "%.0f W", w)) }
                if let r = h.ramPct { bits.append("RAM \(r)%") }
                if !h.onAC, let b = h.battPct { bits.append(T("battery") + " \(b)%") }
                let names = [T("calm"), T("warm"), T("HOT - paused"), T("CRITICAL")]
                bits.append(names[min(max(h.level, 0), 3)])
                if !h.paused.isEmpty {
                    bits.append(T("paused") + ": " + h.paused.joined(separator: ", "))
                }
                bits.append(fleetAge(h.age))
                let tytul = h.model.isEmpty ? h.name : "\(h.name)  [\(h.model)]"
                let it = NSMenuItem(title: tytul + ":   " + bits.joined(separator: "  ·  "),
                                    action: nil, keyEquivalent: "")
                if !h.serial.isEmpty || !h.model.isEmpty {
                    it.toolTip = [h.model, h.serial.isEmpty ? "" : "SN " + h.serial]
                        .filter { !$0.isEmpty }.joined(separator: "  ·  ")
                }
                fmenu.addItem(it)
            }
        } else {
            frow(T("no fleet folder - run: fleet --setup"))
        }
        fleetIt.submenu = fmenu
        m.addItem(fleetIt)

        m.addItem(.separator())
        m.addItem(withTitle: T("Report a problem (GitHub)..."), action: #selector(openIssues), keyEquivalent: "").target = self
        m.addItem(withTitle: T("Write to the author..."), action: #selector(mailAuthor), keyEquivalent: "").target = self
        let coffee = m.addItem(withTitle: T("Buy me a double espresso..."),
                               action: #selector(buyCoffee), keyEquivalent: "")
        coffee.target = self
        coffee.image = img(MUG_FILL)

        // autostart przy logowaniu — default ON (tak instaluje install.sh)
        let auto = NSMenuItem()
        auto.view = SwitchRow(T("Start at login"), on: Autostart.enabled(),
                              target: self, action: #selector(toggleAutostart))
        m.addItem(auto)
        m.addItem(.separator())

        // STOPKA: kolorowe logo firmowe, sygnatura i wysrodkowane Zamknij
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

        let quitIt = NSMenuItem(title: "", action: #selector(quit), keyEquivalent: "q")
        quitIt.target = self
        quitIt.attributedTitle = NSAttributedString(
            string: T("Quit coffee-paladin (protection stops)"),
            attributes: [.paragraphStyle: center, .font: NSFont.menuFont(ofSize: 13)])
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

    @objc func ntfyDialog() {
        let a = NSAlert()
        a.messageText = T("Phone push (ntfy.sh)...")
        a.informativeText = T("The topic name is the ONLY protection: anyone who knows or guesses it can read your alerts and send fake ones. Click Generate for a random unguessable name. On your phone install the ntfy.sh app (from ntfy.sh - mind the lookalike apps) and subscribe to the same topic. Leave empty to disable.")
        let box = NSView(frame: NSRect(x: 0, y: 0, width: 300, height: 26))
        let field = NSTextField(frame: NSRect(x: 0, y: 1, width: 196, height: 24))
        let current = GuardCfg.string("ntfy_topic", "")
        field.stringValue = current.isEmpty ? randomTopic() : current
        box.addSubview(field)
        let gen = NSButton(title: T("Generate"), target: self, action: #selector(ntfyGenerate))
        gen.bezelStyle = .rounded
        gen.controlSize = .small
        gen.frame = NSRect(x: 202, y: 0, width: 98, height: 26)
        box.addSubview(gen)
        ntfyField = field
        a.accessoryView = box
        a.addButton(withTitle: "OK")
        a.addButton(withTitle: "Cancel")
        let result = a.runModal()
        ntfyField = nil
        if result == .alertFirstButtonReturn {
            GuardCfg.set(["ntfy_topic": field.stringValue.trimmingCharacters(in: .whitespaces)])
        }
    }

    // --- nazwa we flocie

    @objc func fleetNameDialog() {
        let a = NSAlert()
        a.messageText = T("Name this Mac in the fleet...")
        a.informativeText = T("With five identical MacBooks the system hostname says nothing. This name shows in the fleet table and menu on every machine. Empty = system hostname.")
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 280, height: 24))
        field.stringValue = GuardCfg.string("fleet_label", "")
        field.placeholderString = T("e.g. render-01, studio-mini, mbp-14")
        a.accessoryView = field
        a.addButton(withTitle: "OK")
        a.addButton(withTitle: "Cancel")
        if a.runModal() == .alertFirstButtonReturn {
            GuardCfg.set(["fleet_label": field.stringValue.trimmingCharacters(in: .whitespaces)])
        }
    }

    // --- autostart

    @objc func toggleAutostart() { Autostart.set(!Autostart.enabled()) }

    /// Tryb "tylko obserwuj" bywa niezrozumialy, a to najwazniejsza opcja dla kogos, kto boi sie
    /// oddac narzedziu wladze nad swoimi procesami — wiec tlumaczymy go wprost.
    @objc func explainDry() {
        let a = NSAlert()
        a.messageText = T("Watch only (dry run)")
        a.informativeText = T("""
With this on, thermal-guard measures everything and writes to its log exactly what it WOULD do - "would pause Python (595% CPU)" - but sends no signal and never touches a single process.

Use it to see whether the thresholds suit your machine before you let the tool freeze real work. Open "Show the guard log" after a heavy job and you will know if it would have interfered too eagerly, or not soon enough.

Remember to switch it off afterwards: in this mode nothing protects the Mac.
""")
        a.alertStyle = .informational
        a.addButton(withTitle: "OK")
        a.runModal()
    }

    @objc func enableProtection() { GuardCfg.set(["dry_run": false]) }

    @objc func toggleNotify() { GuardCfg.set(["notify": !GuardCfg.bool("notify", true)]) }
    @objc func toggleDry() { GuardCfg.set(["dry_run": !GuardCfg.bool("dry_run", true)]) }

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
    @objc func resume() { send("resume") }

    @objc func reportPDF() { report(pdf: true) }
    @objc func reportTXT() { report(pdf: false) }

    func report(pdf: Bool) {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: reportBin)
        p.arguments = pdf ? ["--days", "14", "--pdf"] : ["--days", "14"]
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

    @objc func openLog() { NSWorkspace.shared.open(URL(fileURLWithPath: logPath)) }

    @objc func openIssues() {
        NSWorkspace.shared.open(URL(string: "https://github.com/pawelkwaczynski/coffee-paladin/issues")!)
    }

    @objc func buyCoffee() {
        NSWorkspace.shared.open(URL(string: "https://suppi.pl/panbookovsky")!)
    }

    @objc func mailAuthor() {
        NSWorkspace.shared.open(URL(string: "mailto:kwaczynski.pawel@gmail.com?subject=thermal-guard%20v\(VERSION)")!)
    }
    /// Wyjscie znaczy KONIEC PROGRAMU, nie tylko schowanie ikony: zatrzymujemy demona
    /// i pasek. Wczesniej "Zamknij pasek" zostawialo demona przy zyciu - to bylo mylace
    /// w druga strone (ludzie myśleli, ze wylaczyli ochronę, a ona dzialala).
    /// Teraz etykieta i skutek sa te same, a przed nieodwracalnym krokiem pytamy.
    @objc func quit() {
        let a = NSAlert()
        a.alertStyle = .critical
        a.messageText = T("Turn off thermal protection for this Mac?")
        a.informativeText = T("The daemon and the menu bar both stop. Nothing will pause hot jobs until you start it again.")
        a.addButton(withTitle: T("Quit anyway"))
        a.addButton(withTitle: T("Cancel"))
        NSApp.activate(ignoringOtherApps: true)
        guard a.runModal() == .alertFirstButtonReturn else { return }

        // Demon idzie pierwszy - gdyby pasek zginal wczesniej, uzytkownik zostalby
        // z dzialajaca ochrona i bez zadnego sposobu, zeby ja zobaczyc.
        let uid = String(getuid())
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        p.arguments = ["bootout", "gui/\(uid)/pl.pawel.thermal-guard"]
        try? p.run()
        p.waitUntilExit()

        let b = Process()
        b.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        b.arguments = ["bootout", "gui/\(uid)/pl.pawel.heatbar"]
        try? b.run()          // nie czekamy: to polecenie ubija nas samych
        NSApp.terminate(nil)
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)   // no Dock icon, no window
let bar = Bar()
app.run()
