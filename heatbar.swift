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

let VERSION = "1.6"
let SIGNATURE = "thermal-guard v\(VERSION)  ·  FOCUS FRAME 2026"

let base = NSString(string: "~/.thermal-guard").expandingTildeInPath
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
    "Load:  %.2f    CPU available: %d%%": "Obciążenie:  %.2f    CPU dostępne: %d%%",
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
    "Show in the bar": "Pokaż na pasku",
    "Export report for a repair shop": "Raport dla serwisu",
    "As PDF...": "Jako PDF...",
    "As plain text (TXT)...": "Jako tekst (TXT)...",
    "Show the guard log": "Pokaż dziennik zdarzeń",
    "Quit heatbar": "Zamknij heatbar",
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
    "A project of the AIrON student research club.": "Projekt w ramach koła naukowego.",
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
    "Load:  %.2f    CPU available: %d%%": "Нагрузка:  %.2f    CPU доступно: %d%%",
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
    "Show in the bar": "Показывать в строке меню",
    "Export report for a repair shop": "Отчёт для сервисного центра",
    "As PDF...": "В PDF...",
    "As plain text (TXT)...": "Текстом (TXT)...",
    "Show the guard log": "Показать журнал",
    "Quit heatbar": "Завершить heatbar",
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
    "A project of the AIrON student research club.": "Проект в рамках студенческого научного кружка AIrON.",
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
    "Load:  %.2f    CPU available: %d%%": "负载：  %.2f    CPU 可用：%d%%",
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
    "Show in the bar": "菜单栏显示内容",
    "Export report for a repair shop": "导出维修报告",
    "As PDF...": "PDF 格式...",
    "As plain text (TXT)...": "纯文本（TXT）...",
    "Show the guard log": "查看守护日志",
    "Quit heatbar": "退出 heatbar",
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
    "A project of the AIrON student research club.": "AIrON 学生科研社团的项目。",
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
    "Load:  %.2f    CPU available: %d%%": "Carga:  %.2f    CPU disponible: %d%%",
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
    "Show in the bar": "Mostrar en la barra",
    "Export report for a repair shop": "Informe para el servicio técnico",
    "As PDF...": "Como PDF...",
    "As plain text (TXT)...": "Como texto (TXT)...",
    "Show the guard log": "Ver el registro",
    "Quit heatbar": "Salir de heatbar",
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
    "A project of the AIrON student research club.": "Proyecto del club científico estudiantil AIrON.",
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
        super.init(frame: NSRect(x: 0, y: 0, width: 400, height: 56))
        let W: CGFloat = 400
        if let logo = customLogo() {
            // znak poziomy (wordmark): srodek, wysokosc 22, szerokosc wg proporcji
            let ratio = logo.size.width / max(logo.size.height, 1)
            let h: CGFloat = 24
            let w = min(h * ratio, 330)
            let iv = NSImageView(frame: NSRect(x: (W - w) / 2, y: 25, width: w, height: h))
            iv.image = logo
            iv.imageScaling = .scaleProportionallyUpOrDown
            iv.contentTintColor = .labelColor
            addSubview(iv)
        } else {
            let iv = NSImageView(frame: NSRect(x: (W - 22) / 2, y: 26, width: 22, height: 22))
            iv.image = makeLogo(22)
            addSubview(iv)
        }
        let name = NSTextField(labelWithString: T("A project of the AIrON student research club."))
        name.font = .systemFont(ofSize: 11)
        name.textColor = .secondaryLabelColor
        name.alignment = .center
        name.frame = NSRect(x: 0, y: 6, width: W, height: 14)
        addSubview(name)
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
            try? d.write(to: URL(fileURLWithPath: prefsPath))
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
            try? d.write(to: URL(fileURLWithPath: configPath))
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
            try? d.write(to: URL(fileURLWithPath: awakePath))
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
        // brak wpisu = wlaczone; "service" => disabled/true = wylaczone
        for line in out.split(separator: "\n") where line.contains(services[0]) {
            if line.contains("disabled") || line.contains("true") { return false }
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
    s.chip = j["chip_c"] as? Double
    s.gpu = j["gpu_c"] as? Double
    s.batt = j["battery_c"] as? Double
    s.watts = j["watts"] as? Double
    s.fans = (j["fans"] as? [Int]) ?? []
    s.ramUsed = j["ram_used_gb"] as? Double
    s.ramTotal = j["ram_total_gb"] as? Double
    s.swap = j["swap_used_gb"] as? Double
    s.diskUsed = j["disk_used_gb"] as? Int
    s.diskTotal = j["disk_total_gb"] as? Int
    s.diskPct = j["disk_used_pct"] as? Int
    s.pct = j["battery_pct"] as? Int
    s.onAC = (j["on_ac"] as? Bool) ?? true
    s.level = (j["level"] as? Int) ?? 0
    s.load = (j["load1"] as? Double) ?? 0
    s.cpuLimit = (j["cpu_limit"] as? Int) ?? 100
    s.reason = (j["reason"] as? String) ?? ""
    s.topProc = j["top_proc"] as? String
    s.topCPU = j["top_cpu"] as? Int
    s.paused = (j["paused"] as? [String]) ?? []
    s.manualPause = (j["manual_pause"] as? Bool) ?? false
    s.dryRun = (j["dry_run"] as? Bool) ?? false
    s.keepAwake = (j["keep_awake"] as? Bool) ?? false
    s.trend = j["trend_c_min"] as? Double
    s.eta = j["eta_pause_min"] as? Double
    s.stamp = (j["time"] as? String) ?? ""
    if let z = j["jobs"] as? [[String: Any]] {
        s.jobs = z.map { Job(name: ($0["name"] as? String) ?? "?", minutes: ($0["minutes"] as? Int) ?? 0) }
    }
    if let z = j["top_cpu_list"] as? [[String: Any]] {
        s.topCpuList = z.map { TopCPU(name: ($0["name"] as? String) ?? "?",
                                      cpu: ($0["cpu"] as? Int) ?? Int(($0["cpu"] as? Double) ?? 0)) }
    }
    if let z = j["top_ram_list"] as? [[String: Any]] {
        s.topRamList = z.map { TopRAM(name: ($0["name"] as? String) ?? "?",
                                      gb: ($0["gb"] as? Double) ?? Double(($0["gb"] as? Int) ?? 0)) }
    }
    if let st = j["stats"] as? [String: Any] {
        s.pausesToday = (st["pauses"] as? Int) ?? 0
        s.killsToday = (st["kills"] as? Int) ?? 0
    }
    if let p = j["last_hard_shutdown"] as? [String: Any] { s.lastCrash = p["time"] as? String }
    if let t = j["thresholds"] as? [String: Any] {
        s.thrPause = t["pause"] as? Double
        s.thrKill = t["kill"] as? Double
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
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    let menu = NSMenu()
    var timer: Timer?

    override init() {
        super.init()
        // macOS domyslnie wygasza pozycje menu bez akcji — a u nas wiekszosc wierszy to
        // informacje, nie polecenia. Bez tej flagi caly odczyt byl szary i nieczytelny.
        menu.autoenablesItems = false
        menu.delegate = self
        item.menu = menu
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.refresh() }
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
        row(String(format: T("Load:  %.2f    CPU available: %d%%"), s.load, s.cpuLimit))
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

        let dry = NSMenuItem(title: T("Watch only, never touch processes (dry run)"),
                             action: #selector(toggleDry), keyEquivalent: "")
        dry.target = self
        dry.state = GuardCfg.bool("dry_run", false) ? .on : .off
        ss.addItem(dry)

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
                let warn = (hw["battery_failure"] as? Bool) == true ? "  ⚠️" : ""
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

        m.addItem(.separator())
        m.addItem(withTitle: T("Report a problem (GitHub)..."), action: #selector(openIssues), keyEquivalent: "").target = self
        m.addItem(withTitle: T("Write to the author..."), action: #selector(mailAuthor), keyEquivalent: "").target = self

        // autostart przy logowaniu — default ON (tak instaluje install.sh)
        let auto = m.addItem(withTitle: T("Start at login"), action: #selector(toggleAutostart), keyEquivalent: "")
        auto.target = self
        auto.image = img("power")
        auto.state = Autostart.enabled() ? .on : .off
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
            string: T("Quit heatbar"),
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
    @objc func toggleDry() { GuardCfg.set(["dry_run": !GuardCfg.bool("dry_run", false)]) }

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
        NSWorkspace.shared.open(URL(string: "https://github.com/pawelkwaczynski/thermal-guard/issues")!)
    }

    @objc func mailAuthor() {
        NSWorkspace.shared.open(URL(string: "mailto:kwaczynski.pawel@gmail.com?subject=thermal-guard%20v\(VERSION)")!)
    }
    @objc func quit() { NSApp.terminate(nil) }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)   // no Dock icon, no window
let bar = Bar()
app.run()
