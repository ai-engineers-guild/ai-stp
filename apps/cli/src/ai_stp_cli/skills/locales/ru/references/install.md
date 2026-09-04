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
