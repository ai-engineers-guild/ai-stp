---
title: "Карта команд"
description: "Каждая команда ai-stp, сгруппированная по странице справочника. Флаги берутся из machine help."
---

# Карта команд

Таблица перечисляет каждую команду, объявленную в реестре установленного CLI.
Флаги, правила параметров и `next_actions` сюда не копируются: они меняются
вместе с установленной версией. Их читает CLI:

```bash
ai-stp help --agent --json
```

`mutability` говорит, что команда делает. `confirmation` — каким токеном
подтверждается решение. Ни то ни другое не заменяет чтение дескриптора перед вызовом.

Исполняемый файл — `ai-stp`. Пакет на PyPI — `ai-stp-cli`.

| Команда | Mutability | Confirmation | Страница | Зачем |
| --- | --- | --- | --- | --- |
| `ai-stp eval profile` | `read` | `none` | [eval.md](eval.md) | показать версионированный эталонный профиль оценки для всех или одного типа компонента |
| `ai-stp eval plan` | `plan` | `none` | [eval.md](eval.md) | привязать эталонный профиль оценки к одному точному локальному графу сетапа |
| `ai-stp eval run` | `apply` | `plan_digest` | [eval.md](eval.md) | прогнать локальные детерминированные проверки для одного подтверждённого точного плана оценки |
| `ai-stp eval status` | `read` | `none` | [eval.md](eval.md) | прочитать неизменяемый статус одного локального прогона оценки |
| `ai-stp eval show` | `read` | `none` | [eval.md](eval.md) | показать полные неизменяемые локальные evidence одного прогона оценки |
| `ai-stp publication plan` | `plan` | `none` | [publication.md](publication.md) | создать неизменяемый серверный план для одной точной выпущенной версии компонента |
| `ai-stp attestation sign` | `apply` | `explicit_flag` | [publication.md](publication.md) | подписать точные тестовые данные, зависящие от учётных данных, активным ключом устройства |
| `ai-stp publication status` | `read` | `none` | [publication.md](publication.md) | прочитать текущее серверное состояние одного плана публикации |
| `ai-stp publication confirm` | `apply` | `explicit_flag` | [publication.md](publication.md) | подтвердить один точный неистёкший хеш плана публикации |
| `ai-stp grant list` | `read` | `none` | [grant.md](grant.md) | перечислить приглашения и выдачи мажорных линий текущего аккаунта |
| `ai-stp grant invite` | `apply` | `explicit_flag` | [grant.md](grant.md) | создать email-приглашение на одну точную мажорную линию объекта |
| `ai-stp grant direct` | `apply` | `explicit_flag` | [grant.md](grant.md) | выдать одну точную мажорную линию объекта явному идентификатору аккаунта |
| `ai-stp grant accept` | `apply` | `explicit_flag` | [grant.md](grant.md) | принять приглашение по токену из именованной переменной окружения |
| `ai-stp grant invitation revoke` | `destructive` | `explicit_flag` | [grant.md](grant.md) | отозвать одно ожидающее приглашение, не удаляя локальные байты |
| `ai-stp grant revoke` | `destructive` | `explicit_flag` | [grant.md](grant.md) | отозвать одну активную выдачу только вперёд, сохранив локальные байты |
| `ai-stp report preview` | `plan` | `none` | [report.md](report.md) | подготовить и показать точный ограниченный payload жалобы без отправки |
| `ai-stp report confirm` | `apply` | `explicit_flag` | [report.md](report.md) | отправить ровно один устойчивый превью жалобы после явного подтверждения |
| `ai-stp report list` | `read` | `none` | [report.md](report.md) | перечислить закрытые кейсы жалоб текущего аккаунта |
| `ai-stp owner objects` | `read` | `none` | [owner.md](owner.md) | перечислить объекты, которыми владеет аутентифицированный аккаунт |
| `ai-stp owner object show` | `read` | `none` | [owner.md](owner.md) | прочитать один серверно-авторизованный свой объект и его точные версии |
| `ai-stp owner version show` | `read` | `none` | [owner.md](owner.md) | прочитать одну точную свою версию и её evidence жизненного цикла на сервере |
| `ai-stp auth complete` | `apply` | `none` | [auth.md](auth.md) | завершить ожидающий вход, когда пользователь его одобрил |
| `ai-stp auth login` | `apply` | `none` | [auth.md](auth.md) | начать вход и сообщить код, который пользователь должен одобрить |
| `ai-stp auth logout` | `apply` | `none` | [auth.md](auth.md) | закончить облачную сессию на сервере и здесь, сохранив все локальные данные |
| `ai-stp auth status` | `read` | `none` | [auth.md](auth.md) | сообщить связь с платформой: только локально, authenticated, expired или revoked |
| `ai-stp capabilities` | `read` | `none` | [observe.md](observe.md) | сообщить, что эта установка может делать прямо сейчас |
| `ai-stp component discover` | `read` | `none` | [component-discover.md](component-discover.md) | перечислить нативные компоненты в корнях harness и одном проекте; ничего не меняет |
| `ai-stp component scaffold plan` | `plan` | `none` | [component-discover.md](component-discover.md) | предпросмотр точных файлов и дайджестов одного версионированного scaffold компонента |
| `ai-stp component scaffold apply` | `apply` | `plan_digest` | [component-discover.md](component-discover.md) | создать ровно подтверждённый scaffold компонента, не перезаписывая путь |
| `ai-stp component template render` | `read` | `none` | [component-discover.md](component-discover.md) | отрендерить и провалидировать переносимый шаблон для одного конкретного harness |
| `ai-stp component source parse` | `read` | `none` | [component-source.md](component-source.md) | разобрать внешний источник компонента как недоверенное структурированное намерение |
| `ai-stp component source resolve` | `read` | `none` | [component-source.md](component-source.md) | привязать GitHub-намерение источника к одному точному полному SHA коммита |
| `ai-stp component source search` | `read` | `none` | [component-source.md](component-source.md) | искать имена каталога; попадания пакетов и GitHub требуют --registry-discovery |
| `ai-stp component publish` | `plan` | `none` | [component-publish.md](component-publish.md) | извлечь один встроенный компонент в обычный план публикации |
| `ai-stp component source evidence refresh` | `apply` | `none` | [component-source.md](component-source.md) | обновить официальные GitHub-архивные evidence одной точной локальной версии |
| `ai-stp component source evidence show` | `read` | `none` | [component-source.md](component-source.md) | показать последние локальные GitHub-архивные evidence и свежесть |
| `ai-stp component source evidence history` | `read` | `none` | [component-source.md](component-source.md) | показать ограниченную append-only историю GitHub-архивных evidence |
| `ai-stp component adopt` | `apply` | `none` | [component-discover.md](component-discover.md) | зарегистрировать один обнаруженный компонент в локальном реестре |
| `ai-stp component passport show` | `read` | `none` | [component-passport.md](component-passport.md) | показать текущий локальный черновик паспорта одного принятого компонента |
| `ai-stp component passport suggest` | `read` | `none` | [component-passport.md](component-passport.md) | предложить точные факты манифеста для подтверждения, не меняя черновик |
| `ai-stp component passport update` | `apply` | `plan_digest` | [component-passport.md](component-passport.md) | добавить подтверждённые заявленные факты как новую content-addressed ревизию паспорта |
| `ai-stp component passport validate` | `read` | `none` | [component-passport.md](component-passport.md) | сообщить каждый структурный блокер публикации текущей ревизии паспорта |
| `ai-stp component passport quality` | `read` | `none` | [component-passport.md](component-passport.md) | показать необязательные механические подсказки авторинга, не меняя доверие и готовность |
| `ai-stp component forget` | `apply` | `none` | [component-discover.md](component-discover.md) | пометить зарегистрированный компонент удалённым, сохранив историю |
| `ai-stp consent allow` | `apply` | `none` | [consent.md](consent.md) | записать согласие на неверифицированные объекты одного издателя или мажорной линии |
| `ai-stp consent revoke` | `apply` | `none` | [consent.md](consent.md) | отозвать согласие; для последующих запросов действует сразу |
| `ai-stp consent list` | `read` | `none` | [consent.md](consent.md) | каждое согласие, которое ещё в силе, и что оно покрывало в момент выдачи |
| `ai-stp component version list` | `read` | `none` | [component-publish.md](component-publish.md) | каждая записанная версия одного объекта и следующий minor |
| `ai-stp component version release` | `apply` | `none` | [component-publish.md](component-publish.md) | дать текущему head неизменяемый номер X.Y; minor, если не сказано иначе |
| `ai-stp component fork` | `apply` | `none` | [component-publish.md](component-publish.md) | скопировать одну записанную версию под новой идентичностью; оригинал не трогается |
| `ai-stp component find` | `read` | `none` | [component-discover.md](component-discover.md) | искать в локальном реестре по префиксу, фразе, тегу или полю; без модели и сети |
| `ai-stp config init` | `apply` | `none` | [config.md](config.md) | создать файл конфигурации, если его нет, и в любом случае провалидировать |
| `ai-stp config set` | `apply` | `none` | [config.md](config.md) | записать заявленные значения в файл конфигурации |
| `ai-stp config unset` | `apply` | `none` | [config.md](config.md) | убрать заявленные значения, чтобы снова действовали значения по умолчанию |
| `ai-stp config validate` | `read` | `none` | [config.md](config.md) | прочитать файл конфигурации и отказать, если его нельзя соблюсти |
| `ai-stp config show` | `read` | `none` | [config.md](config.md) | показать действующую конфигурацию и откуда взялось каждое значение |
| `ai-stp device reset` | `destructive` | `explicit_flag` | [device.md](device.md) | вывести эту идентичность устройства из строя и создать новую |
| `ai-stp device init` | `apply` | `none` | [device.md](device.md) | создать идентичность этой установки или вернуть существующую |
| `ai-stp device show` | `read` | `none` | [device.md](device.md) | показать идентичность устройства и где хранится ключ |
| `ai-stp doctor` | `read` | `none` | [observe.md](observe.md) | сообщить о состоянии установки этой инсталляции, ничего не меняя |
| `ai-stp help` | `read` | `none` | [observe.md](observe.md) | выдать полный реестр команд для агента |
| `ai-stp link web` | `read` | `none` | [auth.md](auth.md) | напечатать канонический веб-URL и обратимую ссылку CLI |
| `ai-stp passport developer init` | `apply` | `none` | [passport.md](passport.md) | создать паспорт разработчика этой установки |
| `ai-stp passport developer show` | `read` | `none` | [passport.md](passport.md) | показать паспорт разработчика на текущем head |
| `ai-stp passport developer update` | `apply` | `none` | [passport.md](passport.md) | заявить факты разработчика, добавив одну ревизию |
| `ai-stp passport device refresh` | `apply` | `none` | [passport.md](passport.md) | создать паспорт устройства или привести его к тому, что сейчас наблюдаемо |
| `ai-stp passport device show` | `read` | `none` | [passport.md](passport.md) | показать паспорт устройства на текущем head |
| `ai-stp project discover` | `read` | `none` | [project.md](project.md) | перечислить проекты внутри названного каталога; больше ничего не сканирует |
| `ai-stp project index` | `read` | `none` | [project.md](project.md) | проиндексировать один корень проекта, ограниченно, пропуская секреты и двоичное содержимое |
| `ai-stp project symbols` | `read` | `none` | [project.md](project.md) | прочитать публичные символы проекта, точки входа и тесты; графа вызовов нет |
| `ai-stp harness install` | `apply` | `none` | [harness.md](harness.md) | установить саму программу harness под точным prefix |
| `ai-stp harness update` | `apply` | `none` | [harness.md](harness.md) | сдвинуть выставленную программу harness на версию, которую закрепляет провайдер |
| `ai-stp harness remove` | `destructive` | `explicit_flag` | [harness.md](harness.md) | удалить программу harness, которую поставил этот CLI, и ничего больше |
| `ai-stp harness resume` | `apply` | `none` | [harness.md](harness.md) | закрыть остановленную операцию программы, глядя, никогда не применяя снова |
| `ai-stp harness status` | `read` | `none` | [harness.md](harness.md) | какая программа стоит под одним prefix, из журнала и с диска |
| `ai-stp toolchain install` | `apply` | `none` | [toolchain.md](toolchain.md) | установить один закреплённый инструмент в управляемый каталог; из него ничего не запускает |
| `ai-stp toolchain remove` | `destructive` | `explicit_flag` | [toolchain.md](toolchain.md) | удалить один управляемый инструмент, трогая только пути, которые создал этот CLI |
| `ai-stp project passport` | `apply` | `none` | [project.md](project.md) | записать ревизию паспорта проекта, закрепляющую индекс, toolchain и конфигурацию |
| `ai-stp registry acquire` | `apply` | `none` | [registry.md](registry.md) | получить один точный опубликованный граф сетапа для локальной офлайн-компиляции |
| `ai-stp registry port discover` | `read` | `none` | [registry.md](registry.md) | найти совместимые снапшоты SX и APM под одним явно названным локальным корнем |
| `ai-stp registry port inspect` | `read` | `none` | [registry.md](registry.md) | инспектировать одно отображение setup-store без импорта и без запуска его CLI |
| `ai-stp registry port plan` | `plan` | `none` | [registry.md](registry.md) | предпросмотр только локального импорта setup-store с привязкой к точным байтам манифеста |
| `ai-stp registry port import` | `apply` | `plan_digest` | [registry.md](registry.md) | импортировать подтверждённый точный снапшот SX или APM только в локальный реестр |
| `ai-stp registry fetch` | `apply` | `none` | [registry.md](registry.md) | загрузить точные байты одной опубликованной версии в локальный кэш |
| `ai-stp registry search` | `read` | `none` | [registry.md](registry.md) | искать в публичном каталоге без учётной записи |
| `ai-stp registry version` | `read` | `none` | [registry.md](registry.md) | показать одну точную опубликованную версию и её верифицированный паспорт |
| `ai-stp registry show` | `read` | `none` | [registry.md](registry.md) | показать один объект каталога и его опубликованные версии |
| `ai-stp select eligibility` | `read` | `none` | [select.md](select.md) | из каких кандидатов harness может быть собран, и почему каждый отказ |
| `ai-stp select eligibility-matrix` | `read` | `none` | [select.md](select.md) | куда можно собрать один объект, для каждого поддерживаемого harness |
| `ai-stp select impact` | `read` | `none` | [select.md](select.md) | сравнить контекст, стоимость токенов и capabilities точных локальных версий сетапа |
| `ai-stp select blast-radius` | `read` | `none` | [select.md](select.md) | показать локальные ссылки сетапа, проекта, устройства и установленного target на компонент |
| `ai-stp select propose` | `plan` | `none` | [select.md](select.md) | записать одно composition proposal; без версии и без target |
| `ai-stp select confirm` | `apply` | `none` | [select.md](select.md) | заморозить одно proposal как частную версию сетапа, trace и pin |
| `ai-stp select cancel` | `apply` | `none` | [select.md](select.md) | закрыть одно proposal, не создавая версию и не меняя target |
| `ai-stp select graph` | `read` | `none` | [select.md](select.md) | разрешить точное замыкание зависимостей или назвать каждую причину, почему нельзя |
| `ai-stp select reports` | `read` | `none` | [select.md](select.md) | отчёты состава и конверсии: что выбрано, что конфликтует, что теряется |
| `ai-stp select bundle` | `read` | `none` | [select.md](select.md) | скомпилировать детерминированный пакет одного состава; в target не пишет |
| `ai-stp install plan` | `plan` | `none` | [install.md](install.md) | посчитать неизменяемый план установки; сам по себе ничего не делает |
| `ai-stp install approve` | `apply` | `plan_digest` | [install.md](install.md) | одобрить один план по точному digest; ничто другое его не одобряет |
| `ai-stp install apply` | `apply` | `plan_digest` | [install.md](install.md) | выполнить один одобренный план через провайдер и записать, что случилось |
| `ai-stp install cancel` | `apply` | `none` | [install.md](install.md) | бросить план до применения; отказ, если применение уже началось |
| `ai-stp target status` | `read` | `none` | [target.md](target.md) | ежедневное состояние одного проекта и harness; читает, ничего не обновляет |
| `ai-stp sync preview` | `read` | `none` | [sync.md](sync.md) | предпросмотр локального fast-forward, merge или конфликта без изменения head |
| `ai-stp sync push` | `apply` | `explicit_flag` | [sync.md](sync.md) | запушить один точный локальный head с устойчивым безопасным для воспроизведения событием |
| `ai-stp sync merge` | `apply` | `explicit_flag` | [sync.md](sync.md) | зафиксировать механически чистый мёрж двух head паспортов разработчика |
| `ai-stp sync pull` | `apply` | `explicit_flag` | [sync.md](sync.md) | получить и атомарно применить одну ограниченную страницу из потока учётной записи |
| `ai-stp target diff` | `read` | `none` | [target.md](target.md) | что изменила бы установка выбранной версии; ничего не меняет |
| `ai-stp telemetry show` | `read` | `none` | [telemetry.md](telemetry.md) | что нёс бы анонимный install ping и включён ли он |
| `ai-stp telemetry consent` | `apply` | `explicit_flag` | [telemetry.md](telemetry.md) | ответить на экран телеметрии; сам ничего не отправляет |
| `ai-stp target backups` | `read` | `none` | [target.md](target.md) | копии provider, из которых эта пара может восстановиться; сама ничего не восстанавливает |
| `ai-stp target rollback` | `read` | `none` | [target.md](target.md) | назвать точную предыдущую verified-версию; сама ничего не откатывает |
| `ai-stp install status` | `read` | `none` | [install.md](install.md) | операции, которые остановились без закрытого исхода; ничего не меняет |
| `ai-stp install recover` | `read` | `none` | [install.md](install.md) | что оставила одна остановленная операция и что можно сделать; сама ничего не восстанавливает |
| `ai-stp install resume` | `apply` | `none` | [install.md](install.md) | довести проверку результата, которую прерванный apply так и не сделал; ничего не применяет |
| `ai-stp setup compose plan` | `plan` | `none` | [setup.md](setup.md) | разрешить и зафиксировать новый сетап из точных источников каталога, Git, пакетов и path |
| `ai-stp setup compose apply` | `apply` | `explicit_flag` | [setup.md](setup.md) | записать точный, по-прежнему актуальный смешанный сетап как одну неизменяемую локальную версию |
| `ai-stp setup import inspect` | `read` | `none` | [setup.md](setup.md) | прочитать одну нативную конфигурацию и сообщить, что в ней; ничего не пишет |
| `ai-stp setup import plan` | `plan` | `none` | [setup.md](setup.md) | спланировать точные черновики компонентов и сетапа из одной нативной конфигурации |
| `ai-stp setup publish plan` | `plan` | `none` | [setup.md](setup.md) | спланировать публикацию одного выпущенного сетапа со всеми компонентами, которые он фиксирует |
| `ai-stp setup publish confirm` | `apply` | `explicit_flag` | [setup.md](setup.md) | подтвердить один точный отрецензированный набор публикации: закреплённые компоненты, затем сетап |
| `ai-stp setup update plan` | `plan` | `none` | [setup.md](setup.md) | предпросмотр замены одного встроенного компонента более новым точным снапшотом |
| `ai-stp setup update apply` | `apply` | `explicit_flag` | [setup.md](setup.md) | подтвердить одно точное встроенное обновление и создать новую неизменяемую версию сетапа |
| `ai-stp setup import register` | `apply` | `plan_digest` | [setup.md](setup.md) | зарегистрировать проинспектированную конфигурацию как свой сетап; секретные значения не хранятся |
| `ai-stp provider conformance` | `read` | `none` | [provider.md](provider.md) | проверить одного провайдера по явно выбранному протоколу; ничего не меняет |
| `ai-stp component skill validate` | `read` | `none` | [component-publish.md](component-publish.md) | проверить skill-пакет по Agent Skills Specification и назвать каждое отклонение; ничего не меняет |
| `ai-stp provider check` | `read` | `none` | [provider.md](provider.md) | сообщить установленный провайдер каждого harness и есть ли более новый релиз; ничего не меняет |
| `ai-stp provider update plan` | `read` | `none` | [provider.md](provider.md) | описать замену провайдера одного harness новейшей выпущенной версией по тому же пути; ничего не меняет |
| `ai-stp provider update apply` | `apply` | `plan_digest` | [provider.md](provider.md) | выполнить ровно ту замену провайдера, которую описал план |
| `ai-stp provider reinstall plan` | `read` | `none` | [provider.md](provider.md) | описать переустановку одной точной версии провайдера по тому же пути; ничего не меняет |
| `ai-stp provider reinstall apply` | `apply` | `plan_digest` | [provider.md](provider.md) | выполнить ровно ту переустановку провайдера, которую описал план |
| `ai-stp provider forget` | `apply` | `none` | [provider.md](provider.md) | сбросить записанный выбор провайдера, чтобы снова решали конфигурация и discovery |
| `ai-stp provider fetch` | `apply` | `none` | [provider.md](provider.md) | загрузить аттестованного провайдера OpenNetwork и привязать закрытый манифест релиза |
| `ai-stp provider network` | `read` | `none` | [provider.md](provider.md) | сообщить наблюдаемую сетевую изоляцию protocol-v2 на этой машине |
| `ai-stp provider trust` | `read` | `none` | [provider.md](provider.md) | сообщить закреплённую политику доверия провайдера и проверить один релиз по ней |
| `ai-stp select session` | `read` | `none` | [select.md](select.md) | открытые proposal для проекта и harness и выбранная версия |
| `ai-stp skill install` | `apply` | `none` | [skill.md](skill.md) | установить канонический Agent Skill в указанное назначение |
| `ai-stp skill remove` | `apply` | `none` | [skill.md](skill.md) | удалить Agent Skill, который эта установка поместила в назначение |
| `ai-stp skill status` | `read` | `none` | [skill.md](skill.md) | сообщить, какой Agent Skill в назначении и кому он принадлежит |
| `ai-stp toolchain harness-capabilities` | `read` | `none` | [toolchain.md](toolchain.md) | по harness и kind: что продукт читает нативно, что этот билд умеет проецировать, и почему любой gap — gap; не утверждение, что компонент активен |
| `ai-stp toolchain harnesses` | `read` | `none` | [toolchain.md](toolchain.md) | сообщить о каждом поддерживаемом harness и есть ли он на этой машине |
| `ai-stp toolchain profile` | `read` | `none` | [toolchain.md](toolchain.md) | показать управляемый профиль toolchain, как он разрешается на этой машине |
| `ai-stp version` | `read` | `none` | [observe.md](observe.md) | сообщить о запущенном билде и версиях контрактов, на которых он говорит |

!!! note
    Если `help --agent` называет команду, которой нет в таблице, установленный CLI новее этой страницы: следуйте CLI.
