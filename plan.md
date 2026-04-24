# Pain Quantifier Agent Plan

## Objective
Build a modular Python application to execute the Pain Quantifier research layer.
The goal is to extract, classify, and store market pain signals from raw data so the business can validate hypotheses and generate signals for ICP scoring.

## Deliverables
- `agent_1_orchestrator.py` — main workflow and monthly orchestration.
- `haiku_prompts.py` — structured Claude Haiku prompt library and category definitions.
- `requirements.txt` — required dependencies.

## Architecture
- Fetch raw data from Apify or SerpAPI.
- Classify each record through Claude Haiku.
- Store results exclusively in the `pain_corpus` Airtable table.
- Do not write to `leads`.
- Use stable deduplication so monthly reruns do not create duplicates.

## Data Schema
Each pain record includes:
- `source`
- `raw text`
- `pain_phrase`
- `category`
- `intensity`
- `company_name_raw`
- `timestamp`
- `dedupe_key`

## Classification Rules
- Allowed categories:
  - `billing_error`
  - `manual_work`
  - `reporting_gap`
  - `identity_resolution`
  - `timing_delay`
- Irrelevant or failed classifications should still be stored as `category: failed`.
- Intensity must be an integer between 1 and 5.

## Validation Logic
- Compute whether 30%+ of Club Automation records are flagged as `manual_work` or integration-related.
- The validation function returns:
  - `club_automation_count`
  - `flagged_count`
  - `flagged_ratio`
  - `threshold_met`

## Integration
- Designed for monthly triggering via Make.com webhook.
- Supports batch payload input via `--payload-file`.
- Supports direct fetch from Apify or SerpAPI via environment configuration.
- Uploads processed records to Airtable using the Airtable API.

## Idempotency
- Uses a SHA-256 dedupe key based on:
  - `source`
  - normalized `raw text`
  - `timestamp`
  - normalized `company_name_raw`
- Existing Airtable rows are updated instead of duplicated.

## Environment Variables
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL` (optional, default `claude-2.1`)
- `AIRTABLE_API_KEY`
- `AIRTABLE_BASE_ID`
- `AIRTABLE_TABLE_NAME` (optional, default `pain_corpus`)
- `APIFY_API_KEY` and `APIFY_DATASET_ID` (for Apify fetch)
- `SERPAPI_API_KEY` and `SERPAPI_SEARCH_QUERY` (for SerpAPI fetch)

## Notes
- The code is intentionally isolated to only write to the `pain_corpus` table.
- The implementation is designed to be updated continuously and maintain idempotent monthly execution.
