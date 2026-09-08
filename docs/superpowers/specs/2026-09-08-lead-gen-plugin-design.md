# Lead Gen Plugin — Design Spec

Date: 2026-09-08

## Purpose

Claude Code Plugin для двухэтапной генерации B2B-лидов:

1. **ICP Builder** — интервью с пользователем, формирует Ideal Customer Profile.
2. **Deep Research** — оркестратор параллельных агентов ищет реальные компании под ICP, проверяет их, находит публичные контакты компаний и людей-ЛПР, сохраняет результат в два файла-таблицы.

Источник для Phase 1 — диалог с пользователем (никаких внешних данных). Источники для Phase 2 — Firecrawl-скиллы (firecrawl-lead-gen, firecrawl-company-directories, firecrawl-deep-research, firecrawl-lead-research) плюс встроенные WebSearch/WebFetch как фоллбэк; дополнительные источники (Apollo, Hunter, LinkedIn Sales Navigator, отраслевые базы) подключаются, если пользователь подтвердил доступ на pre-flight.

## Non-goals

- Не строим отдельный MCP-сервер — Agent tool в Claude Code уже параллелит работу subagent'ов.
- Не заливаем лиды в CRM автоматически.
- Не храним историю в базе данных — только файлы в рабочей директории.
- Не делаем UI — весь процесс идёт через диалог и markdown/CSV файлы.
- Не делаем цикл обратной связи (good/bad лиды → уточнение ICP) и pre-meeting брифы — это следующая версия.

## Structure

```
lead-gen-plugin/
├── .claude-plugin/plugin.json
├── commands/
│   └── lead-gen.md              # входная точка: /lead-gen
└── skills/
    ├── icp-builder/SKILL.md     # Phase 1
    └── deep-research/SKILL.md   # Phase 2
```

`/lead-gen` — единственная команда-вход. Она объясняет пользователю, что сейчас начнётся интервью, и вызывает skill `icp-builder`. По завершении Phase 1 предлагает перейти к `deep-research` (с подтверждением, не автоматически).

## Рабочая директория

Каждый ICP живёт в своей папке: `leads/<slug>/`, где `slug` — короткая метка ICP латиницей (из one-line label Block A, согласованная с пользователем). Внутри:

```
leads/<slug>/
├── icp-brief.md              # Phase 1 output
├── research/
│   ├── <channel>.json        # сырые находки каждого агента-канала
│   ├── verified.json         # результат verifier pass
│   └── contacts.json         # результат contact enrichment
├── companies-<YYYY-MM-DD>.md # итоговая таблица 1 (+ .csv)
└── people-<YYYY-MM-DD>.md    # итоговая таблица 2 (+ .csv)
```

## Phase 1 — ICP Builder

Промпт пользователя (Discovery → Delivery) переносится в `skills/icp-builder/SKILL.md` почти без изменений: те же 9 слотов, интервью по 1-2 вопроса за ход с 3-5 предложенными вариантами, чекпоинт с Draft ICP и подтверждением "go".

Изменения относительно исходного промпта:

- **Block A (ICP Brief)** сохраняется в `leads/<slug>/icp-brief.md`: Offer, Target segment, Firmographics, Geography & language, Decision-maker (титулы ЛПР, влияющих, блокирующих), Core pain, Buying triggers, Must-have criteria, Nice-to-have criteria, Disqualifiers, Lookalike anchor.
- **Exclusion list** — отдельная секция в том же файле: существующие клиенты (из слота Proof) и конкуренты (из Disqualifiers, если названы). Эти компании не попадают в выдачу Phase 2.
- **Block B** (источники и query patterns на языке рынка) сохраняется как секция `## Search plan` в том же файле — вход для оркестратора, не копипаст для пользователя.

После сохранения скилл сообщает, что ICP готов, и спрашивает, запускать ли Phase 2 сейчас.

## Phase 2 — Deep Research оркестратор

`skills/deep-research/SKILL.md` читает `leads/<slug>/icp-brief.md` (если папок несколько — спрашивает, какую) и действует как оркестратор.

### Шаг 0 — Pre-flight

Один AskUserQuestion (multiSelect где уместно):

- Firecrawl: платный ключ или бесплатный hosted-тир.
- Дополнительные источники, к которым есть доступ: Apollo, Hunter, LinkedIn Sales Navigator, отраслевые базы, другое — или ничего.
- Желаемый объём N компаний (default 30–50).

От ответов зависят бюджеты и набор инструментов для агентов.

### Шаг 1 — Каналы поиска

Оркестратор формирует каналы из `## Search plan` (гео + язык определяют состав): бизнес-реестры/каталоги, Google Maps/отзывы, LinkedIn/соцсети, новости/тендеры/триггеры, отраслевые ассоциации/выставки. Количество и состав не фиксированы жёстко. Правило: при N > 50 дополнительно делить агентов по региону или суб-сегменту, иначе все каналы найдут одни и те же очевидные компании.

### Шаг 2 — Параллельный сбор (агенты-каналы)

По одному Agent (general-purpose) на канал, все в одном вызове параллельно. Каждый агент получает: критерии ICP, exclusion list, свой канал и query patterns, бюджет, список доступных источников из pre-flight. Агент **не считает score** — он собирает сырые факты и пишет `research/<channel>.json`:

```json
[{
  "company": "...", "domain": "...", "country": "...",
  "website": "url", "linkedin": "url|null", "instagram": "url|null",
  "facebook": "url|null", "google_maps": "url|null",
  "evidence": [{"criterion": "<must-have/nice-to-have/trigger id из ICP>", "found": true, "url": "...", "note": "1 line"}],
  "public_contacts": [{"type": "phone|email|form", "value": "...", "source_url": "..."}]
}]
```

Требования агенту: реальные действующие компании, каждый факт с URL, никаких догадок; если по каналу ничего нет — пустой массив, это не ошибка.

**Бюджет на агента** (default для бесплатного тира): ≤ 15 search, ≤ 20 scrape. При платном ключе — ×3. Указывается в промпте агента явно.

### Шаг 3 — Merge и скоринг (оркестратор, детерминированно)

- Мерж всех `research/*.json` по нормализованному домену (fallback — нормализованное название). Evidence и контакты объединяются, дубли по URL убираются.
- Исключение компаний из exclusion list.
- Score по формуле исходного промпта: must-have 60 баллов поровну на критерий — компания без хотя бы одного подтверждённого must-have **исключается**, не скорится; nice-to-have 25 баллов поровну; триггеры за последние 12 месяцев 15 баллов поровну.
- Сортировка по убыванию, срез до N × 1.3 (запас под отсев verifier'ом).

### Шаг 4 — Verifier pass

Отдельный агент (или несколько, батчами по ~10 компаний параллельно) для каждого кандидата открывает сайт и/или ключевые source URL и подтверждает каждый must-have. Пишет `research/verified.json`: `{domain, status: "confirmed|rejected|unverifiable", checked: [{criterion, confirmed, url}], reason}`. Оркестратор убирает `rejected`, `unverifiable` оставляет с пометкой в таблице. Срез до N.

### Шаг 5 — Contact enrichment

Для каждой подтверждённой компании агенты (батчами параллельно) ищут людей по титулам из слота Decision-maker: LinkedIn, страница команды на сайте, пресс-релизы, публикации, отраслевые каталоги; при наличии Apollo/Hunter — через них. Пишут `research/contacts.json`:

```json
[{
  "domain": "...", "company": "...",
  "people": [{"name": "...", "title": "...", "role": "decision-maker|influencer|blocker",
              "contacts": [{"type": "email|phone|linkedin|telegram|other", "value": "...", "source_url": "..."}]}]
}]
```

Только публичные данные с источником. Если человека нашли, а контакта нет — запись остаётся с пустыми контактами (имя + должность + LinkedIn уже ценность).

### Шаг 6 — Вывод

Два файла, каждый в `.md` и `.csv`:

**Таблица 1 — `companies-<date>`**, отсортирована по score:

| # | Company | Website | LinkedIn | Instagram | Facebook | Google Maps | Reviews | Score | Verification | Triggers (source URL) | Public contacts | Why it fits |

- `Reviews` — ссылка на отзывы (Google/Yandex/отраслевые) или `—`.
- `Verification` — `confirmed` / `unverifiable`.
- `Public contacts` — все найденные контакты компании в формате `значение_источник`, через `; `. Пример: `+971 4 123 4567_website; info@acme.ae_google_maps; contact-form_website`. Источник — короткая метка (`website`, `google_maps`, `linkedin`, `directory:<name>`, `facebook` и т.д.).
- `—` для отсутствующего канала. Google Maps — только у компаний с физической B2B-локацией.

**Таблица 2 — `people-<date>`**, сгруппирована по компании в порядке таблицы 1:

| # | Company | Name | Title | Role | Contacts | Profile source |

- `Role` — decision-maker / influencer / blocker (по ICP).
- `Contacts` — в том же формате `значение_источник`, через `; `. Пример: `a.ivanov@acme.ae_hunter; +971 50 123 4567_linkedin; linkedin.com/in/aivanov_linkedin`.
- `Profile source` — URL, где человек подтверждён в этой должности.

После таблиц в `companies-<date>.md` — 3–5 строк: какие критерии было сложнее всего проверить, какие каналы дали больше всего, как можно уточнить ICP.

## Error handling / edge cases

- `leads/*/icp-brief.md` не найден при прямом запуске `deep-research` — сообщить и предложить сначала пройти ICP Builder.
- Агент-канал вернул пустой массив — допустимо, канал просто не вносит вклад.
- Firecrawl недоступен / лимит исчерпан — агент переключается на WebSearch/WebFetch и отмечает это в своём JSON (`"degraded": true`); оркестратор предупреждает пользователя, что охват мог быть уже.
- Verifier не смог открыть сайт — `unverifiable`, компания остаётся с пометкой, а не выбрасывается.
- Контакты не найдены ни у одной компании — таблица 2 всё равно создаётся (с людьми без контактов или пустая) и это явно сообщается пользователю.

## Testing

Ручная проверка сквозного сценария: `/lead-gen` → интервью → `leads/<slug>/icp-brief.md` с exclusion list и search plan → подтвердить Phase 2 → pre-flight → `research/*.json` заполнены → `companies-*.md/.csv` и `people-*.md/.csv` с непустыми таблицами, работающими source URL хотя бы у части строк, контактами в формате `значение_источник`, ни одной компании из exclusion list.
