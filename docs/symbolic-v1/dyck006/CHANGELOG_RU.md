# Изменения DYCK006 /0.4.8

- Добавлены role_ast.py, role_checker.py, role_promotion.py и независимый query check.
- Существующие synthesis/contracts/features/learner/service/mcp дополнены additive role mode/scope/query_id.
- Добавлены22 targeted tests,2 transport tests, fixture и настоящий MCP QA runner.
- Прежние regression runners получили opt-in совместимость additive API и resource-busy retry.
- Обновлены README, архитектура, установка, интерфейс, тестирование, release notes,
  JSON/TypeScript types и полная evidence поставка; исходное ТЗ сохранено в docs.
- Численное ядро, Symbolic V1, SP, старый evaluator/checker, workspace и SQLite не менялись.
