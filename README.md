# Экономическая MMO «Россия»

Самостоятельный проект, не смешивать с LunexEconom или другими играми.

## Новому ИИ: читать в таком порядке
1. docs/GDD-1.0-1.2.md — утверждённые решения.
2. docs/PRODUCTION-CATALOG-1.0-COMPLETE.md — обзор и ограничения.
3. docs/PRODUCTION-CATALOG-1.0-QA.md — проверенные факты и недоработки.
4. docs/PRODUCTION-CATALOG-1.0-GOODS.json — канонические 300 SKU.
5. docs/PRODUCTION-CATALOG-1.0-RECIPES.json — канонические 450 проектных рецептов.
6. docs/PRODUCTION-CATALOG-1.0-EQUIPMENT.json — 45 предприятий и 70 типов линий.
7. docs/PRODUCTION-CATALOG-1.0-MODELS-BRANDS.md — коммерческие модели и бренды игроков.
8. docs/PRODUCTION-CATALOG-1.0-SUPPLY-CHAINS.md — источники, импорт, склады и логистика.
9. docs/PRODUCTION-CATALOG-1.0-PRODUCTION-LINES.md — производство и затраты.
10. docs/PRODUCTION-CATALOG-1.0-PLAN.md — калибровка перед реализацией.

Каталог сохраняется как канон JSON. С этапа M0 разработан локальный Python/SQLite-симулятор, но промышленная экономическая калибровка и сетевой MMO-сервер ещё не реализованы.

## Economy Balancing 1.1 / Economic Core M0
- docs/ECONOMY-BALANCING-1.1.md — сценарный пересчёт 450 рецептов, условные параметры 45 предприятий.
- docs/ECONOMIC-CORE-M0-REPORT.md — реализация ядра и ограничения.
- core/economy.py — автономный Python + SQLite, без внешнего сервера.
- core/balance.py — пересчёт модельных сценариев.
- tests/ — 17 проверок.
- Запуск: python3 -m unittest discover -s tests -v

## Economic Core M1–M3

- `core/market.py`: локальный биржевой рынок, резервы, городские квоты импорта и бюджетный спрос.
- `core/ai.py`: 100 детерминированных ИИ-компаний для 10 городов, в том числе начальное производство муки и розница.
- `simulate.py`: 30-дневный офлайн-интеграционный прогон, без запуска фонового сервиса.
- `docs/ECONOMIC-CORE-M1-REPORT.md`, `docs/ECONOMIC-CORE-M2-REPORT.md`, `docs/ECONOMIC-CORE-M3-REPORT.md`: отчёты этапов.
- `docs/ECONOMIC-M3-SIMULATION.json`: воспроизводимые результаты seed=42.
- `docs/ECONOMIC-M1-M3-QA.json`: контрольный QA и хэши канонических JSON.

Проверки: `python3 -m unittest discover -s tests -q`

Офлайн-прогон: `python3 simulate.py --days 30 --seed 42`

**Ограничение:** на M3 моделируются две мукомольные производственные цепочки, а не все отрасли. Нет внешнего API, серверного развёртывания или Android APK.

## Android + живой сервер 0.2 (10 этапов)

- Отчёт о 10 этапах: `docs/TEN-STAGES-BETA-0.2.md`.
- Проверка сборки, тестов и данных: `docs/TEN-STAGES-BETA-0.2-QA.json`.
- APK: https://rikagro.ru/russia-mmo/android-0.2.apk
- Сервер: https://rikagro.ru/russia-mmo/health
- Код серверной интеграции: `server.py`, `core/beta_features.py`, `core/world.py`.
- Android: `android/Main.gd` / Godot 4.7.2, landscape, текстовые игровые окна.
- Тесты: `python3 -m unittest discover -s tests -q`; E2E: `python3 tests/beta2_smoke.py`.
- Срок игры: 7 реальных дней = 1 игровой год.
- Это ограниченная текстовая бета: все товары и рецепты доступны движку, но ещё нет всей глубины MMO, филиальных складов и 2.5D.
