-- Vision capability, per model (spec 009 [D7]).
--
-- Why a column and not a derived fact: whether a model accepts image input is not inferable from its id,
-- its provider or its wire. It is a property of the model, and it is the one property that decides whether
-- an attached image is DELIVERED or silently replaced by a sentence saying it could not be. The app
-- measured this to be wrong in both directions — llama-4-maverick was declared blind and can see;
-- gpt-oss-120b accepts no image at all — so a guess is not available.
--
-- The default is `false`, and that is the safe direction: refusing or labelling an image is recoverable,
-- sending one to a model that cannot take it is not.
ALTER TABLE llm.llm_model
    ADD COLUMN IF NOT EXISTS sees_images boolean NOT NULL DEFAULT false;

-- The two models measured to see, in the workspace this migration was written against. Applied by id so a
-- re-run is a no-op, and only when the row exists: a migration must not invent catalogue rows.
UPDATE llm.llm_model
   SET sees_images = true
 WHERE id IN (
    'databricks/databricks-llama-4-maverick',
    'databricks/databricks-gemma-3-12b',
    'databricks/databricks-claude-sonnet-4-5',
    'anthropic/claude-sonnet-4-5',
    'openai/gpt-4.1',
    'openai/gpt-4.1-mini',
    'google_vertex/google/gemini-3.5-flash',
    'google_vertex/google/gemini-3.8-flash',
    'google_vertex/google/gemini-3.8-pro'
 );
