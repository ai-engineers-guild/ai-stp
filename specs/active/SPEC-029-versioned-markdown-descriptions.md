---
description: "SPEC-029: Неизменяемые безопасные Markdown-описания версий."
last_verified: "2026-08-09"
---

# SPEC-029: Неизменяемые безопасные Markdown-описания версий

## Цель

Дать компонентам и сетапам выразительное описание без второй изменяемой
документации, расхождения между CLI, API и web и возможности исполнить или скрыто
загрузить недоверенное содержимое.

## Границы

Входит поле `description` точного паспорта версии, формат `commonmark_v1`,
валидация, безопасный HTML, текстовый excerpt и общий malicious corpus. Отдельный
объектный текст, WYSIWYG-редактор, произвольный HTML, remote images и загрузка
вложений не входят.

## Термины

- `commonmark_v1` — закрытый профиль CommonMark с версионированными пределами и
  запрещёнными конструкциями;
- `safe_markdown_v1` — версия валидатора и renderer;
- excerpt — детерминированная однострочная текстовая проекция карточки.

## Требования

- `REQ-2901`: Единственное содержательное поле описания версии — `description` в
  неизменяемом `ComponentVersionPassport` или `SetupVersionPassport`; отдельного
  mutable documentation field нет.
- `REQ-2902`: Для passport schema v1 поле `description` всегда означает
  `commonmark_v1`; render projection явно объявляет format и renderer version, а
  exact source входит в канонические байты и digest паспорта.
- `REQ-2903`: Вход обязан быть непустым UTF-8, Unicode NFC, использовать только
  LF, занимать не больше 16 KiB и содержать не больше 256 строк.
- `REQ-2904`: Профиль разрешает абзацы, заголовки, выделение, inline code,
  ограждённые блоки кода, цитаты, разделитель, упорядоченные и неупорядоченные списки
  и ссылки только `https` либо локальные fragment links.
- `REQ-2905`: Raw HTML, images, небезопасные или неоднозначные URL, control
  characters и неизвестные token types закрываются отказом до сохранения версии.
- `REQ-2906`: `safe_markdown_v1` выдаёт deterministic sanitized HTML без raw
  source HTML; внешняя ссылка получает `rel="nofollow noopener noreferrer"`.
- `REQ-2907`: Excerpt извлекается из текстовых и code tokens, схлопывает
  whitespace, ограничивается 240 Unicode code points и завершает усечённый текст
  символом `…`.
- `REQ-2908`: API, CLI и web используют один versioned positive/malicious corpus;
  несовпадение accepted/rejected, HTML или excerpt является contract failure.
- `REQ-2909`: Изменение описания опубликованной версии не переписывает паспорт и
  создаёт новую версию `X.Y` по общим правилам registry.
- `REQ-2910`: Неподдерживаемый `description_format` или renderer version не
  понижается молча и возвращает typed incompatibility.

## Состояния и ошибки

Описание либо принято целиком, либо версия не создаётся. Частично очищенный input
не сохраняется. Нарушение профиля является неверным паспортом; неизвестная версия
формата или renderer является несовместимостью, а не пустым описанием.

## Безопасность и приватность

Renderer не выполняет код, не разрешает HTML и не загружает ресурсы. URL
проверяется после CommonMark parsing; percent-encoding, entity decoding и Unicode
не должны превращать запрещённую схему в разрешённую. Лимиты применяются до
дорогого parsing.

## Совместимость и миграция

До публичного выпуска старые паспорта без `description_format` читаются как
`commonmark_v1`, только если их `description` проходит текущий профиль; следующая
сериализация включает поле явно. Опубликованные байты после выпуска не
переписываются. Изменение grammar, лимитов, HTML или excerpt создаёт новый format
или renderer version.

## Критерии приёмки

| Требование | Исполнимый способ проверки |
|---|---|
| `REQ-2901` | Contract test доказывает отсутствие второго поля описания у паспорта и local object. |
| `REQ-2902` | Изменение description меняет canonical passport digest, а projection содержит exact format и renderer version. |
| `REQ-2903` | Boundary corpus покрывает bytes, lines, NFC, CR и control characters. |
| `REQ-2904` | Positive corpus сравнивает exact HTML и excerpt всех разрешённых конструкций. |
| `REQ-2905` | Malicious corpus отклоняет HTML, images, unsafe URL, controls и неизвестный token. |
| `REQ-2906` | Golden HTML не содержит source HTML и фиксирует безопасные link attributes. |
| `REQ-2907` | Golden excerpt покрывает whitespace, Unicode и точную границу 240 code points. |
| `REQ-2908` | Python contract test валидирует каждую запись общего JSON corpus; web owner подключает тот же файл без копии. |
| `REQ-2909` | Registry test отклоняет замену bytes известной версии и принимает новую minor version. |
| `REQ-2910` | Неизвестные format и renderer version дают typed incompatibility. |
