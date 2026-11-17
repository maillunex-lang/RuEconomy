# Production Catalog 1.0 — контракт рецепта

450 фиксированных рецептов в RECIPES.json и RECIPES.csv. Все поля целочисленны, бренды не меняют BOM.
Состав: recipe_id, output_goods_id, process_variant, enterprise_id, line_type, technology_level, inputs, outputs, waste_mass_g, cycle_game_minutes, electricity_wh, labor_minutes, setup_game_minutes, quality_floor.
Стандартная и ресурсосберегающая фиксированные карты на один и тот же класс модели. Возможны несколько производственных линий на предприятие, распределение мощности и переналадка.
Коэффициенты — проектные, не отраслевые нормативы; см. QA.md.
