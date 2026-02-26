"""
AI Engine – Multi-provider abstraction for PII entity detection.
Supports OpenAI (ChatGPT), Anthropic (Claude) and Google (Gemini).

Handles large texts by splitting into chunks that fit within AI token limits
and merging results, ensuring consistent variable assignment across chunks.
"""

import json
import re
from typing import Dict, List, Tuple, Optional

# Approximate character limit per chunk.  Most models handle ~120k chars
# comfortably; we stay well below to leave room for the system prompt and
# response.  Overlapping avoids splitting an entity at a boundary.
CHUNK_SIZE = 60_000
CHUNK_OVERLAP = 2_000

# ---------------------------------------------------------------------------
# Prompt that instructs the AI to find all PII entities
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Du bist ein Experte für Datenanonymisierung. Deine Aufgabe ist es, in einem gegebenen Text alle personenbezogenen und identifizierenden Daten zu finden.

Du musst folgende Kategorien erkennen – in ALLEN Sprachen, die im Text vorkommen:

1. VORNAME – Vornamen von Personen
2. NACHNAME – Nachnamen von Personen
3. STRASSE – Straßennamen
4. HAUSNUMMER – Hausnummern
5. STADT – Städte / Orte
6. PLZ – Postleitzahlen
7. LAND – Länder
8. KONTONUMMER – Kontonummern, IBANs, BICs
9. EMAIL – E-Mail-Adressen
10. TELEFON – Telefonnummern
11. KRYPTO_ADRESSE – Bitcoin-Adressen oder andere Kryptowährungs-Adressen
12. UNTERNEHMEN – Firmennamen (GmbH, AG, Ltd, Inc, SE, OG, KG, etc.)
13. GRUNDSTUECK – Grundstücksbezeichnungen, Parzellen, Flurnummern, Grundbucheinträge
14. GEBURTSDATUM – Geburtsdaten von Personen
15. SOZIALVERSICHERUNG – Sozialversicherungsnummern
16. STEUERNUMMER – Steuernummern, UID-Nummern
17. AUSWEISNUMMER – Reisepass-, Personalausweis-, Führerscheinnummern
18. GELDBETRAG – Geldbeträge und Währungsangaben (z.B. $100, 50€, 1.000 USD, 5.000,00 EUR, £200, CHF 500, ¥10000)
19. UNTERSCHRIFT – Handschriftlich wirkende Texte, Unterschriften, Paraphen, Kürzel, Initialen

WICHTIGE REGELN:
- Gleiche Entitäten (z.B. derselbe Vorname "Max" an mehreren Stellen) sollen als EINE Entität behandelt werden.
- Gib NUR die Entitäten zurück, die tatsächlich im Text vorkommen.
- Gib die Entitäten EXAKT so zurück, wie sie im Text stehen (gleiche Schreibweise, Groß-/Kleinschreibung).
- Erkenne Entitäten in ALLEN Sprachen (Deutsch, Englisch, Französisch, etc.).
- Ignoriere allgemeine Begriffe die keine konkreten PII sind (z.B. "Straße" allein ohne Namen).
- Achte BESONDERS auf Geldbeträge und Währungen: $, €, £, ¥, USD, EUR, GBP, CHF, JPY, BTC und alle anderen Währungen. Auch Beträge wie "1.000,00" oder "100.00" neben einem Währungszeichen erkennen.
- NICHT anonymisieren: Rechtliche Normen, Paragraphen (§), Gesetzesverweise (z.B. "§ 123 BGB", "Art. 5 DSGVO", "§ 823 Abs. 1 BGB"), Standards und Normen (ISO, DIN, EN, ÖNORM), Rechtsformzusätze in Normverweisen. Diese sind KEINE personenbezogenen Daten.
- Erkenne handschriftlich wirkende Texte, Unterschriften, Paraphen, Initialen und Kürzel als UNTERSCHRIFT. Auch unleserliche oder kurze Zeichenfolgen, die wie handschriftliche Notizen wirken.

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt im folgenden Format, ohne weitere Erklärung:

{
  "entities": [
    {"text": "Max", "category": "VORNAME"},
    {"text": "Mustermann", "category": "NACHNAME"},
    {"text": "Musterstraße", "category": "STRASSE"},
    {"text": "42", "category": "HAUSNUMMER"},
    {"text": "Berlin", "category": "STADT"},
    {"text": "10115", "category": "PLZ"},
    {"text": "DE89370400440532013000", "category": "KONTONUMMER"},
    {"text": "max@example.com", "category": "EMAIL"},
    {"text": "Muster GmbH", "category": "UNTERNEHMEN"},
    {"text": "5.000,00 EUR", "category": "GELDBETRAG"},
    {"text": "J.M.", "category": "UNTERSCHRIFT"}
  ]
}"""

USER_PROMPT_TEMPLATE = """Analysiere den folgenden Text und finde ALLE personenbezogenen und identifizierenden Daten.

TEXT:
\"\"\"
{text}
\"\"\"

Antworte NUR mit dem JSON-Objekt."""


def _parse_ai_response(response_text: str) -> List[Dict[str, str]]:
    """Parse the JSON response from the AI, handling markdown fences."""
    text = response_text.strip()
    # Strip markdown code fences if present
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    data = json.loads(text)
    return data.get("entities", [])


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def detect_entities_openai(api_key: str, text: str, model: str = "gpt-4o") -> List[Dict[str, str]]:
    """Use OpenAI / ChatGPT to detect PII entities."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(text=text)},
        ],
        temperature=0.0,
        max_tokens=4096,
    )
    return _parse_ai_response(response.choices[0].message.content)


def detect_entities_anthropic(api_key: str, text: str, model: str = "claude-sonnet-4-20250514") -> List[Dict[str, str]]:
    """Use Anthropic / Claude to detect PII entities."""
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(text=text)},
        ],
    )
    return _parse_ai_response(message.content[0].text)


def detect_entities_gemini(api_key: str, text: str, model: str = "gemini-2.0-flash") -> List[Dict[str, str]]:
    """Use Google Gemini to detect PII entities."""
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    gen_model = genai.GenerativeModel(model)
    prompt = SYSTEM_PROMPT + "\n\n" + USER_PROMPT_TEMPLATE.format(text=text)
    response = gen_model.generate_content(prompt)
    return _parse_ai_response(response.text)


# ---------------------------------------------------------------------------
# Unified interface
# ---------------------------------------------------------------------------

PROVIDERS = {
    "openai": detect_entities_openai,
    "anthropic": detect_entities_anthropic,
    "gemini": detect_entities_gemini,
}


def _split_text(text: str) -> List[str]:
    """Split *text* into overlapping chunks that fit within AI token limits."""
    if len(text) <= CHUNK_SIZE:
        return [text]
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start = end - CHUNK_OVERLAP
    return chunks


def _deduplicate_entities(all_entities: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Remove duplicate entities (same text + category)."""
    seen = set()
    unique: List[Dict[str, str]] = []
    for ent in all_entities:
        key = (ent["text"], ent["category"])
        if key not in seen:
            seen.add(key)
            unique.append(ent)
    return unique


def detect_entities(
    provider: str,
    api_key: str,
    text: str,
    progress_callback=None,
) -> List[Dict[str, str]]:
    """
    Detect PII entities using the chosen AI provider.

    Automatically splits large texts into chunks and merges results.
    *progress_callback(int)* is called with 0-100 percentage.

    Returns a list of dicts: [{"text": "...", "category": "..."}, ...]
    """
    func = PROVIDERS.get(provider)
    if func is None:
        raise ValueError(f"Unknown provider: {provider}")

    chunks = _split_text(text)
    all_entities: List[Dict[str, str]] = []

    for i, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback(int((i / len(chunks)) * 100))
        chunk_entities = func(api_key, chunk)
        all_entities.extend(chunk_entities)

    if progress_callback:
        progress_callback(100)

    return _deduplicate_entities(all_entities)


def assign_variables(entities: List[Dict[str, str]]) -> Dict[str, Tuple[str, str]]:
    """
    Assign anonymisation variables to detected entities.

    Returns a dict mapping original text -> (variable_id, category).
    Same text always gets the same variable.  Variables use hexadecimal
    counting starting at A (i.e. A, B, C, D, E, F, 10, 11, …).
    Signature/handwriting entities are redacted without a variable label.
    """
    mapping: Dict[str, Tuple[str, str]] = {}
    counter = 0xA  # Start at hex A
    for ent in entities:
        txt = ent["text"]
        if txt not in mapping:
            if ent["category"] == "UNTERSCHRIFT":
                mapping[txt] = ("", ent["category"])
            else:
                var_id = f"{counter:X}"
                mapping[txt] = (var_id, ent["category"])
                counter += 1
    return mapping
