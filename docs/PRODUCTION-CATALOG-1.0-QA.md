# Production Catalog 1.0-draft-2 — итог QA

**Структурная проверка: PASS.** JSON каноничен, CSV и GOODS.md синхронизированы.

- 300 SKU, 450 фиксированных рецептов, 45 предприятий. Все 10 категориальных квот сохранены.
- Все ссылки существуют, входные количества положительные целые, граф ацикличен.
- Все 233 производимых товара имеют рецепты; остальные 67 имеют предприятие-источник.
- Баланс масс: масса входа = масса выхода + потери + учтённые побочные потоки. Физическая достоверность норм не подтверждена.
- Нет неиспользуемых промежуточных товаров по классификации конечного спроса. Готовые товары могут не входить в рецепты, поскольку продаются потребителю.
- Техническая вода RAW-025 используется, оба вида воды имеют поставщика ENT-045.
- Поголовье AGRI-024/025/026 переименовано в мясное сырьё, единица g сохранена; old_unit удалено.
- Сталь и полимеры перенесены в BUILD-013/014, кровля и плитка в OTHER-009/010 с миграцией всех рецептурных ссылок.
- Поддоны OTHER-008 резервируются для перевозки, а не исчезают на единицу готовой продукции.

## Открытые оговорки
- Rye flour replaces spaghetti SKU FOOD-035; user approval required for irreversible SKU renaming in an existing game
- ENT-025 is split into licensed facilities under one enterprise type, not three separate enterprise IDs
- ENT-045 combines utilities and commercial property to retain 45 types
- Dairy whey and skim milk are modeled as noncommercial co-products without SKU
- Pallets are reserved as reusable logistics assets, not physically consumed
- Raw sugar from beet is represented inside packaged sugar recipe, without separate sugar refinery SKU
- Recipe coefficients remain hypothetical and not physically calibrated
- Economy Balancing 1.0 scenarios based on old draft are stale and must be recalculated

**Не готово к промышленному или игровому продакшену без калибровки.**
