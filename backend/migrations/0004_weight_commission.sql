-- Предполагаемый вес отделён от фактического: прогноз задаётся при создании заказа,
-- факт — после взвешивания. Расхождение подсказывает, предупреждать ли клиента.
-- Комиссия, рассчитанная от предполагаемого веса, НЕ сохраняется в commission_usd —
-- поэтому заказ с одним лишь прогнозом закрыть по-прежнему нельзя.
ALTER TABLE orders ADD COLUMN est_weight_kg NUMERIC(8,3) CHECK (est_weight_kg >= 0);

-- Нефинальный вес по старой модели — это и был прогноз.
UPDATE orders SET est_weight_kg = weight_kg, weight_kg = NULL
WHERE weight_kg IS NOT NULL AND NOT weight_is_final;

ALTER TABLE orders DROP COLUMN weight_is_final;
