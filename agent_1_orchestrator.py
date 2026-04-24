"""Agent 1: Pain Quantifier orchestration script."""

import argparse
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

try:
    from anthropic import Client, HUMAN_PROMPT, AI_PROMPT
except ImportError:  # pragma: no cover
    Client = None
    HUMAN_PROMPT = "\nHuman: "
    AI_PROMPT = "\nAssistant: "

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

import haiku_prompts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

AIRTABLE_API_URL = "https://api.airtable.com/v0"

FIELD_SOURCE = "source"
FIELD_RAW_TEXT = "raw text"
FIELD_PAIN_PHRASE = "pain_phrase"
FIELD_CATEGORY = "category"
FIELD_INTENSITY = "intensity"
FIELD_COMPANY_NAME_RAW = "company_name_raw"
FIELD_TIMESTAMP = "timestamp"
FIELD_DEDUPE_KEY = "dedupe_key"

ALLOWED_CATEGORIES = set(haiku_prompts.CATEGORIES) | {"failed"}


@dataclass
class PainSignal:
    source: str
    raw_text: str
    company_name_raw: str
    timestamp: str
    category: str = "failed"
    intensity: int = 0
    pain_phrase: str = ""
    dedupe_key: str = ""
    extra: Dict[str, Any] = None

    def to_airtable_record(self) -> Dict[str, Any]:
        return {
            FIELD_SOURCE: self.source,
            FIELD_RAW_TEXT: self.raw_text,
            FIELD_PAIN_PHRASE: self.pain_phrase,
            FIELD_CATEGORY: self.category,
            FIELD_INTENSITY: self.intensity,
            FIELD_COMPANY_NAME_RAW: self.company_name_raw,
            FIELD_TIMESTAMP: self.timestamp,
            FIELD_DEDUPE_KEY: self.dedupe_key,
        }


def normalize_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip().lower()
    return normalized


def compute_dedupe_key(source: str, raw_text: str, timestamp: str, company_name_raw: str) -> str:
    payload = f"{source}|{normalize_text(raw_text)}|{timestamp}|{normalize_text(company_name_raw)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def safe_json_load(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    json_text = None
    try:
        json_text = text.strip()
        if not json_text.startswith("{"):
            match = re.search(r"\{.*\}", text, re.S)
            if match:
                json_text = match.group(0)
        return json.loads(json_text)
    except json.JSONDecodeError:
        return None


def parse_classification_response(response_text: str) -> Dict[str, Any]:
    parsed = safe_json_load(response_text)
    if not parsed:
        return {"pain_phrase": "", "category": "failed", "intensity": 0}

    category = parsed.get("category", "failed")
    if category not in ALLOWED_CATEGORIES:
        category = "failed"

    intensity = parsed.get("intensity", 0)
    try:
        intensity = int(intensity)
    except (TypeError, ValueError):
        intensity = 0

    if category == "failed":
        intensity = 0
    elif intensity < 1 or intensity > 5:
        intensity = max(1, min(5, intensity))

    return {
        "pain_phrase": parsed.get("pain_phrase", "").strip(),
        "category": category,
        "intensity": intensity,
    }


class PainClassifier:
    def __init__(self, api_key: str, model: str = "claude-2.1"):
        if Client is None:
            raise RuntimeError(
                "Anthropic client library is not installed. Install 'anthropic' in your environment."
            )
        self.client = Client(api_key=api_key)
        self.model = model

    def classify(self, signal: PainSignal) -> PainSignal:
        prompt = haiku_prompts.build_classification_prompt(
            raw_text=signal.raw_text,
            company_name_raw=signal.company_name_raw,
            source=signal.source,
            timestamp=signal.timestamp,
        )
        full_prompt = f"{HUMAN_PROMPT}{prompt}{AI_PROMPT}"

        response = self.client.completions.create(
            model=self.model,
            prompt=full_prompt,
            max_tokens_to_sample=300,
            temperature=0.0,
        )

        text = getattr(response, "completion", None) or response.get("completion") or str(response)
        classification = parse_classification_response(text)

        signal.pain_phrase = classification["pain_phrase"]
        signal.category = classification["category"]
        signal.intensity = classification["intensity"]
        return signal


class AirtablePainCorpusClient:
    def __init__(self, api_key: str, base_id: str, table_name: str):
        self.api_key = api_key
        self.base_id = base_id
        self.table_name = table_name
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })

    def _table_url(self) -> str:
        quoted_table = requests.utils.quote(self.table_name, safe="")
        return f"{AIRTABLE_API_URL}/{self.base_id}/{quoted_table}"

    def _escape_formula_value(self, value: str) -> str:
        return value.replace("'", "\\'")

    def find_record_by_dedupe(self, dedupe_key: str) -> Optional[Dict[str, Any]]:
        formula = f"{{{FIELD_DEDUPE_KEY}}} = '{self._escape_formula_value(dedupe_key)}'"
        params = {"filterByFormula": formula, "pageSize": 1}
        url = self._table_url()
        response = self.session.get(url, params=params)
        response.raise_for_status()
        result = response.json()
        records = result.get("records", [])
        return records[0] if records else None

    def upsert_record(self, signal: PainSignal) -> Dict[str, Any]:
        record_payload = {"fields": signal.to_airtable_record()}
        existing = self.find_record_by_dedupe(signal.dedupe_key)
        if existing:
            record_id = existing["id"]
            url = f"{self._table_url()}/{record_id}"
            response = self.session.patch(url, json=record_payload)
        else:
            url = self._table_url()
            response = self.session.post(url, json=record_payload)

        response.raise_for_status()
        return response.json()


def fetch_apify_batch() -> List[Dict[str, Any]]:
    api_key = os.getenv("APIFY_API_KEY")
    dataset_id = os.getenv("APIFY_DATASET_ID")
    if not api_key or not dataset_id:
        raise ValueError("APIFY_API_KEY and APIFY_DATASET_ID must be set to fetch data from Apify.")

    url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?format=json"
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def fetch_serpapi_batch() -> List[Dict[str, Any]]:
    api_key = os.getenv("SERPAPI_API_KEY")
    query = os.getenv("SERPAPI_SEARCH_QUERY")
    if not api_key or not query:
        raise ValueError("SERPAPI_API_KEY and SERPAPI_SEARCH_QUERY must be set to fetch data from SerpAPI.")

    url = "https://serpapi.com/search.json"
    params = {"engine": "google", "q": query, "api_key": api_key}
    response = requests.get(url, params=params)
    response.raise_for_status()
    result = response.json()
    raw_results = []

    for item in result.get("organic_results", []) + result.get("top_ads", []) + result.get("news_results", []):
        raw_text = item.get("snippet") or item.get("title") or ""
        raw_results.append(
            {
                "source": "serpapi",
                "raw_text": raw_text,
                "company_name_raw": item.get("title", "") if item.get("title") else "",
                "timestamp": item.get("date", ""),
            }
        )
    return raw_results


def load_records_from_payload(payload: Any) -> List[PainSignal]:
    if not isinstance(payload, list):
        raise ValueError("Payload must be a list of records.")

    signals: List[PainSignal] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "unknown"))
        raw_text = str(item.get("raw_text") or item.get("raw text") or "")
        company_name_raw = str(item.get("company_name_raw") or item.get("company_name") or "")
        timestamp = str(item.get("timestamp") or item.get("time") or "")
        signal = PainSignal(
            source=source,
            raw_text=raw_text,
            company_name_raw=company_name_raw,
            timestamp=timestamp,
        )
        signal.dedupe_key = compute_dedupe_key(
            source=signal.source,
            raw_text=signal.raw_text,
            timestamp=signal.timestamp,
            company_name_raw=signal.company_name_raw,
        )
        signals.append(signal)
    return signals


def validate_club_automation_signals(signals: List[PainSignal]) -> Dict[str, Any]:
    club_signals = [
        s for s in signals if "club automation" in normalize_text(s.company_name_raw)
    ]
    if not club_signals:
        return {
            "club_automation_count": 0,
            "flagged_count": 0,
            "flagged_ratio": 0.0,
            "threshold_met": False,
        }

    flagged = [
        s
        for s in club_signals
        if s.category == "manual_work"
        or s.category == "integration_missing"
        or re.search(r"integration|sync|api|connect|connector|pipeline", s.raw_text, re.I)
        or re.search(r"integration|sync|api|connect|connector|pipeline", s.pain_phrase, re.I)
    ]

    ratio = len(flagged) / len(club_signals)
    return {
        "club_automation_count": len(club_signals),
        "flagged_count": len(flagged),
        "flagged_ratio": round(ratio, 3),
        "threshold_met": ratio >= 0.3,
    }


def process_signals(
    signals: List[PainSignal],
    classifier: PainClassifier,
    airtable_client: AirtablePainCorpusClient,
    dry_run: bool = False,
) -> List[PainSignal]:
    processed: List[PainSignal] = []
    for signal in signals:
        try:
            logger.info("Classifying signal from source=%s company=%s", signal.source, signal.company_name_raw)
            signal = classifier.classify(signal)
        except Exception as exc:
            logger.exception("Classification failed for signal: %s", exc)
            signal.category = "failed"
            signal.intensity = 0
            signal.pain_phrase = signal.pain_phrase or ""

        if not signal.dedupe_key:
            signal.dedupe_key = compute_dedupe_key(
                source=signal.source,
                raw_text=signal.raw_text,
                timestamp=signal.timestamp,
                company_name_raw=signal.company_name_raw,
            )

        if dry_run:
            processed.append(signal)
            continue

        try:
            airtable_client.upsert_record(signal)
            processed.append(signal)
        except Exception as exc:
            logger.exception("Failed to save pain signal to Airtable: %s", exc)
            signal.category = "failed"
            signal.intensity = 0
            processed.append(signal)

    return processed


def load_json_file(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pain Quantifier orchestration for monthly signal extraction.")
    parser.add_argument("--payload-file", help="JSON file containing a list of raw signals to process.")
    parser.add_argument("--source", choices=["apify", "serpapi"], default="apify", help="Fetch source when no payload file is provided.")
    parser.add_argument("--dry-run", action="store_true", help="Run classification without saving to Airtable.")
    parser.add_argument("--print-validation", action="store_true", help="Print validation results for Club Automation signals.")
    args = parser.parse_args()

    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    airtable_api_key = os.getenv("AIRTABLE_API_KEY")
    airtable_base_id = os.getenv("AIRTABLE_BASE_ID")
    airtable_table_name = os.getenv("AIRTABLE_TABLE_NAME", "pain_corpus")

    if not anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required for classification.")
    if not airtable_api_key or not airtable_base_id:
        raise RuntimeError("AIRTABLE_API_KEY and AIRTABLE_BASE_ID are required for Airtable writes.")

    if args.payload_file:
        payload = load_json_file(args.payload_file)
        signals = load_records_from_payload(payload)
    elif args.source == "apify":
        raw_records = fetch_apify_batch()
        signals = load_records_from_payload(raw_records)
    else:
        raw_records = fetch_serpapi_batch()
        signals = load_records_from_payload(raw_records)

    classifier = PainClassifier(api_key=anthropic_api_key, model=os.getenv("ANTHROPIC_MODEL", "claude-2.1"))
    airtable_client = AirtablePainCorpusClient(
        api_key=airtable_api_key,
        base_id=airtable_base_id,
        table_name=airtable_table_name,
    )

    processed_signals = process_signals(signals, classifier, airtable_client, dry_run=args.dry_run)

    if args.print_validation:
        validation = validate_club_automation_signals(processed_signals)
        logger.info("Club Automation validation: %s", validation)
        print(json.dumps(validation, indent=2))

    logger.info("Processed %d signals.", len(processed_signals))


if __name__ == "__main__":
    main()
