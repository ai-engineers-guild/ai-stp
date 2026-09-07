# Install

Намерения: установить, обновить, откатиться.

Берите из machine help: `ai-stp install plan`, `ai-stp install approve`,
`ai-stp install apply`, `ai-stp install cancel`, `ai-stp setup update plan`,
`ai-stp setup update apply`, `ai-stp setup import plan`,
`ai-stp registry acquire`, `ai-stp target status`, `ai-stp target rollback`.

Покажите `required_authorization` из плана. Apply только digest этого плана.
После apply вызовите `ai-stp target status` с тем же провайдером и доверяйте
`pending_authorization`; не выводите готовность из успешного apply и не
повторяйте apply, чтобы закончить вход.

Для сохранения и возврата берите `ai-stp setup preserve plan`,
`ai-stp setup preserved list`, `ai-stp setup preserved show` и
`ai-stp setup restore plan`. Выбирайте ID сохранённого сетапа, не угадывайте
backup-ref. Проверяйте охват и доступность копии. Возврат сначала сохраняет
текущие правки, затем проверяет полное охваченное нативное состояние.
Запись в offline-списке не является свежим измерением провайдера.
