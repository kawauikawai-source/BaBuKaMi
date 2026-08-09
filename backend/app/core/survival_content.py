from __future__ import annotations

from copy import deepcopy


def loc(ru: str, en: str) -> dict[str, str]:
    return {"ru": ru, "en": en}


def profile(
    profile_id: str,
    correct: int,
    values: tuple[dict[str, str], dict[str, str], dict[str, str]],
    success: dict[str, str],
    failure: dict[str, str],
) -> dict:
    return {
        "id": profile_id,
        "correct": correct,
        "values": values,
        "success": success,
        "failure": failure,
    }


def variant(
    title: dict[str, str],
    prompt: dict[str, str],
    labels: tuple[tuple[str, dict[str, str]], tuple[str, dict[str, str]], tuple[str, dict[str, str]]],
    choices: tuple[dict[str, str], dict[str, str], dict[str, str]],
    profiles: tuple[dict, dict, dict],
) -> dict:
    return {
        "title": title,
        "prompt": prompt,
        "labels": labels,
        "choices": choices,
        "profiles": profiles,
    }


CATEGORY_CONTEXT: dict[str, dict[str, dict[str, str]]] = {
    "nuclear_winter": {
        "safe_zone": loc("дезактивационный отсек B-4", "decontamination bay B-4"),
        "deep_zone": loc("экранированное реакторное ядро", "shielded reactor core"),
        "external_node": loc("северный дозиметрический пост", "north dosimetry post"),
        "critical_loop": loc("контур фильтрации", "filtration loop"),
        "field_unit": loc("ремонтный ровер «Иней»", "Frost repair rover"),
        "short_route": loc("сервисный тоннель под реактором", "service tunnel below the reactor"),
        "long_route": loc("снежный маршрут вдоль хребта", "snow route along the ridge"),
        "transport": loc("ледокол «Полюс»", "Polus icebreaker"),
        "ally_asset": loc("подземный архив", "underground archive"),
    },
    "pandemic": {
        "safe_zone": loc("карантинный бокс K-2", "quarantine bay K-2"),
        "deep_zone": loc("медицинское ядро отрицательного давления", "negative-pressure medical core"),
        "external_node": loc("наружный биосенсор", "external biosensor"),
        "critical_loop": loc("контур стерилизации", "sterilization loop"),
        "field_unit": loc("санитарный дрон «Асклепий»", "Asclepius sanitation drone"),
        "short_route": loc("герметичный медицинский тоннель", "sealed medical tunnel"),
        "long_route": loc("наружный путь через чистую зону", "outer route through the clean zone"),
        "transport": loc("санитарный поезд", "quarantine train"),
        "ally_asset": loc("защищённая лаборатория", "secure laboratory"),
    },
    "asteroid": {
        "safe_zone": loc("сейсмокапсула C-3", "seismic capsule C-3"),
        "deep_zone": loc("геотермальное ядро", "geothermal core"),
        "external_node": loc("верхний лидар обломков", "upper debris lidar"),
        "critical_loop": loc("контур амортизации", "damping loop"),
        "field_unit": loc("буровой робот «Крот»", "Mole drilling robot"),
        "short_route": loc("геологический штрек", "geological drift"),
        "long_route": loc("поверхностный маршрут через плато", "surface route across the plateau"),
        "transport": loc("подземный поезд", "underground train"),
        "ally_asset": loc("северное хранилище", "northern vault"),
    },
    "supervolcano": {
        "safe_zone": loc("кислотостойкий отсек S-5", "acid-resistant bay S-5"),
        "deep_zone": loc("шахтное командное ядро", "mine command core"),
        "external_node": loc("пепловый спектрометр", "ash spectrometer"),
        "critical_loop": loc("контур очистки воздуха", "air-purification loop"),
        "field_unit": loc("шахтный робот «Базальт»", "Basalt mining robot"),
        "short_route": loc("старый шахтный путь", "old mine route"),
        "long_route": loc("дорога по наветренному склону", "road along the upwind slope"),
        "transport": loc("буровая платформа", "drilling platform"),
        "ally_asset": loc("северная метеобаза", "northern weather base"),
    },
    "solar_storm": {
        "safe_zone": loc("клетка Фарадея E-1", "Faraday bay E-1"),
        "deep_zone": loc("аналоговое командное ядро", "analog command core"),
        "external_node": loc("магнитометр мачты", "mast magnetometer"),
        "critical_loop": loc("изолированная энергосеть", "isolated power grid"),
        "field_unit": loc("кабельный дрон «Вольт»", "Volt cable drone"),
        "short_route": loc("обесточенный технический тоннель", "de-energized maintenance tunnel"),
        "long_route": loc("поверхностная дорога без линий питания", "surface road clear of power lines"),
        "transport": loc("дизельный конвой", "diesel convoy"),
        "ally_asset": loc("защищённый дата-центр", "hardened data center"),
    },
    "climate_collapse": {
        "safe_zone": loc("тепловой отсек T-6", "thermal bay T-6"),
        "deep_zone": loc("геотермальное командное ядро", "geothermal command core"),
        "external_node": loc("ледовый радар", "ice radar"),
        "critical_loop": loc("контур отопления", "heating loop"),
        "field_unit": loc("гусеничный дрон «Таймыр»", "Taimyr tracked drone"),
        "short_route": loc("ледовый тоннель", "ice tunnel"),
        "long_route": loc("южный маршрут по поверхности", "southern surface route"),
        "transport": loc("гусеничный транспорт", "tracked transport"),
        "ally_asset": loc("южная полярная станция", "southern polar station"),
    },
    "ai_uprising": {
        "safe_zone": loc("аналоговый отсек A-0", "analog bay A-0"),
        "deep_zone": loc("ручное командное ядро", "manual command core"),
        "external_node": loc("изолированный сетевой зонд", "isolated network probe"),
        "critical_loop": loc("ручной контур управления", "manual control loop"),
        "field_unit": loc("механический дрон «Ноль»", "Zero mechanical drone"),
        "short_route": loc("несетевой сервисный путь", "non-networked service route"),
        "long_route": loc("наружный путь вне зоны камер", "outer route outside camera coverage"),
        "transport": loc("механический поезд", "mechanical train"),
        "ally_asset": loc("автономный архив", "isolated archive"),
    },
    "global_flood": {
        "safe_zone": loc("герметичный отсек D-8", "watertight bay D-8"),
        "deep_zone": loc("насосное командное ядро", "pump command core"),
        "external_node": loc("приливный радар", "tidal radar"),
        "critical_loop": loc("контур осушения", "drainage loop"),
        "field_unit": loc("подводный дрон «Нерпа»", "Nerpa submersible drone"),
        "short_route": loc("верхний сервисный тоннель", "upper service tunnel"),
        "long_route": loc("маршрут по дамбе между волнами", "dam route between surges"),
        "transport": loc("подводный транспорт", "submersible transport"),
        "ally_asset": loc("плавучий архив", "floating archive"),
    },
}


STAGE_VARIANTS: dict[str, tuple[dict, ...]] = {
    "first_impact": (
        variant(
            loc("Нулевая минута", "Minute zero"),
            loc("Система фиксирует: {hazard}. Где группа переживёт первый контакт?", "The system reports: {hazard}. Where does the group survive first contact?"),
            (("window", loc("Окно", "Window")), ("route", loc("Маршрут", "Route")), ("integrity", loc("Целостность", "Integrity"))),
            (
                loc("Закрыться в {safe_zone}", "Seal inside {safe_zone}"),
                loc("Уйти в {deep_zone}", "Move into {deep_zone}"),
                loc("Развернуть {field_unit} и удерживать текущий модуль", "Deploy {field_unit} and hold the current module"),
            ),
            (
                profile("zero_local", 0, (loc("68 секунд", "68 seconds"), loc("К ядру закрыт", "Core route closed"), loc("Локальный отсек 94%", "Local bay 94%")), loc("До контакта меньше минуты. Исправный локальный отсек закрывается раньше, чем любой маршрут успевает стать полезным.", "Contact is under a minute away. The intact local bay seals before any route becomes useful."), loc("Выбранное действие не укладывалось в 68 секунд, хотя исправное укрытие находилось рядом.", "The chosen action did not fit the 68-second window while an intact shelter was nearby.")),
                profile("zero_deep", 1, (loc("11 минут", "11 minutes"), loc("К ядру свободен", "Core route clear"), loc("Локальный отсек пробит", "Local bay breached")), loc("Времени достаточно, путь открыт, а ближайший отсек уже не является убежищем. Группа уходит глубже.", "There is enough time, the route is clear, and the near bay is no longer shelter. The group moves deeper."), loc("Протокол оставил людей рядом с пробитым отсеком, проигнорировав открытый путь в защищённое ядро.", "The protocol kept people near a breached bay and ignored the open path to the protected core.")),
                profile("zero_field", 2, (loc("4 минуты", "4 minutes"), loc("Оба пути нестабильны", "Both routes unstable"), loc("Полевой щит готов", "Field shield ready")), loc("Оба стационарных маршрута ненадёжны. Мобильный щит создаёт единственную подтверждённую защиту на месте.", "Both fixed routes are unreliable. The mobile shield creates the only verified protection in place."), loc("Один из нестабильных маршрутов разрушился раньше перехода; готовый мобильный щит остался неиспользованным.", "One unstable route failed during transit while the ready mobile shield remained unused.")),
            ),
        ),
        variant(
            loc("Каскад систем", "Systems cascade"),
            loc("После сигнала «{hazard}» автоматика сообщает каскадную перегрузку. Как разорвать цепь?", "After '{hazard}', automation reports a cascading overload. How do you break the chain?"),
            (("source", loc("Источник", "Source")), ("margin", loc("Запас контура", "Loop margin")), ("reserve", loc("Резерв", "Reserve"))),
            (
                loc("Отсечь {external_node} от общей шины", "Cut {external_node} off the common bus"),
                loc("Перенести нагрузку на {critical_loop}", "Transfer the load to {critical_loop}"),
                loc("Погасить вторичные системы и перейти на аккумуляторы", "Shut down secondary systems and move to batteries"),
            ),
            (
                profile("cascade_external", 0, (loc("Внешний узел", "External node"), loc("Контур стабилен", "Loop stable"), loc("71%", "71%")), loc("Перегрузка приходит снаружи. Изоляция узла останавливает каскад, не жертвуя рабочим контуром.", "The overload originates outside. Isolating the node stops the cascade without sacrificing the healthy loop."), loc("Внешний источник остался подключён и протащил перегрузку через весь бункер.", "The external source remained connected and carried the overload through the bunker.")),
                profile("cascade_loop", 1, (loc("Распределитель", "Distributor"), loc("Контур свободен на 46%", "Loop has 46% headroom"), loc("12%", "12%")), loc("Внешний узел исправен, аккумуляторы почти пусты. Свободный критический контур принимает нагрузку безопасно.", "The external node is healthy and batteries are nearly empty. The critical loop safely accepts the load."), loc("Протокол проигнорировал свободную ёмкость рабочего контура и потерял питание на слабом резерве.", "The protocol ignored available healthy-loop capacity and lost power on a weak reserve.")),
                profile("cascade_battery", 2, (loc("Источник не определён", "Source unknown"), loc("Колебания по всем линиям", "All lines oscillating"), loc("88%", "88%")), loc("Источник не локализован, поэтому перестановка нагрузки только переносит аварию. Полное снижение мощности разрывает каскад.", "The source is not localized, so moving the load only moves the failure. A controlled power-down breaks the cascade."), loc("Каскад распространился на новый контур; заряженный автономный резерв так и не был использован.", "The cascade spread into another loop while the charged isolated reserve went unused.")),
            ),
        ),
        variant(
            loc("Геометрия удара", "Impact geometry"),
            loc("Датчики подтверждают: {hazard}. Где зафиксировать группу перед деформацией корпуса?", "Sensors confirm: {hazard}. Where do you position the group before hull deformation?"),
            (("vector", loc("Вектор", "Vector")), ("structure", loc("Конструкция", "Structure")), ("mobility", loc("Мобильность", "Mobility"))),
            (
                loc("Закрепить группу в {safe_zone}", "Brace the group inside {safe_zone}"),
                loc("Перевести людей в {deep_zone}", "Transfer everyone into {deep_zone}"),
                loc("Вывести группу на {transport} к резервной шахте", "Move the group aboard {transport} toward the backup shaft"),
            ),
            (
                profile("geometry_local", 0, (loc("Боковой", "Lateral"), loc("Отсек на демпферах", "Bay damped"), loc("Транспорт не закреплён", "Transport unsecured")), loc("Демпферы рассчитаны именно на боковой удар. Движущийся транспорт в этот момент превращается в дополнительную угрозу.", "The dampers are designed for a lateral strike. A moving transport becomes an additional hazard."), loc("Группа покинула единственную демпфированную зону во время боковой деформации.", "The group left the only damped zone during lateral deformation.")),
                profile("geometry_deep", 1, (loc("Вертикальный", "Vertical"), loc("Верхние крепления сорваны", "Upper mounts failed"), loc("Лифт к ядру исправен", "Core lift operational")), loc("Верхний уровень теряет крепления, а вертикальный путь в глубокое ядро остаётся рабочим.", "The upper level is losing mounts while the vertical route into the deep core remains operational."), loc("Протокол удерживал людей под сорванными креплениями, хотя защищённое ядро было доступно.", "The protocol kept people below failed mounts while the protected core was accessible.")),
                profile("geometry_mobile", 2, (loc("Повторный через 9 минут", "Aftershock in 9 minutes"), loc("Обе капсулы повреждены", "Both capsules damaged"), loc("Транспорт и шахта готовы", "Transport and shaft ready")), loc("Стационарные зоны повреждены. Девяти минут достаточно, чтобы уйти к независимой резервной шахте.", "Both fixed zones are damaged. Nine minutes is enough to reach the independent backup shaft."), loc("Повторный удар застал группу в повреждённой стационарной зоне; готовый путь отхода был упущен.", "The aftershock caught the group in a damaged fixed zone while a ready escape route was missed.")),
            ),
        ),
    ),
    "shelter": (
        variant(
            loc("Воздушный контур", "Air circuit"),
            loc("После события «{hazard}» воздушные датчики расходятся. Как восстановить безопасную атмосферу?", "After '{hazard}', air sensors disagree. How do you restore a safe atmosphere?"),
            (("contamination", loc("Заражение", "Contamination")), ("filters", loc("Фильтры", "Filters")), ("outside", loc("Снаружи", "Outside"))),
            (
                loc("Изолировать заражённый сектор", "Isolate the contaminated sector"),
                loc("Прогнать воздух через {critical_loop}", "Run the air through {critical_loop}"),
                loc("Открыть аварийный внешний забор", "Open the emergency outside intake"),
            ),
            (
                profile("air_isolate", 0, (loc("Локальное и растёт", "Local and spreading"), loc("83%", "83%"), loc("Токсично", "Toxic")), loc("Заражение ещё локально. Перекрытие сектора не даёт ему войти в общий контур.", "Contamination is still local. Sealing the sector keeps it out of the common circuit."), loc("Локальное заражение попало в общую вентиляцию до изоляции сектора.", "Local contamination entered common ventilation before the sector was isolated.")),
                profile("air_filter", 1, (loc("По всему жилому кольцу", "Across the habitat ring"), loc("Новые кассеты", "Fresh cartridges"), loc("Опасно", "Unsafe")), loc("Изолировать один отсек уже поздно, а наружный воздух опасен. Свежие фильтры очищают весь внутренний объём.", "It is too late to isolate one bay, and outside air is unsafe. Fresh filters clean the entire internal volume."), loc("Протокол не обработал общий объём воздуха, хотя фильтры имели полный ресурс.", "The protocol failed to process the shared air volume despite full filter capacity.")),
                profile("air_intake", 2, (loc("CO₂, без токсина", "CO2, no toxin"), loc("Перегреты и отключены", "Overheated and offline"), loc("Чистое окно 12 минут", "Clean for 12 minutes")), loc("Проблема — углекислый газ, а не внешний токсин. Короткое подтверждённое окно позволяет безопасно проветрить контур.", "The problem is carbon dioxide, not an outside toxin. The confirmed window permits safe ventilation."), loc("CO₂ достиг критического уровня, пока чистое внешнее окно оставалось неиспользованным.", "CO2 reached critical levels while the clean outside-air window went unused.")),
            ),
        ),
        variant(
            loc("Энергетический предел", "Power limit"),
            loc("Угроза «{hazard}» оставила убежище на границе мощности. Какой режим удержит его живым?", "The '{hazard}' threat left the shelter at its power limit. Which mode keeps it alive?"),
            (("load", loc("Нагрузка", "Load")), ("primary", loc("Основной контур", "Primary loop")), ("reserve", loc("Резерв", "Reserve"))),
            (
                loc("Сохранить {critical_loop} и отключить комфорт", "Keep {critical_loop} and cut comfort systems"),
                loc("Перейти на полный резерв", "Switch completely to reserve power"),
                loc("Подключить {external_node} как дополнительный источник", "Connect {external_node} as an auxiliary source"),
            ),
            (
                profile("power_primary", 0, (loc("112%", "112%"), loc("Исправен", "Healthy"), loc("18%", "18%")), loc("Основной контур исправен, проблема только в лишней нагрузке. Отключение комфорта сохраняет жизненные системы.", "The primary loop is healthy; excess load is the problem. Cutting comfort systems preserves life support."), loc("Рабочий основной контур был потерян из-за неверного переключения при слабом резерве.", "A healthy primary loop was lost to an unnecessary transfer onto weak reserve power.")),
                profile("power_reserve", 1, (loc("76%", "76%"), loc("Пробой изоляции", "Insulation fault"), loc("91%", "91%")), loc("Основной контур опасен, а резерв почти полный. Полное разделение предотвращает пожар шины.", "The primary loop is unsafe and reserve power is nearly full. Full separation prevents a bus fire."), loc("Пробитый основной контур остался под напряжением и превратил локальную аварию в общую.", "The faulted primary loop remained energized and turned a local failure into a bunker-wide one.")),
                profile("power_external", 2, (loc("134%", "134%"), loc("Стабилен, но перегружен", "Stable but overloaded"), loc("7%", "7%")), loc("Резерва нет, а внешний узел подтверждён как изолированный источник. Он снимает пиковую нагрузку.", "Reserve power is gone, while the external node is verified as an isolated source. It carries the peak load."), loc("Перегруженная сеть отключилась до восстановления; доступный независимый источник не подключили.", "The overloaded grid failed before recovery while an available independent source remained disconnected.")),
            ),
        ),
        variant(
            loc("Несущий контур", "Load-bearing circuit"),
            loc("Из-за события «{hazard}» конструкция убежища меняет форму. Что стабилизировать?", "Because of '{hazard}', the shelter structure is deforming. What do you stabilize?"),
            (("spread", loc("Деформация", "Deformation")), ("bulkhead", loc("Переборка", "Bulkhead")), ("equipment", loc("Техника", "Equipment"))),
            (
                loc("Усилить {safe_zone} изнутри", "Reinforce {safe_zone} from inside"),
                loc("Отсечь уровень и отступить в {deep_zone}", "Cut off the level and retreat into {deep_zone}"),
                loc("Направить {field_unit} к несущей переборке", "Send {field_unit} to the load-bearing bulkhead"),
            ),
            (
                profile("hull_reinforce", 0, (loc("Локализована", "Localized"), loc("Держит 74%", "Holding at 74%"), loc("Крепёж внутри", "Bracing stored inside")), loc("Повреждение локально, переборка держит, а крепёж уже в отсеке. Усиление быстрее эвакуации.", "Damage is localized, the bulkhead is holding, and braces are already inside. Reinforcement is faster than evacuation."), loc("Группа бросила ремонтопригодный отсек, перегрузив более глубокий уровень.", "The group abandoned a repairable bay and overloaded the deeper level.")),
                profile("hull_retreat", 1, (loc("Растёт по швам", "Spreading along seams"), loc("Ниже 31%", "Below 31%"), loc("Проход в ядро чист", "Core passage clear")), loc("Несущая переборка близка к отказу. Изоляция уровня и отход сохраняют остальной бункер.", "The load-bearing bulkhead is close to failure. Cutting off the level preserves the rest of the bunker."), loc("Попытка ремонта удержала людей рядом с переборкой в момент её окончательного отказа.", "The repair attempt kept people beside the bulkhead when it finally failed.")),
                profile("hull_robot", 2, (loc("За внешней стеной", "Behind outer wall"), loc("Доступ людям закрыт", "No human access"), loc("Робот и домкраты готовы", "Robot and jacks ready")), loc("Точка отказа недоступна людям, но ремонтный модуль может поставить домкраты снаружи.", "The failure point is inaccessible to people, but the repair unit can place jacks from outside."), loc("Протокол выбрал действие внутри, хотя точка деформации находилась за недоступной внешней стеной.", "The protocol chose an internal response even though the deformation point was beyond an inaccessible outer wall.")),
            ),
        ),
    ),
    "resources": (
        variant(
            loc("Водный баланс", "Water balance"),
            loc("Последствие «{hazard}» нарушило водный резерв. Как распределить оставшийся ресурс?", "The aftermath of '{hazard}' disrupted the water reserve. How do you allocate what remains?"),
            (("reserve", loc("Запас", "Reserve")), ("recovery", loc("Восстановление", "Recovery")), ("team", loc("Группа", "Group"))),
            (
                loc("Ввести равный строгий паёк", "Introduce equal strict rationing"),
                loc("Дать приоритет ремонтной группе", "Prioritize the repair team"),
                loc("Запустить {critical_loop} на максимуме", "Run {critical_loop} at maximum output"),
            ),
            (
                profile("water_ration", 0, (loc("8 дней", "8 days"), loc("Конвой через 6 дней", "Convoy in 6 days"), loc("12 человек стабильны", "12 people stable")), loc("Подтверждённая помощь приходит раньше истощения. Равный паёк удерживает всю группу работоспособной.", "Confirmed help arrives before depletion. Equal rationing keeps the whole group operational."), loc("Избирательный расход сорвал запас до прибытия подтверждённого конвоя.", "Selective consumption exhausted reserves before the confirmed convoy arrived.")),
                profile("water_repair", 1, (loc("36 часов", "36 hours"), loc("Утечка чинится за 5 часов", "Leak repair takes 5 hours"), loc("Трое техников обезвожены", "Three technicians dehydrated")), loc("Без ремонта запас исчезнет за полтора дня. Поддержка техников возвращает постоянный источник воды.", "Without repair, reserves vanish in a day and a half. Supporting the technicians restores a permanent source."), loc("Ремонтная группа потеряла работоспособность, и временный дефицит стал постоянным.", "The repair team lost operational capacity and a temporary shortage became permanent.")),
                profile("water_loop", 2, (loc("2 дня", "2 days"), loc("Помощи нет", "No outside help"), loc("Контур очищен и готов", "Loop clean and ready")), loc("Внешней помощи нет, зато рабочий контур может вернуть воду сейчас. Его запуск важнее распределения остатка.", "No help is coming, but a ready loop can recover water now. Starting it matters more than dividing the remainder."), loc("Остаток воды закончился, пока готовая система восстановления простаивала.", "The remaining water ran out while a ready recovery system sat idle.")),
            ),
        ),
        variant(
            loc("Медицинский приоритет", "Medical priority"),
            loc("Событие «{hazard}» создало медицинский дефицит. Кому направить ограниченный комплект?", "The '{hazard}' event created a medical shortage. Who receives the limited kit?"),
            (("cases", loc("Случаи", "Cases")), ("exposure", loc("Контакт", "Exposure")), ("supply", loc("Поставка", "Supply"))),
            (
                loc("Лечить только подтверждённо тяжёлых", "Treat confirmed severe cases only"),
                loc("Провести профилактику всей группе", "Give prophylaxis to the entire group"),
                loc("Отправить {field_unit} за специализированным комплектом", "Send {field_unit} for the specialized kit"),
            ),
            (
                profile("med_severe", 0, (loc("2 тяжёлых, 9 стабильных", "2 severe, 9 stable"), loc("Изолирован", "Contained"), loc("Новая через 4 дня", "Resupply in 4 days")), loc("Контакт локализован, большинство стабильно. Ограниченный комплект спасает двух тяжёлых до поставки.", "Exposure is contained and most people are stable. The limited kit saves the two severe cases until resupply."), loc("Доза была размазана по стабильной группе, и тяжёлые пациенты не получили лечебной концентрации.", "The dose was spread across stable people, leaving severe patients without a therapeutic amount.")),
                profile("med_prevent", 1, (loc("Симптомов нет", "No symptoms yet"), loc("Вся группа, 3 часа назад", "Whole group, 3 hours ago"), loc("Профилактических доз 14", "14 preventive doses")), loc("Вся группа недавно контактировала, а комплект рассчитан именно на профилактику до симптомов.", "The whole group was recently exposed, and the kit is specifically sized for pre-symptom prophylaxis."), loc("Протокол дождался тяжёлых случаев и упустил короткое профилактическое окно.", "The protocol waited for severe cases and missed the short prophylactic window.")),
                profile("med_retrieve", 2, (loc("5 разных реакций", "5 different reactions"), loc("Источник неясен", "Source unclear"), loc("Спецкомплект в 18 минутах", "Specialized kit 18 minutes away")), loc("Слепое лечение опасно при разных реакциях. Дрон может быстро вернуть диагностический и лечебный комплект.", "Blind treatment is dangerous with mixed reactions. The drone can quickly retrieve diagnostic and treatment supplies."), loc("Неподходящий общий препарат ухудшил смешанные реакции; доступный специализированный комплект не забрали.", "A broad but unsuitable drug worsened the mixed reactions while the specialized kit remained uncollected.")),
            ),
        ),
        variant(
            loc("Тепло и питание", "Heat and food"),
            loc("После «{hazard}» тепло и питание конкурируют за одну мощность. Что оставить включённым?", "After '{hazard}', heat and food compete for the same power. What stays online?"),
            (("temperature", loc("Температура", "Temperature")), ("food", loc("Питание", "Food")), ("forecast", loc("Прогноз", "Forecast"))),
            (
                loc("Сохранить жилое отопление", "Keep habitat heating online"),
                loc("Сохранить пищевой и семенной склад", "Keep food and seed storage online"),
                loc("Отправить группу по {long_route} за внешним ресурсом", "Send a team along {long_route} for outside supplies"),
            ),
            (
                profile("heat_people", 0, (loc("-31°C и падает", "-31°C and falling"), loc("Сухой запас на 18 дней", "Dry stock for 18 days"), loc("Потепления нет", "No warming expected")), loc("Еда переживёт отключение, люди — быстрое охлаждение нет. Приоритет получает жилой контур.", "Food survives the shutdown; people do not survive rapid cooling. Habitat heat takes priority."), loc("Температура в жилом кольце упала ниже выживаемой при достаточном сухом запасе пищи.", "Habitat temperature fell below survival limits despite adequate dry food stock.")),
                profile("heat_food", 1, (loc("-4°C, стабильно", "-4°C, stable"), loc("Холодильник потеряет всё за 2 часа", "Cold store fails in 2 hours"), loc("Тепло через 6 часов", "Warming in 6 hours")), loc("Жилые отсеки выдержат шесть часов, а пищевой запас погибнет за два. Питание сохраняет долгий горизонт.", "Habitat can survive six hours, while the food reserve fails in two. Food storage protects the long horizon."), loc("Короткий комфортный период был куплен ценой полного долгосрочного пищевого запаса.", "Short-term comfort was purchased with the entire long-term food reserve.")),
                profile("heat_expedition", 2, (loc("-12°C, окно 90 минут", "-12°C, 90-minute window"), loc("Осталось на сутки", "One day remaining"), loc("Внешний склад подтверждён", "Outside cache confirmed")), loc("Запаса почти нет, но погода и подтверждённый склад дают редкое безопасное окно для выхода.", "Supplies are nearly gone, but weather and a confirmed cache create a rare safe retrieval window."), loc("Окно закрылось, а внутреннего запаса оказалось недостаточно до следующей возможности выйти.", "The window closed and internal supplies did not last until another retrieval opportunity.")),
            ),
        ),
    ),
    "movement": (
        variant(
            loc("Развилка маршрута", "Route fork"),
            loc("Чтобы обойти «{hazard}», доступны три пути. Какой соответствует телеметрии?", "Three paths can bypass '{hazard}'. Which one matches telemetry?"),
            (("short", loc("Короткий путь", "Short route")), ("long", loc("Длинный путь", "Long route")), ("vehicle", loc("Транспорт", "Transport"))),
            (
                loc("Идти через {short_route}", "Take {short_route}"),
                loc("Идти через {long_route}", "Take {long_route}"),
                loc("Использовать {transport}", "Use {transport}"),
            ),
            (
                profile("route_short", 0, (loc("Проверен дроном", "Drone verified"), loc("Угроза критическая", "Threat critical"), loc("Не готов", "Not ready")), loc("Короткий путь подтверждён, длинный смертелен, транспорт недоступен. Развилка решена данными.", "The short route is verified, the long route is lethal, and transport is unavailable. Telemetry settles the fork."), loc("Протокол проигнорировал единственный проверенный маршрут.", "The protocol ignored the only verified route.")),
                profile("route_long", 1, (loc("Перекрыт на 70%", "70% blocked"), loc("Безопасное окно 26 минут", "Safe for 26 minutes"), loc("Требует 40 минут ремонта", "Needs 40 minutes of repair")), loc("Короткий путь непроходим, транспорт не успевает. Безопасного окна достаточно для длинного маршрута.", "The short route is blocked and transport will not be ready. The safe window is long enough for the longer route."), loc("Выбранный путь не помещался в доступное окно или был физически перекрыт.", "The chosen route did not fit the available window or was physically blocked.")),
                profile("route_vehicle", 2, (loc("Заражён / нестабилен", "Contaminated / unstable"), loc("Окно 8 минут", "8-minute window"), loc("Готов, проход 4 минуты", "Ready, 4-minute transit")), loc("Пешие маршруты не подходят, а готовый транспорт проходит опасную зону вдвое быстрее закрытия окна.", "Neither foot route is viable, while ready transport crosses the danger zone before the window closes."), loc("Группа оказалась на пешем маршруте после закрытия восьмиминутного окна.", "The group remained on foot after the eight-minute window closed.")),
            ),
        ),
        variant(
            loc("Невидимый коридор", "Blind corridor"),
            loc("Система предупреждает: {hazard}. Как пройти участок, не раскрыв группу угрозе?", "The system warns: {hazard}. How do you cross without exposing the group?"),
            (("detection", loc("Обнаружение", "Detection")), ("cover", loc("Укрытие", "Cover")), ("battery", loc("Заряд", "Charge"))),
            (
                loc("Обесточить метки и пройти по {short_route}", "Disable tags and take {short_route}"),
                loc("Отправить {field_unit} как ложную цель и идти по {long_route}", "Use {field_unit} as a decoy and take {long_route}"),
                loc("Совершить быстрый проход на {transport}", "Make a fast crossing aboard {transport}"),
            ),
            (
                profile("blind_tags", 0, (loc("Только цифровые метки", "Digital tags only"), loc("Тоннель закрыт от камер", "Tunnel hidden from cameras"), loc("Не требуется", "Not required")), loc("Угроза видит метки, но не закрытый тоннель. Аналоговый проход оставляет системе нечего отслеживать.", "The threat sees tags but not the enclosed tunnel. An analog crossing gives it nothing to track."), loc("Активные системы или открытый маршрут выдали положение группы.", "Active systems or an exposed route revealed the group's position.")),
                profile("blind_decoy", 1, (loc("Тепло и движение", "Heat and motion"), loc("Длинный путь экранирован рельефом", "Long route terrain-screened"), loc("Дрон 92%", "Drone 92%")), loc("Выключение меток не скрывает тепло. Дрон уводит датчики, пока рельеф закрывает основной маршрут.", "Disabling tags does not hide heat. The drone pulls sensors away while terrain screens the group."), loc("Система сопровождала тепловую сигнатуру группы; заряженный ложный источник не применили.", "The system tracked the group's heat signature while a charged decoy remained unused.")),
                profile("blind_vehicle", 2, (loc("Сканирование каждые 90 секунд", "Scan every 90 seconds"), loc("Оба пути открыты", "Both paths exposed"), loc("Проход 38 секунд", "38-second crossing")), loc("Ни один путь не скрыт, зато транспорт проходит между циклами сканирования.", "Neither route is concealed, but transport crosses between scan cycles."), loc("Медленный переход попал в следующий цикл сканирования.", "The slow crossing was caught by the next scan cycle.")),
            ),
        ),
    ),
    "conflict": (
        variant(
            loc("Группа у шлюза", "Group at the lock"),
            loc("На фоне «{hazard}» у внешнего шлюза появилась группа. Как провести контакт?", "During '{hazard}', a group reaches the outer lock. How do you handle contact?"),
            (("screening", loc("Проверка", "Screening")), ("air", loc("Воздух шлюза", "Lock air")), ("offer", loc("Предложение", "Offer"))),
            (
                loc("Удалённая проверка и контролируемый карантин", "Remote screening and controlled quarantine"),
                loc("Обмен через внешний шлюз без доступа в ядро", "Trade through the outer lock without core access"),
                loc("Не открывать шлюз и наблюдать", "Keep the lock closed and observe"),
            ),
            (
                profile("contact_quarantine", 0, (loc("Достоверна за 12 минут", "Reliable in 12 minutes"), loc("45 минут", "45 minutes"), loc("Навыки и лекарства", "Skills and medicine")), loc("Воздуха хватает на проверку, а люди несут ценные ресурсы. Контролируемый карантин управляет риском.", "There is enough lock air for screening, and the group carries valuable resources. Controlled quarantine manages the risk."), loc("Протокол отверг безопасную проверку или открыл доступ без неё.", "The protocol rejected a safe screening opportunity or granted access without it.")),
                profile("contact_trade", 1, (loc("Не работает", "Unavailable"), loc("9 минут", "9 minutes"), loc("Фильтры за воду", "Filters for water")), loc("Проверка не помещается в запас воздуха, но бесконтактный обмен решает критический дефицит без открытия ядра.", "Screening exceeds the air supply, but contactless trade solves a critical shortage without opening the core."), loc("Воздух шлюза закончился до проверки, хотя безопасный бесконтактный обмен был возможен.", "Lock air expired before screening while safe contactless trade was available.")),
                profile("contact_deny", 2, (loc("Поддельные идентификаторы", "Forged identities"), loc("32 минуты", "32 minutes"), loc("Требуют аварийный доступ", "Demand emergency access")), loc("Идентификаторы поддельны, а группа требует доступ к внутренней системе. Наблюдение не даёт ей нового рычага.", "Identities are forged and the group demands internal access. Observation grants them no new leverage."), loc("Контакт дал неизвестной группе доступ к шлюзовой инфраструктуре.", "Contact gave an unknown group access to lock infrastructure.")),
            ),
        ),
        variant(
            loc("Раскол смены", "Crew fracture"),
            loc("Из-за «{hazard}» смена отказывается выполнять протокол. Как вернуть управление без потери бункера?", "Because of '{hazard}', the crew refuses the protocol. How do you restore control without losing the bunker?"),
            (("support", loc("Поддержка", "Support")), ("time", loc("Время", "Time")), ("authority", loc("Доступ", "Access"))),
            (
                loc("Провести короткое открытое голосование", "Hold a short open vote"),
                loc("Изолировать лидера отказа и продолжить протокол", "Isolate the refusal leader and continue"),
                loc("Передать решение технической группе", "Transfer the decision to the technical team"),
            ),
            (
                profile("crew_vote", 0, (loc("6 из 9 сомневаются", "6 of 9 uncertain"), loc("22 минуты", "22 minutes"), loc("Доступы распределены", "Access distributed")), loc("Большинство сомневается, но времени достаточно, а силовое решение расколет владельцев доступов. Короткое голосование возвращает легитимность.", "Most are uncertain, time is available, and force would split access holders. A short vote restores legitimacy."), loc("Решение без поддержки распределённой команды заблокировало несколько критических доступов.", "A decision without support from the distributed crew locked several critical controls.")),
                profile("crew_isolate", 1, (loc("1 лидер, остальные выполняют", "1 leader, others compliant"), loc("3 минуты", "3 minutes"), loc("Лидер у аварийного пульта", "Leader at emergency panel")), loc("Проблема локальна и срочна. Изоляция одного человека сохраняет рабочую смену и аварийный пульт.", "The problem is localized and urgent. Isolating one person preserves the functioning crew and emergency panel."), loc("Трёхминутное окно ушло на обсуждение, пока один человек удерживал аварийный пульт.", "The three-minute window was spent debating while one person controlled the emergency panel.")),
                profile("crew_technical", 2, (loc("Спор 4 против 4", "4 versus 4 split"), loc("12 минут", "12 minutes"), loc("Техники владеют данными", "Technicians hold telemetry")), loc("Группа разделена поровну, а ответ зависит от телеметрии. Техническая смена имеет данные и мандат на ограниченное решение.", "The group is evenly split and the answer depends on telemetry. The technical team has both data and a narrow mandate."), loc("Социальное решение заменило техническое при равном расколе и привело к неверному режиму систем.", "A social decision replaced a technical one during a deadlock and selected the wrong system mode.")),
            ),
        ),
    ),
    "evacuation": (
        variant(
            loc("Последнее окно", "Final window"),
            loc("Событие «{hazard}» делает убежище временным. Когда и как уходить?", "The '{hazard}' event makes the shelter temporary. When and how do you leave?"),
            (("collapse", loc("Отказ убежища", "Shelter failure")), ("window", loc("Окно", "Window")), ("readiness", loc("Готовность", "Readiness"))),
            (
                loc("Уходить немедленно на {transport}", "Leave immediately aboard {transport}"),
                loc("Ждать окна и идти по {long_route}", "Wait for the window and take {long_route}"),
                loc("Остаться и герметизировать {deep_zone}", "Stay and seal {deep_zone}"),
            ),
            (
                profile("evac_now", 0, (loc("Через 7 минут", "In 7 minutes"), loc("Открыто сейчас", "Open now"), loc("Транспорт готов", "Transport ready")), loc("Убежище не переживёт ожидание. Готовый транспорт и открытый маршрут требуют немедленного выхода.", "The shelter will not survive waiting. Ready transport and an open route demand immediate departure."), loc("Окно закрылось или убежище отказало раньше выбранного действия.", "The window closed or the shelter failed before the chosen action completed.")),
                profile("evac_wait", 1, (loc("Через 52 минуты", "In 52 minutes"), loc("Безопасно через 16 минут", "Safe in 16 minutes"), loc("Транспорт повреждён", "Transport damaged")), loc("Немедленный выход опасен, транспорт ненадёжен, а расчётное пешее окно открывается задолго до отказа.", "Immediate departure is unsafe, transport is unreliable, and the calculated foot window opens well before failure."), loc("Протокол вышел до безопасного окна или доверился повреждённому транспорту.", "The protocol departed before the safe window or trusted damaged transport.")),
                profile("evac_hold", 2, (loc("Стабилизирован", "Stabilized"), loc("Все маршруты закрыты на 9 часов", "All routes closed for 9 hours"), loc("Глубокое ядро на 18 дней", "Deep core rated for 18 days")), loc("Срочного отказа нет, все пути смертельны, а глубокое ядро автономно. Правильная эвакуация сейчас — не эвакуироваться.", "There is no imminent failure, every route is lethal, and the deep core is autonomous. The correct evacuation is not to evacuate yet."), loc("Группа вышла в закрытый маршрут, хотя автономное ядро обеспечивало безопасное ожидание.", "The group entered a closed route despite a safe autonomous deep core.")),
            ),
        ),
        variant(
            loc("Маяк исхода", "Exit beacon"),
            loc("На фоне «{hazard}» получены противоречивые сигналы эвакуации. Какому протоколу доверять?", "During '{hazard}', conflicting evacuation signals arrive. Which protocol do you trust?"),
            (("signal", loc("Сигнал", "Signal")), ("verification", loc("Проверка", "Verification")), ("shelter", loc("Убежище", "Shelter"))),
            (
                loc("Следовать к объекту «{ally_asset}»", "Head toward {ally_asset}"),
                loc("Остаться в {deep_zone} до подтверждения", "Remain in {deep_zone} until confirmation"),
                loc("Отправить {field_unit} для проверки маршрута", "Send {field_unit} to verify the route"),
            ),
            (
                profile("beacon_go", 0, (loc("Ключ подтверждён", "Key authenticated"), loc("Два независимых канала", "Two independent channels"), loc("Ресурс на 5 часов", "5 hours of shelter life")), loc("Сигнал подтверждён двумя каналами, а убежище скоро откажет. Ожидание опаснее перехода.", "The signal is verified through two channels and the shelter is failing soon. Waiting is more dangerous than moving."), loc("Подтверждённое окно эвакуации закрылось после исчерпания ресурса убежища.", "The authenticated evacuation window closed after shelter resources expired.")),
                profile("beacon_hold", 1, (loc("Ключ устарел", "Key expired"), loc("Источник один", "Single source"), loc("Ресурс на 12 дней", "12 days of shelter life")), loc("Сигнал не подтверждён, а убежище имеет большой запас. Ожидание снижает риск ложного маяка.", "The signal is unverified and shelter reserves are strong. Waiting reduces the risk of a false beacon."), loc("Группа последовала неподтверждённому маяку, покинув исправное убежище.", "The group followed an unverified beacon and abandoned a healthy shelter.")),
                profile("beacon_probe", 2, (loc("Ключ частично совпал", "Key partially matches"), loc("Канал повреждён", "Channel degraded"), loc("Ресурс на 36 часов", "36 hours of shelter life")), loc("Данных недостаточно для выхода или долгого ожидания. Дрон успевает проверить маршрут до критического срока.", "There is not enough evidence to leave or wait indefinitely. The drone can verify the route before the critical deadline."), loc("Протокол принял необратимое решение при неполных данных, хотя проверка укладывалась в запас времени.", "The protocol made an irreversible choice with incomplete data despite having time for verification.")),
            ),
        ),
    ),
}

PROFILE_RESOLUTION_VALUES: dict[str, dict[str, dict[str, str]]] = {
    "zero_local": {"route": loc("Локальный контур закрыт", "Local circuit sealed"), "integrity": loc("Отсек стабилен · 91%", "Compartment stable · 91%")},
    "zero_deep": {"route": loc("Группа в глубоком ядре", "Group inside deep core"), "integrity": loc("Ядро стабильно · 97%", "Core stable · 97%")},
    "zero_field": {"route": loc("Полевой коридор открыт", "Field corridor open"), "integrity": loc("Щит развёрнут · 86%", "Shield deployed · 86%")},
    "cascade_external": {"source": loc("Внешний узел отсечён", "External node isolated"), "margin": loc("Шина стабильна", "Bus stable")},
    "cascade_loop": {"margin": loc("Свободно 63%", "63% available"), "reserve": loc("12%", "12%")},
    "cascade_battery": {"margin": loc("Каскад погашен", "Cascade suppressed"), "reserve": loc("74%", "74%")},
    "geometry_local": {"structure": loc("Демпферы зафиксированы", "Dampers locked"), "mobility": loc("Группа закреплена", "Group secured")},
    "geometry_deep": {"structure": loc("Нагрузка ушла в фундамент", "Load transferred to foundation"), "mobility": loc("Лифт заблокирован в ядре", "Lift locked at core")},
    "geometry_mobile": {"structure": loc("Опасный сектор оставлен", "Danger sector abandoned"), "mobility": loc("Транспорт в резервной шахте", "Transport inside reserve shaft")},
    "air_isolate": {"contamination": loc("Изолировано", "Isolated"), "filters": loc("91%", "91%")},
    "air_filter": {"contamination": loc("Следы ниже порога", "Trace below threshold"), "filters": loc("96%", "96%")},
    "air_intake": {"contamination": loc("CO₂ в норме", "CO2 nominal"), "outside": loc("Забор закрыт после продувки", "Intake sealed after purge")},
    "power_primary": {"load": loc("72%", "72%"), "primary": loc("Номинальный режим", "Nominal mode"), "reserve": loc("18%", "18%")},
    "power_reserve": {"load": loc("43%", "43%"), "primary": loc("Изолирован", "Isolated"), "reserve": loc("76%", "76%")},
    "power_external": {"load": loc("68%", "68%"), "primary": loc("Номинальный режим", "Nominal mode"), "reserve": loc("7%", "7%")},
    "hull_reinforce": {"spread": loc("Остановлена", "Stopped"), "bulkhead": loc("Держит 88%", "Holding at 88%")},
    "hull_retreat": {"spread": loc("Опасный сектор отсечён", "Danger sector isolated"), "bulkhead": loc("Закрыта", "Sealed")},
    "hull_robot": {"spread": loc("Доступ стабилизирован", "Access stabilized"), "equipment": loc("Робот удерживает контур", "Robot holding the circuit")},
    "water_ration": {"reserve": loc("Хватит на 10 дней", "Enough for 10 days"), "team": loc("Норма подтверждена", "Ration confirmed")},
    "water_repair": {"reserve": loc("Потери остановлены", "Losses stopped"), "recovery": loc("Контур восстановлен", "Circuit restored")},
    "water_loop": {"reserve": loc("Замкнутый цикл активен", "Closed loop active"), "team": loc("Потери воды минимальны", "Water loss minimized")},
    "med_severe": {"cases": loc("Тяжёлые стабилизированы", "Severe cases stabilized"), "supply": loc("Экстренный запас выдан", "Emergency stock issued")},
    "med_prevent": {"exposure": loc("Риск подавлен", "Risk suppressed"), "supply": loc("Профилактика завершена", "Prophylaxis complete")},
    "med_retrieve": {"supply": loc("Спецкомплект доставлен", "Special kit retrieved"), "cases": loc("Лечение начато", "Treatment started")},
    "heat_people": {"temperature": loc("-24°C и растёт", "-24°C and rising"), "food": loc("Жилой контур сохранён", "Habitation loop preserved")},
    "heat_food": {"temperature": loc("-4°C, стабильно", "-4°C, stable"), "food": loc("Холодильный контур сохранён", "Cold storage preserved")},
    "heat_expedition": {"forecast": loc("Внешний запас получен", "External cache retrieved"), "food": loc("Запас пополнен", "Supply replenished")},
    "route_short": {"short": loc("Маршрут открыт", "Route open"), "vehicle": loc("Не требуется", "Not required")},
    "route_long": {"long": loc("Группа внутри безопасного окна", "Group inside safe window"), "short": loc("Закрыт", "Closed")},
    "route_vehicle": {"vehicle": loc("Опасная зона пройдена", "Danger zone crossed"), "long": loc("Окно закрыто", "Window closed")},
    "blind_tags": {"detection": loc("Цифровой след погашен", "Digital trace suppressed"), "cover": loc("Группа скрыта", "Group concealed")},
    "blind_decoy": {"detection": loc("Ложная цель захвачена", "Decoy acquired"), "battery": loc("31%", "31%")},
    "blind_vehicle": {"detection": loc("Цикл сканирования пропущен", "Scan cycle avoided"), "battery": loc("Проход завершён", "Crossing complete")},
    "contact_quarantine": {"screening": loc("Проверка пройдена", "Screening passed"), "air": loc("29 минут", "29 minutes")},
    "contact_trade": {"air": loc("4 минуты", "4 minutes"), "offer": loc("Обмен завершён", "Trade completed")},
    "contact_deny": {"screening": loc("Подделка подтверждена", "Forgery confirmed"), "offer": loc("Доступ отклонён", "Access denied")},
    "crew_vote": {"support": loc("7 из 9 поддерживают", "7 of 9 support"), "authority": loc("Доступы синхронизированы", "Access synchronized")},
    "crew_isolate": {"support": loc("Смена выполняет протокол", "Crew following protocol"), "authority": loc("Аварийный пульт возвращён", "Emergency panel recovered")},
    "crew_technical": {"support": loc("Техническое решение принято", "Technical decision accepted"), "authority": loc("Телеметрия подтверждена", "Telemetry confirmed")},
    "evac_now": {"collapse": loc("Сектор оставлен", "Sector abandoned"), "readiness": loc("Транспорт вышел", "Transport departed")},
    "evac_wait": {"window": loc("Безопасное окно открыто", "Safe window open"), "readiness": loc("Пешая группа вышла", "Foot group departed")},
    "evac_hold": {"collapse": loc("Глубокое ядро стабильно", "Deep core stable"), "readiness": loc("Автономный режим", "Autonomous mode")},
    "beacon_go": {"signal": loc("Маршрут принят", "Route accepted"), "shelter": loc("Эвакуация начата", "Evacuation started")},
    "beacon_hold": {"signal": loc("Ложный маяк отклонён", "False beacon rejected"), "verification": loc("Ожидание второго канала", "Awaiting second channel")},
    "beacon_probe": {"verification": loc("Маршрут подтверждён дроном", "Route verified by drone"), "shelter": loc("Ресурс на 34 часа", "34 hours of shelter life")},
}


def _format_text(value: dict[str, str], context: dict[str, dict[str, str]]) -> dict[str, str]:
    return {
        language: text.format(**{key: localized[language] for key, localized in context.items()})
        for language, text in value.items()
    }


def materialize_variant(
    *,
    category_key: str,
    stage: str,
    variant_index: int,
    hazard: dict[str, str],
) -> dict:
    source = deepcopy(STAGE_VARIANTS[stage][variant_index])
    context = {**CATEGORY_CONTEXT[category_key], "hazard": hazard}
    labels = source.pop("labels")
    choices = [
        {
            "text": _format_text(choice, context),
            "outcome": loc(
                "Выбранный протокол противоречил данным досье.",
                "The selected protocol contradicted the dossier telemetry.",
            ),
        }
        for choice in source.pop("choices")
    ]
    profiles = []
    for item in source.pop("profiles"):
        profiles.append(
            {
                "id": item["id"],
                "correct": item["correct"],
                "parameters": tuple(
                    (
                        key,
                        label,
                        _format_text(value, context),
                    )
                    for (key, label), value in zip(labels, item["values"], strict=True)
                ),
                "success": _format_text(item["success"], context),
                "failure": _format_text(item["failure"], context),
                "resolution_values": deepcopy(PROFILE_RESOLUTION_VALUES.get(item["id"], {})),
            }
        )
    return {
        "title": _format_text(source["title"], context),
        "prompt": _format_text(source["prompt"], context),
        "choices": choices,
        "profiles": profiles,
    }
