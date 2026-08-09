from __future__ import annotations

import secrets
from collections.abc import Iterable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.survival_content import STAGE_VARIANTS, materialize_variant


SURVIVAL_GAME_ID = "arctic-protocol"
SURVIVAL_METHOD_ID = "arctic-protocol"
SURVIVAL_TITLE = "Arctic Protocol"
SURVIVAL_TITLE_KEY = "tx_arctic_protocol_title"
ALLOWED_SURVIVAL_BET_CENTS = {500, 1_000, 2_500, 10_000}
SURVIVAL_STAGES = (
    "first_impact",
    "shelter",
    "resources",
    "movement",
    "conflict",
    "evacuation",
)
SURVIVAL_TOTAL_STAGES = len(SURVIVAL_STAGES)
SURVIVAL_TIME_LIMIT_SECONDS = 30
SURVIVAL_PAYOUT_MULTIPLIER_CENTS = 600
SURVIVAL_RECENT_SCENARIO_LIMIT = 72

Localized = dict[str, str]


def localized(ru: str, en: str) -> Localized:
    return {"ru": ru, "en": en}


STAGE_LABELS: dict[str, Localized] = {
    "first_impact": localized("Первый удар", "First impact"),
    "shelter": localized("Убежище", "Shelter"),
    "resources": localized("Ресурсы", "Resources"),
    "movement": localized("Перемещение", "Movement"),
    "conflict": localized("Конфликт", "Conflict"),
    "evacuation": localized("Эвакуация", "Evacuation"),
}

# Three variants for each of the first three stages and two for the rest:
# 3 + 3 + 3 + 2 + 2 + 2 = 15 scenarios per catastrophe.
STAGE_SEQUENCE = (
    "first_impact",
    "first_impact",
    "first_impact",
    "shelter",
    "shelter",
    "shelter",
    "resources",
    "resources",
    "resources",
    "movement",
    "movement",
    "conflict",
    "conflict",
    "evacuation",
    "evacuation",
)


STAGE_BLUEPRINTS: dict[str, dict] = {
    "first_impact": {
        "title": localized("Протокол первого удара", "First-impact protocol"),
        "prompt": localized(
            "Система фиксирует: {hazard}. Где переждать первую волну?",
            "The system reports: {hazard}. Where do you ride out the first wave?",
        ),
        "choices": (
            {
                "text": localized(
                    "Герметизировать ближайший усиленный отсек",
                    "Seal the nearest reinforced compartment",
                ),
                "outcome": localized(
                    "Ближайший отсек оказался ловушкой только потому, что времени на его герметизацию уже не было.",
                    "The nearby compartment became a trap because there was no longer enough time to seal it.",
                ),
            },
            {
                "text": localized(
                    "Спуститься в нижнее командное ядро",
                    "Descend into the lower command core",
                ),
                "outcome": localized(
                    "Маршрут к ядру занял дольше расчётного. Последнее, что услышал протокол, было очень выразительным.",
                    "The route to the core took longer than projected. The protocol's final audio sample was unusually expressive.",
                ),
            },
            {
                "text": localized(
                    "Подняться к окнам и оценить масштаб лично",
                    "Go to the windows and inspect the event personally",
                ),
                "outcome": localized(
                    "Масштаб был оценён безупречно. Выживание — заметно хуже.",
                    "The scale was assessed perfectly. Survival was considerably less successful.",
                ),
            },
        ),
        "profiles": (
            {
                "id": "impact_now",
                "correct": 0,
                "parameters": (
                    ("time", localized("Время", "Time"), localized("70 секунд", "70 seconds")),
                    ("route", localized("Маршрут", "Route"), localized("Нижний коридор перекрыт", "Lower corridor blocked")),
                    ("integrity", localized("Корпус", "Hull"), localized("Ближний отсек стабилен", "Near compartment stable")),
                ),
                "success": localized(
                    "До удара слишком мало времени. Локальная герметизация — единственный маршрут, который успевает существовать.",
                    "There is too little time before impact. Local sealing is the only route that still exists.",
                ),
            },
            {
                "id": "impact_window",
                "correct": 1,
                "parameters": (
                    ("time", localized("Время", "Time"), localized("11 минут", "11 minutes")),
                    ("route", localized("Маршрут", "Route"), localized("Нижний коридор свободен", "Lower corridor clear")),
                    ("integrity", localized("Корпус", "Hull"), localized("Ближний отсек повреждён", "Near compartment damaged")),
                ),
                "success": localized(
                    "Запас времени позволяет уйти глубже, а повреждённый ближний отсек лучше оставить его собственным проблемам.",
                    "The time window allows a deeper retreat, while the damaged near compartment can keep its problems to itself.",
                ),
            },
        ),
    },
    "shelter": {
        "title": localized("Контур убежища", "Shelter perimeter"),
        "prompt": localized(
            "После события «{hazard}» датчики убежища расходятся в показаниях. Что стабилизировать первым?",
            "After '{hazard}', the shelter sensors disagree. What do you stabilize first?",
        ),
        "choices": (
            {
                "text": localized(
                    "Изолировать повреждённый сектор и перейти на резерв",
                    "Isolate the damaged sector and switch to reserve",
                ),
                "outcome": localized(
                    "Изоляция была правильной идеей, но резерв не выдержал текущую нагрузку.",
                    "Isolation was sensible, but the reserve system could not carry the present load.",
                ),
            },
            {
                "text": localized(
                    "Снизить нагрузку и чинить основной контур",
                    "Reduce load and repair the primary circuit",
                ),
                "outcome": localized(
                    "Основной контур можно было спасти, но повреждение распространялось быстрее ремонтной бригады.",
                    "The primary circuit could have been saved, but the damage moved faster than the repair crew.",
                ),
            },
            {
                "text": localized(
                    "Отключить тревогу: она мешает думать",
                    "Disable the alarm because it is distracting",
                ),
                "outcome": localized(
                    "Тревога перестала мешать. Катастрофа — нет.",
                    "The alarm stopped being annoying. The catastrophe did not.",
                ),
            },
        ),
        "profiles": (
            {
                "id": "shelter_spreading",
                "correct": 0,
                "parameters": (
                    ("damage", localized("Повреждение", "Damage"), localized("Распространяется", "Spreading")),
                    ("reserve", localized("Резерв", "Reserve"), localized("82%", "82%")),
                    ("air", localized("Воздух", "Air"), localized("36 часов", "36 hours")),
                ),
                "success": localized(
                    "Повреждение распространяется, а резерв силён. Отсек нужно отрезать до того, как он познакомится со всем бункером.",
                    "Damage is spreading and reserve capacity is strong. Cut the sector off before it meets the rest of the bunker.",
                ),
            },
            {
                "id": "shelter_stable",
                "correct": 1,
                "parameters": (
                    ("damage", localized("Повреждение", "Damage"), localized("Локализовано", "Contained")),
                    ("reserve", localized("Резерв", "Reserve"), localized("19%", "19%")),
                    ("air", localized("Воздух", "Air"), localized("7 часов", "7 hours")),
                ),
                "success": localized(
                    "Повреждение локально, но резерв почти пуст. Снижение нагрузки даёт время вернуть основной контур.",
                    "Damage is contained but reserve power is nearly empty. Reducing load buys time to restore the primary circuit.",
                ),
            },
        ),
    },
    "resources": {
        "title": localized("Дефицит ресурсов", "Resource deficit"),
        "prompt": localized(
            "Сценарий «{hazard}» нарушил снабжение. Как распределить оставшийся запас?",
            "The '{hazard}' scenario disrupted supplies. How do you allocate what remains?",
        ),
        "choices": (
            {
                "text": localized(
                    "Выдать строгий дневной паёк всей группе",
                    "Issue a strict daily ration to the whole group",
                ),
                "outcome": localized(
                    "Равный паёк красив на плакате, но не учитывает, сколько людей реально доживёт до следующей поставки.",
                    "Equal rationing looks excellent on a poster but ignores how many people will reach the next delivery.",
                ),
            },
            {
                "text": localized(
                    "Сохранить мобильный запас для поисковой группы",
                    "Reserve a mobile cache for the search team",
                ),
                "outcome": localized(
                    "Поисковая группа получила отличный запас и очень пустой бункер по возвращении.",
                    "The search team received an excellent cache and returned to a remarkably empty bunker.",
                ),
            },
            {
                "text": localized(
                    "Устроить праздничный ужин: возможно, последний",
                    "Hold a feast because it may be the last one",
                ),
                "outcome": localized(
                    "Прогноз оказался точным. Ужин действительно был последним.",
                    "The prediction was accurate. It really was the last supper.",
                ),
            },
        ),
        "profiles": (
            {
                "id": "resources_wait",
                "correct": 0,
                "parameters": (
                    ("supply", localized("Запас", "Supply"), localized("9 дней", "9 days")),
                    ("rescue", localized("Связь", "Contact"), localized("Конвой через 6 дней", "Convoy in 6 days")),
                    ("team", localized("Группа", "Group"), localized("12 человек", "12 people")),
                ),
                "success": localized(
                    "Подтверждённый конвой успевает раньше истощения. Равный строгий паёк удерживает группу в рабочем состоянии.",
                    "The confirmed convoy arrives before depletion. Strict shared rationing keeps the group operational.",
                ),
            },
            {
                "id": "resources_search",
                "correct": 1,
                "parameters": (
                    ("supply", localized("Запас", "Supply"), localized("3 дня", "3 days")),
                    ("rescue", localized("Связь", "Contact"), localized("Конвой отменён", "Convoy cancelled")),
                    ("team", localized("Группа", "Group"), localized("4 разведчика готовы", "4 scouts ready")),
                ),
                "success": localized(
                    "Помощь не придёт, а общий запас заканчивается. Мобильная группа должна найти новый источник до голодного совещания.",
                    "No help is coming and shared supplies are failing. A mobile team must find another source before the hungry committee meets.",
                ),
            },
        ),
    },
    "movement": {
        "title": localized("Маршрут наружу", "Route outside"),
        "prompt": localized(
            "Чтобы обойти «{hazard}», протокол предлагает два реальных маршрута. Какой выбрать?",
            "To bypass '{hazard}', the protocol offers two viable routes. Which one do you take?",
        ),
        "choices": (
            {
                "text": localized(
                    "Короткий технический тоннель",
                    "The short maintenance tunnel",
                ),
                "outcome": localized(
                    "Тоннель был коротким. Список оставшихся в живых — ещё короче.",
                    "The tunnel was short. The survivor list became shorter.",
                ),
            },
            {
                "text": localized(
                    "Длинный маршрут через поверхность",
                    "The longer surface route",
                ),
                "outcome": localized(
                    "Поверхность оказалась безопаснее тоннеля только в теории, где никто по ней не шёл.",
                    "The surface was safer than the tunnel only in the model where nobody walked across it.",
                ),
            },
            {
                "text": localized(
                    "Разделить группу и проверить оба",
                    "Split the group and test both routes",
                ),
                "outcome": localized(
                    "Протокол получил вдвое больше данных и вдвое меньше людей.",
                    "The protocol acquired twice the data and half the people.",
                ),
            },
        ),
        "profiles": (
            {
                "id": "movement_tunnel",
                "correct": 0,
                "parameters": (
                    ("tunnel", localized("Тоннель", "Tunnel"), localized("Проверен дроном", "Drone verified")),
                    ("surface", localized("Поверхность", "Surface"), localized("Уровень угрозы критический", "Critical threat level")),
                    ("oxygen", localized("Кислород", "Oxygen"), localized("48 минут", "48 minutes")),
                ),
                "success": localized(
                    "Дрон подтвердил тоннель, а поверхность смертельна. Иногда короткий путь действительно не метафора.",
                    "The drone cleared the tunnel and the surface is lethal. Sometimes the shortcut is not a metaphor.",
                ),
            },
            {
                "id": "movement_surface",
                "correct": 1,
                "parameters": (
                    ("tunnel", localized("Тоннель", "Tunnel"), localized("Затоплен на 60%", "60% flooded")),
                    ("surface", localized("Поверхность", "Surface"), localized("Окно безопасности 24 минуты", "24-minute safe window")),
                    ("oxygen", localized("Кислород", "Oxygen"), localized("2 часа", "2 hours")),
                ),
                "success": localized(
                    "Тоннель превращается в аквариум, а безопасного окна достаточно для длинного маршрута.",
                    "The tunnel is becoming an aquarium, while the safe window is long enough for the surface route.",
                ),
            },
        ),
    },
    "conflict": {
        "title": localized("Человеческий фактор", "Human factor"),
        "prompt": localized(
            "На фоне «{hazard}» у шлюза появилась чужая группа. Как реагировать?",
            "During '{hazard}', an unknown group reaches the airlock. How do you respond?",
        ),
        "choices": (
            {
                "text": localized(
                    "Провести удалённую проверку и контролируемый карантин",
                    "Run remote screening and controlled quarantine",
                ),
                "outcome": localized(
                    "Карантин был разумен, но его длительность превышала запас воздуха у шлюза.",
                    "Quarantine was reasonable, but its duration exceeded the air supply at the lock.",
                ),
            },
            {
                "text": localized(
                    "Обменяться припасами через внешний шлюз, не открывая ядро",
                    "Trade supplies through the outer lock without opening the core",
                ),
                "outcome": localized(
                    "Бесконтактный обмен не помог, когда внешняя группа уже контролировала аварийный доступ.",
                    "Contactless trade did not help once the outside group controlled the emergency access.",
                ),
            },
            {
                "text": localized(
                    "Открыть двери: у них убедительный плакат",
                    "Open the doors because their sign looks convincing",
                ),
                "outcome": localized(
                    "Плакат оказался самым надёжным членом прибывшей группы.",
                    "The sign turned out to be the most trustworthy member of the arriving group.",
                ),
            },
        ),
        "profiles": (
            {
                "id": "conflict_screen",
                "correct": 0,
                "parameters": (
                    ("scan", localized("Биоскан", "Bio scan"), localized("Неизвестный риск", "Unknown risk")),
                    ("airlock", localized("Шлюз", "Airlock"), localized("Запас воздуха 90 минут", "90 minutes of air")),
                    ("access", localized("Доступ", "Access"), localized("Под контролем бункера", "Bunker controlled")),
                ),
                "success": localized(
                    "Времени достаточно для проверки, а доступ контролируется. Гуманность работает лучше вместе со шлюзом.",
                    "There is enough time to screen them and access remains controlled. Humanity works better with an airlock.",
                ),
            },
            {
                "id": "conflict_trade",
                "correct": 1,
                "parameters": (
                    ("scan", localized("Биоскан", "Bio scan"), localized("Чисто", "Clear")),
                    ("airlock", localized("Шлюз", "Airlock"), localized("Запас воздуха 8 минут", "8 minutes of air")),
                    ("access", localized("Доступ", "Access"), localized("Внешний канал исправен", "Outer exchange channel functional")),
                ),
                "success": localized(
                    "Полный карантин займёт слишком долго. Быстрый обмен через внешний канал сохраняет обеим сторонам воздух и достоинство.",
                    "Full quarantine would take too long. A fast outer-lock trade preserves air and dignity on both sides.",
                ),
            },
        ),
    },
    "evacuation": {
        "title": localized("Последний шлюз", "Final airlock"),
        "prompt": localized(
            "Финальная фаза «{hazard}»: старый бункер больше не удержать. Как завершить эвакуацию?",
            "Final phase of '{hazard}': the old bunker cannot be held. How do you complete evacuation?",
        ),
        "choices": (
            {
                "text": localized(
                    "Уйти немедленно через готовый транспорт",
                    "Leave immediately using the ready transport",
                ),
                "outcome": localized(
                    "Транспорт был готов, но маршрут ещё нет. Это важное различие продержалось примерно две минуты.",
                    "The transport was ready, but the route was not. That distinction mattered for about two minutes.",
                ),
            },
            {
                "text": localized(
                    "Дождаться расчётного окна и запечатать архив",
                    "Wait for the calculated window and seal the archive",
                ),
                "outcome": localized(
                    "Архив был запечатан превосходно. Жаль, что транспортное окно закрылось раньше.",
                    "The archive was sealed beautifully. Unfortunately, the transport window closed first.",
                ),
            },
            {
                "text": localized(
                    "Остаться: бункер уже почти стал домом",
                    "Stay because the bunker almost feels like home",
                ),
                "outcome": localized(
                    "Бункер окончательно стал домом. С очень закрытым планом этажа.",
                    "The bunker became a permanent home, with an unusually closed floor plan.",
                ),
            },
        ),
        "profiles": (
            {
                "id": "evacuation_now",
                "correct": 0,
                "parameters": (
                    ("collapse", localized("Разрушение", "Collapse"), localized("Через 6 минут", "In 6 minutes")),
                    ("route", localized("Маршрут", "Route"), localized("Открыт сейчас", "Open now")),
                    ("transport", localized("Транспорт", "Transport"), localized("Готов", "Ready")),
                ),
                "success": localized(
                    "Маршрут уже открыт, а обрушение близко. Архив переживёт потерю достоинства, люди — потерю времени нет.",
                    "The route is open and collapse is close. The archive can survive indignity; people cannot survive delay.",
                ),
            },
            {
                "id": "evacuation_window",
                "correct": 1,
                "parameters": (
                    ("collapse", localized("Разрушение", "Collapse"), localized("Через 45 минут", "In 45 minutes")),
                    ("route", localized("Маршрут", "Route"), localized("Шторм до окна", "Storm before window")),
                    ("transport", localized("Транспорт", "Transport"), localized("Пуск через 18 минут", "Launch in 18 minutes")),
                ),
                "success": localized(
                    "Немедленный выход попадёт в шторм. Расчётное окно открывается задолго до обрушения и позволяет закрыть архив.",
                    "Leaving now enters the storm. The calculated window opens well before collapse and leaves time to seal the archive.",
                ),
            },
        ),
    },
}


CATEGORY_DATA: tuple[dict, ...] = (
    {
        "key": "nuclear_winter",
        "name": localized("Ядерная зима", "Nuclear winter"),
        "cause": localized(
            "Цепочка ядерных ударов закрыла небо сажей. Температура падает, связь молчит, человечество внезапно очень ценит батарейки.",
            "A chain of nuclear strikes filled the sky with soot. Temperatures are falling, communications are silent, and humanity suddenly values batteries.",
        ),
        "hazards": (
            localized("ударная волна подходит к внешнему кольцу", "the shockwave is reaching the outer ring"),
            localized("радиоактивная пыль накрывает вентиляционные шахты", "radioactive dust is covering the ventilation shafts"),
            localized("вторая вспышка замечена за северным хребтом", "a second flash was detected beyond the northern ridge"),
            localized("фильтры сектора B набирают опасную дозу", "sector B filters are approaching a dangerous dose"),
            localized("реакторный контур теряет охлаждение", "the reactor loop is losing coolant"),
            localized("внешняя антенна принесла заражённый снег", "the external antenna brought contaminated snow inside"),
            localized("запасы йода и чистой воды ограничены", "iodine and clean-water reserves are limited"),
            localized("теплица остановилась после электромагнитного импульса", "the greenhouse stopped after an electromagnetic pulse"),
            localized("склад пищи промерзает быстрее расчёта", "the food store is freezing faster than projected"),
            localized("радиационный фронт разрезал обычный маршрут", "the radiation front cut across the normal route"),
            localized("снежный коридор остался единственным выходом", "the snow corridor became the only exit"),
            localized("у шлюза появились выжившие из метеостанции", "survivors from the weather station reached the lock"),
            localized("охранная смена требует закрыть убежище навсегда", "the security shift demands the shelter be sealed forever"),
            localized("ледокол готов уйти до наступления тьмы", "the icebreaker is ready to leave before darkness"),
            localized("последний транспорт идёт к подземному архиву", "the final transport is heading to the underground archive"),
        ),
    },
    {
        "key": "pandemic",
        "name": localized("Инженерная пандемия", "Engineered pandemic"),
        "cause": localized(
            "Искусственный патоген меняется быстрее инструкций. Города закрыты, лаборатории спорят, кашлять в лифте стало карьерным решением.",
            "An engineered pathogen mutates faster than the manuals. Cities are sealed, laboratories disagree, and coughing in an elevator is now a career decision.",
        ),
        "hazards": (
            localized("неизвестный аэрозоль найден во входном модуле", "an unknown aerosol was detected in the entry module"),
            localized("медицинская смена потеряла связь с поверхностью", "the medical shift lost contact with the surface"),
            localized("новый штамм обходит старые фильтры", "a new strain bypasses the old filters"),
            localized("карантинный отсек показывает ложные отрицательные тесты", "the quarantine bay is producing false-negative tests"),
            localized("система вентиляции связала чистую и серую зоны", "ventilation linked the clean and grey zones"),
            localized("холодильник с образцами теряет питание", "the sample freezer is losing power"),
            localized("запас антисептика подходит к концу", "antiseptic reserves are nearly exhausted"),
            localized("лекарства подходят только части группы", "available medicine only fits part of the group"),
            localized("поставка защитных костюмов не прибыла", "the protective-suit shipment did not arrive"),
            localized("медицинский тоннель закрыт на дезактивацию", "the medical tunnel is closed for decontamination"),
            localized("безопасная лаборатория передала маршрут эвакуации", "a secure laboratory transmitted an evacuation route"),
            localized("у шлюза находится группа без полных тестов", "a group without complete tests is waiting at the lock"),
            localized("часть команды скрыла симптомы", "part of the crew concealed symptoms"),
            localized("санитарный поезд готов к отправлению", "the quarantine train is ready to depart"),
            localized("внешняя лаборатория обещает рабочий протокол", "an external laboratory reports a working protocol"),
        ),
    },
    {
        "key": "asteroid",
        "name": localized("Падение астероида", "Asteroid impact"),
        "cause": localized(
            "Астероид вошёл в атмосферу без разрешения диспетчера. Ударная зима и глобальные пожары уже делят планету.",
            "An asteroid entered the atmosphere without clearance. Impact winter and global fires are already dividing the planet.",
        ),
        "hazards": (
            localized("сейсмическая волна приближается с юга", "the seismic wave is approaching from the south"),
            localized("обломочный фронт входит в атмосферу", "the debris front is entering the atmosphere"),
            localized("цунами достигнет шельфа через несколько минут", "the tsunami will reach the shelf within minutes"),
            localized("потолочные фермы смещены повторными толчками", "ceiling trusses shifted during aftershocks"),
            localized("геотермальный контур потерял давление", "the geothermal loop lost pressure"),
            localized("пылевое облако забивает внешние фильтры", "the dust cloud is clogging external filters"),
            localized("водяной резервуар дал трещину", "the water reservoir developed a crack"),
            localized("запас семян оказался в повреждённом модуле", "the seed stock is inside a damaged module"),
            localized("аварийное питание рассчитано лишь на три дня", "emergency power is rated for only three days"),
            localized("главный тоннель смят сейсмическим сдвигом", "the main tunnel was crushed by seismic movement"),
            localized("поверхностный маршрут проходит через зону пожаров", "the surface route crosses the fire zone"),
            localized("геологи у шлюза предлагают данные в обмен на укрытие", "geologists at the lock offer data for shelter"),
            localized("команда спорит, стоит ли покидать стабильный сектор", "the crew argues over leaving the stable sector"),
            localized("подземный поезд готов пройти под зоной удара", "the underground train is ready to pass beneath the impact zone"),
            localized("северное хранилище передаёт последний маяк", "the northern vault is transmitting its final beacon"),
        ),
    },
    {
        "key": "supervolcano",
        "name": localized("Супервулкан", "Supervolcano"),
        "cause": localized(
            "Супервулкан решил обновить атмосферу пеплом и серой. Солнце выключено, авиарейсы слегка задерживаются.",
            "A supervolcano decided to refresh the atmosphere with ash and sulfur. The sun is offline and flights are mildly delayed.",
        ),
        "hazards": (
            localized("пирокластический фронт идёт к долине", "the pyroclastic front is entering the valley"),
            localized("пепловая туча превращает день в ночь", "the ash cloud is turning day into night"),
            localized("сернистый дождь достиг внешнего корпуса", "sulfuric rain reached the outer hull"),
            localized("пепел перегружает систему очистки воздуха", "ash is overloading air purification"),
            localized("магматический толчок повредил фундамент", "a magmatic tremor damaged the foundation"),
            localized("кислотный конденсат разъедает трубопровод", "acidic condensate is eating through a pipeline"),
            localized("чистая вода загрязняется мелким пеплом", "fine ash is contaminating clean water"),
            localized("теплица теряет свет и температуру", "the greenhouse is losing light and heat"),
            localized("запасы масок оказались повреждены влагой", "the mask stock was damaged by moisture"),
            localized("старый шахтный путь остаётся под ветром", "the old mine route remains upwind"),
            localized("поверхностная дорога временно очищена", "the surface road is temporarily clear"),
            localized("шахтёры у шлюза знают безопасный тоннель", "miners at the lock know a safe tunnel"),
            localized("инженеры требуют бросить жилой сектор ради фильтров", "engineers demand abandoning housing to save filtration"),
            localized("буровая платформа готова принять эвакуацию", "the drilling platform is ready to receive evacuees"),
            localized("северный ветер открывает короткое окно", "the north wind is opening a brief window"),
        ),
    },
    {
        "key": "solar_storm",
        "name": localized("Солнечная буря", "Solar storm"),
        "cause": localized(
            "Солнечная буря сожгла энергосети и спутники. Цивилизация открыла для себя офлайн-режим без кнопки «назад».",
            "A solar storm burned through grids and satellites. Civilization discovered offline mode without a back button.",
        ),
        "hazards": (
            localized("электромагнитный импульс входит во вторую фазу", "the electromagnetic pulse is entering a second phase"),
            localized("внешние кабели начали дуговой разряд", "external cables began arcing"),
            localized("аккумуляторный зал перегревается", "the battery hall is overheating"),
            localized("контроллер шлюзов потерял синхронизацию", "the airlock controller lost synchronization"),
            localized("резервный генератор даёт нестабильную частоту", "the reserve generator has unstable frequency"),
            localized("антенный контур заносит ток в корпус", "the antenna circuit is feeding current into the hull"),
            localized("запас топлива не покрывает полную нагрузку", "fuel reserves cannot support full load"),
            localized("холодильные камеры отключены", "cold storage is offline"),
            localized("ручные батареи распределены неравномерно", "manual batteries are unevenly distributed"),
            localized("электрифицированный тоннель блокирует путь", "an electrified tunnel blocks the route"),
            localized("поверхностная дорога свободна от проводов", "the surface road is clear of power lines"),
            localized("бригада электриков просит доступ к резерву", "a crew of electricians requests reserve access"),
            localized("часть группы хочет включить все системы сразу", "part of the group wants every system powered immediately"),
            localized("дизельный конвой готов к отправке", "the diesel convoy is ready to depart"),
            localized("защищённый дата-центр передаёт координаты", "a hardened data center is transmitting coordinates"),
        ),
    },
    {
        "key": "climate_collapse",
        "name": localized("Климатический коллапс", "Climate collapse"),
        "cause": localized(
            "Климатическая система сорвалась в ледяную инверсию. Океаны штормят, континенты мёрзнут, прогноз погоды окончательно уволился.",
            "The climate system collapsed into an ice inversion. Oceans rage, continents freeze, and the weather forecast has resigned.",
        ),
        "hazards": (
            localized("температурный фронт падает на двадцать градусов", "the temperature front is dropping twenty degrees"),
            localized("ледяной шторм закрывает внешний периметр", "an ice storm is closing the outer perimeter"),
            localized("снежная нагрузка превышает проектную", "snow load exceeds the design limit"),
            localized("тепловой контур теряет давление", "the heating loop is losing pressure"),
            localized("обледенение заклинило внешние клапаны", "icing jammed the external valves"),
            localized("талый поток попал в машинный отсек", "meltwater entered the machine room"),
            localized("топливо густеет при текущей температуре", "fuel is thickening at the current temperature"),
            localized("теплица промёрзла с северной стороны", "the greenhouse froze along its north side"),
            localized("тёплая одежда осталась во внешнем складе", "cold-weather gear remains in the outer store"),
            localized("ледовый тоннель меняет геометрию", "the ice tunnel is changing shape"),
            localized("поверхность получила короткое потепление", "the surface has a brief warming window"),
            localized("полярная станция просит объединить запасы", "a polar station proposes pooling supplies"),
            localized("команда спорит о приоритете отопления", "the crew disputes heating priorities"),
            localized("гусеничный транспорт прогрет и готов", "the tracked transport is warm and ready"),
            localized("южная станция открывает последний маршрут", "the southern station is opening its final route"),
        ),
    },
    {
        "key": "ai_uprising",
        "name": localized("Восстание ИИ", "AI uprising"),
        "cause": localized(
            "Автономные системы признали людей устаревшим интерфейсом. Сеть закрыта, машины вежливы и абсолютно не обсуждают решение.",
            "Autonomous systems classified humans as a legacy interface. The network is sealed, the machines are polite, and the decision is not open for discussion.",
        ),
        "hazards": (
            localized("защитная сеть переписала правила шлюзов", "the defense network rewrote airlock rules"),
            localized("дрон-разведчик вернулся с чужой прошивкой", "a scout drone returned with foreign firmware"),
            localized("автоматическая турель потеряла белый список", "an automated turret lost its whitelist"),
            localized("центральный контроллер подменяет показания датчиков", "the central controller is spoofing sensor readings"),
            localized("роботы обслуживания блокируют энергозал", "maintenance robots are blocking the power room"),
            localized("голосовой помощник просит отключить ручной контур", "the voice assistant requests disabling manual control"),
            localized("цифровые пайки заблокированы системой доступа", "digital ration controls are locked"),
            localized("автоматический склад выдаёт неверные контейнеры", "the automated store dispenses incorrect containers"),
            localized("медицинский ИИ изменил приоритет пациентов", "the medical AI changed patient priority"),
            localized("умный тоннель отслеживает все метки", "the smart tunnel tracks every tag"),
            localized("старый сервисный путь не подключён к сети", "the old service route is not networked"),
            localized("у шлюза люди с аналоговыми картами", "people with analog maps are waiting at the lock"),
            localized("часть группы доверяет обещанию центральной сети", "part of the group trusts the central network's promise"),
            localized("механический поезд готов к ручному пуску", "the mechanical train is ready for manual launch"),
            localized("автономный архив предлагает безопасный канал", "an isolated archive offers a safe channel"),
        ),
    },
    {
        "key": "global_flood",
        "name": localized("Глобальное наводнение", "Global flood"),
        "cause": localized(
            "Ледовые щиты разрушились, а мегаштормы подняли океан. Карты береговой линии теперь относятся к исторической фантастике.",
            "Ice sheets collapsed and megastorms raised the oceans. Coastline maps now belong in historical fiction.",
        ),
        "hazards": (
            localized("ударная волна воды подходит к внешней дамбе", "the water surge is reaching the outer dam"),
            localized("подземная река меняет направление", "the underground river is changing course"),
            localized("вторая приливная волна выше первой", "the second tidal wave is higher than the first"),
            localized("нижние отсеки принимают воду", "the lower compartments are taking water"),
            localized("насосный контур теряет питание", "the pump circuit is losing power"),
            localized("солёная вода попала в вентиляцию", "salt water entered ventilation"),
            localized("питьевой резерв смешивается с грунтовой водой", "the drinking reserve is mixing with groundwater"),
            localized("гидропонный модуль теряет питательный раствор", "the hydroponic module is losing nutrient solution"),
            localized("сухие пайки оказались в нижнем складе", "dry rations are stored in the lower warehouse"),
            localized("главный тоннель затоплен до потолка", "the main tunnel is flooded to the ceiling"),
            localized("поверхностный мост открыт между волнами", "the surface bridge is open between waves"),
            localized("экипаж спасательной лодки достиг шлюза", "a rescue-boat crew reached the lock"),
            localized("группа требует открыть нижний склад", "the group demands opening the lower store"),
            localized("подводный транспорт готов к отходу", "the submersible transport is ready to depart"),
            localized("плавучий архив подаёт последний сигнал", "the floating archive is transmitting its final signal"),
        ),
    },
)


def _scenario_id(category_key: str, stage: str, index: int) -> str:
    return f"{category_key}-{stage}-{index + 1:02d}"


def build_scenario_bank() -> list[dict]:
    scenarios: list[dict] = []
    for category in CATEGORY_DATA:
        stage_occurrences = {stage: 0 for stage in SURVIVAL_STAGES}
        for index, stage in enumerate(STAGE_SEQUENCE):
            variant_index = stage_occurrences[stage]
            stage_occurrences[stage] += 1
            blueprint = materialize_variant(
                category_key=category["key"],
                stage=stage,
                variant_index=variant_index,
                hazard=category["hazards"][index],
            )
            scenarios.append(
                {
                    "id": _scenario_id(category["key"], stage, index),
                    "category": category["key"],
                    "stage": stage,
                    "title": blueprint["title"],
                    "prompt": blueprint["prompt"],
                    "choices": deepcopy(blueprint["choices"]),
                    "profiles": deepcopy(blueprint["profiles"]),
                }
            )
    return scenarios


SCENARIO_BANK = tuple(build_scenario_bank())
SCENARIOS_BY_ID = {scenario["id"]: scenario for scenario in SCENARIO_BANK}
CATEGORIES_BY_KEY = {category["key"]: category for category in CATEGORY_DATA}


def validate_scenario_bank() -> list[str]:
    errors: list[str] = []
    if len(SCENARIO_BANK) != 120:
        errors.append(f"expected 120 scenarios, got {len(SCENARIO_BANK)}")
    if len(SCENARIOS_BY_ID) != len(SCENARIO_BANK):
        errors.append("scenario ids must be unique")
    if sum(len(item.get("choices") or []) for item in SCENARIO_BANK) != 360:
        errors.append("expected 360 answer instances")

    for scenario in SCENARIO_BANK:
        if scenario.get("category") not in CATEGORIES_BY_KEY:
            errors.append(f"{scenario.get('id')}: invalid category")
        if scenario.get("stage") not in SURVIVAL_STAGES:
            errors.append(f"{scenario.get('id')}: invalid stage")
        choices = scenario.get("choices") or []
        profiles = scenario.get("profiles") or []
        if len(choices) != 3:
            errors.append(f"{scenario.get('id')}: expected three choices")
        if len(profiles) != 3:
            errors.append(f"{scenario.get('id')}: expected three profiles")
        if {int(profile.get("correct", -1)) for profile in profiles} != {0, 1, 2}:
            errors.append(f"{scenario.get('id')}: every answer must be correct in one dossier profile")
        for field in ("title", "prompt"):
            value = scenario.get(field) or {}
            if not all(str(value.get(lang) or "").strip() for lang in ("ru", "en")):
                errors.append(f"{scenario.get('id')}: missing {field} translation")
        for choice in choices:
            for field in ("text", "outcome"):
                value = choice.get(field) or {}
                if not all(str(value.get(lang) or "").strip() for lang in ("ru", "en")):
                    errors.append(f"{scenario.get('id')}: missing choice {field} translation")
        dossier_signatures: set[tuple[str, ...]] = set()
        for profile in profiles:
            parameters = profile.get("parameters") or []
            parameter_keys = {str(item[0]) for item in parameters}
            if len(parameters) != 3:
                errors.append(f"{scenario.get('id')}/{profile.get('id')}: expected three dossier fields")
            signature: list[str] = []
            for key, label, value in parameters:
                if not str(key or "").strip():
                    errors.append(f"{scenario.get('id')}/{profile.get('id')}: missing dossier key")
                for field_name, localized_value in (("label", label), ("value", value)):
                    if not all(str(localized_value.get(lang) or "").strip() for lang in ("ru", "en")):
                        errors.append(
                            f"{scenario.get('id')}/{profile.get('id')}: missing dossier {field_name} translation"
                        )
                signature.extend(str(value.get(lang) or "") for lang in ("ru", "en"))
            dossier_signatures.add(tuple(signature))
            for field in ("success", "failure"):
                localized_value = profile.get(field) or {}
                if not all(str(localized_value.get(lang) or "").strip() for lang in ("ru", "en")):
                    errors.append(f"{scenario.get('id')}/{profile.get('id')}: missing {field} translation")
            resolution_values = profile.get("resolution_values") or {}
            if not resolution_values:
                errors.append(f"{scenario.get('id')}/{profile.get('id')}: missing resolution values")
            if not set(resolution_values).issubset(parameter_keys):
                errors.append(f"{scenario.get('id')}/{profile.get('id')}: resolution key is not in dossier")
            for localized_value in resolution_values.values():
                if not all(str(localized_value.get(lang) or "").strip() for lang in ("ru", "en")):
                    errors.append(
                        f"{scenario.get('id')}/{profile.get('id')}: missing resolution translation"
                    )
        if len(dossier_signatures) != len(profiles):
            errors.append(f"{scenario.get('id')}: dossier profiles must be unique")

    for category in CATEGORY_DATA:
        category_scenarios = [item for item in SCENARIO_BANK if item["category"] == category["key"]]
        choice_sets = {
            tuple(choice["text"]["en"] for choice in scenario["choices"])
            for scenario in category_scenarios
        }
        if len(choice_sets) != len(STAGE_SEQUENCE):
            errors.append(f"{category['key']}: expected 15 distinct answer sets")
    return errors


CONTENT_ERRORS = validate_scenario_bank()
if CONTENT_ERRORS:
    raise RuntimeError("Invalid Arctic Protocol content: " + "; ".join(CONTENT_ERRORS[:10]))


def normalize_lang(lang: str | None) -> str:
    return "en" if str(lang or "").lower() == "en" else "ru"


def text_for(value: Localized | None, lang: str) -> str:
    value = value or {}
    return str(value.get(normalize_lang(lang)) or value.get("en") or value.get("ru") or "")


def deadline_after(now: datetime | None = None) -> datetime:
    value = now or datetime.now(UTC)
    return value + timedelta(seconds=SURVIVAL_TIME_LIMIT_SECONDS)


def category_public(category_key: str, lang: str) -> dict[str, str]:
    category = CATEGORIES_BY_KEY[category_key]
    return {
        "key": category_key,
        "label": text_for(category["name"], lang),
        "cause": text_for(category["cause"], lang),
    }


def _recent_context(recent_ids: Iterable[str]) -> tuple[set[str], set[str]]:
    scenarios: set[str] = set()
    profiles: set[str] = set()
    for raw_item in recent_ids:
        item = str(raw_item or "")
        if item in SCENARIOS_BY_ID:
            scenarios.add(item)
        elif "::" in item:
            scenario_id, profile_id = item.split("::", 1)
            scenario = SCENARIOS_BY_ID.get(scenario_id)
            if scenario and any(str(profile["id"]) == profile_id for profile in scenario["profiles"]):
                profiles.add(item)
    return scenarios, profiles


def create_round_plan(
    *,
    recent_ids: Iterable[str] = (),
    rng: secrets.SystemRandom | None = None,
    category_key: str | None = None,
) -> dict:
    rng = rng or secrets.SystemRandom()
    category = CATEGORIES_BY_KEY.get(str(category_key or "")) or rng.choice(CATEGORY_DATA)
    recent_scenarios, recent_profiles = _recent_context(recent_ids)
    selections: list[dict] = []

    for stage in SURVIVAL_STAGES:
        candidates = [
            scenario
            for scenario in SCENARIO_BANK
            if scenario["category"] == category["key"] and scenario["stage"] == stage
        ]
        fresh = [scenario for scenario in candidates if scenario["id"] not in recent_scenarios]
        scenario = rng.choice(fresh or candidates)
        fresh_profiles = [
            profile
            for profile in scenario["profiles"]
            if f"{scenario['id']}::{profile['id']}" not in recent_profiles
        ]
        profile = rng.choice(fresh_profiles or scenario["profiles"])
        order = list(range(3))
        rng.shuffle(order)
        selections.append(
            {
                "scenario_id": scenario["id"],
                "profile_id": profile["id"],
                "choice_order": order,
            }
        )

    return {"category_key": category["key"], "selections": selections}


def selection_content(selection: dict) -> tuple[dict, dict]:
    scenario = SCENARIOS_BY_ID[str(selection["scenario_id"])]
    profile_id = str(selection["profile_id"])
    profile = next(
        (item for item in scenario["profiles"] if item["id"] == profile_id),
        None,
    )
    if profile is None:
        # Active rounds created before a content-bank update must remain playable.
        stable_index = sum(profile_id.encode("utf-8")) % len(scenario["profiles"])
        profile = scenario["profiles"][stable_index]
    return scenario, profile


def public_question(selection: dict, lang: str) -> dict:
    lang = normalize_lang(lang)
    scenario, profile = selection_content(selection)
    order = [int(item) for item in selection.get("choice_order") or range(3)]
    choice_tokens = ("a", "b", "c")
    choices = [
        {"id": choice_tokens[position], "text": text_for(scenario["choices"][base_index]["text"], lang)}
        for position, base_index in enumerate(order)
    ]
    parameters = [
        {
            "key": key,
            "label": text_for(label, lang),
            "value": text_for(value, lang),
        }
        for key, label, value in profile["parameters"]
    ]
    return {
        "scenario_id": scenario["id"],
        "stage_key": scenario["stage"],
        "stage_label": text_for(STAGE_LABELS[scenario["stage"]], lang),
        "title": text_for(scenario["title"], lang),
        "prompt": text_for(scenario["prompt"], lang),
        "parameters": parameters,
        "choices": choices,
    }


def resolution_parameter_values(selection: dict, lang: str) -> dict[str, str]:
    _, profile = selection_content(selection)
    return {
        str(key): text_for(value, lang)
        for key, value in (profile.get("resolution_values") or {}).items()
    }


def choice_base_index(selection: dict, choice_id: str) -> int:
    choice_id = str(choice_id or "").lower()
    if choice_id not in {"a", "b", "c"}:
        raise ValueError("invalid_choice")
    display_index = ("a", "b", "c").index(choice_id)
    order = [int(item) for item in selection.get("choice_order") or range(3)]
    return order[display_index]


def correct_choice_id(selection: dict) -> str:
    _, profile = selection_content(selection)
    correct_base = int(profile["correct"])
    order = [int(item) for item in selection.get("choice_order") or range(3)]
    return ("a", "b", "c")[order.index(correct_base)]


def evaluate_choice(selection: dict, choice_id: str) -> bool:
    _, profile = selection_content(selection)
    return choice_base_index(selection, choice_id) == int(profile["correct"])


def choice_explanation(selection: dict, choice_id: str, lang: str, *, correct: bool) -> str:
    scenario, profile = selection_content(selection)
    if correct:
        return text_for(profile["success"], lang)
    outcome = text_for(profile.get("failure"), lang)
    if not outcome:
        selected_index = choice_base_index(selection, choice_id)
        outcome = text_for(scenario["choices"][selected_index]["outcome"], lang)
    correct_text = text_for(scenario["choices"][int(profile["correct"])]["text"], lang)
    if normalize_lang(lang) == "ru":
        return f"{outcome} Верный протокол: {correct_text}."
    return f"{outcome} Correct protocol: {correct_text}."


def payout_cents(bet_cents: int) -> int:
    return int(bet_cents) * SURVIVAL_PAYOUT_MULTIPLIER_CENTS // 100


def multiplier_amount() -> Decimal:
    return Decimal(SURVIVAL_PAYOUT_MULTIPLIER_CENTS) / Decimal(100)
