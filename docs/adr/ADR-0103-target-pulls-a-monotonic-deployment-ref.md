---
description: "Решение убрать GitHub Actions runner с production-хоста и развёртывать только монотонно продвигаемый ref после зелёного CI."
last_verified: "2026-08-29"
---

# ADR-0103: Target забирает монотонный deployment ref

Статус: принято. Заменяет в части постоянного GitHub Actions runner решение,
которое принадлежит приватной инфраструктуре и здесь не публикуется.
Уточнено `ADR-0109`: источником развёртывания становится публичный репозиторий,
транспорт этой записи при этом сохраняется.

## Контекст

Предыдущее решение правильно развернуло транспорт: production-хост устанавливает
исходящее соединение, а CI не получает SSH-ключ и не входит на сервер. Однако
постоянный Actions runner оставил на production-хосте credential, который
принимает исполняемый workflow, и сделал GitHub scheduler частью runtime
сервера — последнее постоянное Linux-исключение.

## Решение

Зелёный `check` точного push-коммита выполняет на одноразовом release worker
только promotion: без force продвигает `refs/heads/deploy/prod` на проверенный
SHA. Отложенный старый workflow не может откатить ref.

Production-хост больше не зарегистрирован как runner. Минутный systemd timer
исходящим соединением забирает единственный ref через read-only deploy key.
`deploy/pull-deploy.sh`:

- держит bare mirror и сериализует выполнение через `flock`;
- отказывается от не-fast-forward перехода относительно развёрнутого SHA;
- извлекает exact commit в content-addressed каталог;
- до изменения дерева пишет существующий recovery marker;
- сохраняет host-owned `.env*`, `.deploy-env`, `.deploy-state` и backups;
- вызывает неизменившиеся `deploy/run.sh` и `deploy/verify.sh`.

GitHub получает право записи только в promotion job. Target получает только
read-only Contents-доступ и не умеет менять checks, workflows или refs.

## Последствия

Actions credential и сервис runner удаляются с production-хоста после canary.
Развёртывание асинхронно относительно promotion job; авторитетный результат —
точная identity в `.deploy-state/current`, systemd journal и внешний
`verify_public.py`. Ручной exact-SHA deploy и rollback остаются рабочими.
