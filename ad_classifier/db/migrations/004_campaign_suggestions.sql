ALTER TABLE marketing_entities RENAME COLUMN campaign_signals_json TO campaign_suggestions_json;

UPDATE marketing_entities
SET campaign_suggestions_json = '[]'
WHERE campaign_suggestions_json IS NOT NULL
  AND json_valid(campaign_suggestions_json)
  AND json_type(campaign_suggestions_json) = 'object';
