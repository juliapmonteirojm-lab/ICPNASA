# ICPNASA

A lightweight project for the Pain Quantifier research layer, designed to extract market pain signals and store them in Airtable.

## Current Implementation
- `agent_1_orchestrator.py`: Main orchestration script for monthly batch processing.
- `haiku_prompts.py`: Claude Haiku prompt definitions and classification metadata.
- `requirements.txt`: Python dependencies.
- `plan.md`: Implementation plan and architecture summary.

## Usage
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set environment variables:
   - `ANTHROPIC_API_KEY`
   - `AIRTABLE_API_KEY`
   - `AIRTABLE_BASE_ID`
   - `AIRTABLE_TABLE_NAME` (optional, defaults to `pain_corpus`)
   - `APIFY_API_KEY` and `APIFY_DATASET_ID` or `SERPAPI_API_KEY` and `SERPAPI_SEARCH_QUERY`
3. Run the orchestrator:
   ```bash
   python agent_1_orchestrator.py --source apify --dry-run --print-validation
   ```

## Notes
- The script is intentionally written to only persist data to the `pain_corpus` table.
- Idempotency is handled by a stable dedupe key so repeated monthly executions do not create duplicate entries.
- Failed or irrelevant classifications are still stored with `category: failed`.

## Continuous Updates
This repository is actively maintained, and the implementation is expected to be kept up to date as integration details evolve.
