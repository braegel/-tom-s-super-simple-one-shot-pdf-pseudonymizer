"""
PDF Processor – Read text from PDFs and redact identified entities.
Uses PyMuPDF (fitz) for all PDF operations.

Key improvements:
- Uses fitz redaction annotations so the underlying text is truly removed
  (not merely covered by a shape that could be lifted).
- Sorts entities longest-first to avoid partial matches inside longer ones.
- Appends a summary page listing all variable assignments.
"""

import fitz  # PyMuPDF
from typing import Dict, Tuple, List
import os


# Turquoise colour for redaction boxes  (R, G, B  0-1 float)
TURQUOISE = (0.0, 0.808, 0.820)
TURQUOISE_DARK = (0.0, 0.545, 0.545)
WHITE = (1, 1, 1)

# Category labels for the summary page
CATEGORY_LABELS = {
    "VORNAME": "Vorname",
    "NACHNAME": "Nachname",
    "STRASSE": "Straße",
    "HAUSNUMMER": "Hausnummer",
    "STADT": "Stadt / Ort",
    "PLZ": "Postleitzahl",
    "LAND": "Land",
    "KONTONUMMER": "Kontonummer / IBAN",
    "EMAIL": "E-Mail-Adresse",
    "TELEFON": "Telefonnummer",
    "KRYPTO_ADRESSE": "Krypto-Adresse",
    "UNTERNEHMEN": "Unternehmen",
    "GRUNDSTUECK": "Grundstück",
    "GEBURTSDATUM": "Geburtsdatum",
    "SOZIALVERSICHERUNG": "Sozialversicherungsnummer",
    "STEUERNUMMER": "Steuernummer",
    "AUSWEISNUMMER": "Ausweisnummer",
}


def extract_text(pdf_path: str) -> str:
    """Extract the full plain text from a PDF. Requires the PDF to have embedded text."""
    doc = fitz.open(pdf_path)
    pages_text: List[str] = []
    for page in doc:
        pages_text.append(page.get_text("text"))
    doc.close()
    full = "\n".join(pages_text)
    if not full.strip():
        raise ValueError(
            "Das PDF enthält keinen erkennbaren Text. "
            "Bitte stellen Sie sicher, dass das PDF Texterkennung (OCR) hat."
        )
    return full


def _add_redaction(page, rect: fitz.Rect, label: str):
    """Add a redaction annotation that fills *rect* with turquoise and shows *label*."""
    # Calculate font size that fits the box
    box_w = rect.width
    box_h = rect.height
    font_size = min(box_h * 0.82, 11)
    if font_size < 4.5:
        font_size = 4.5

    # Shrink font if the label is too wide
    text_w = fitz.get_text_length(label, fontname="helv", fontsize=font_size)
    while text_w > box_w - 2 and font_size > 4:
        font_size -= 0.5
        text_w = fitz.get_text_length(label, fontname="helv", fontsize=font_size)

    page.add_redact_annot(
        rect,
        text=label,
        fontname="helv",
        fontsize=font_size,
        align=fitz.TEXT_ALIGN_CENTER,
        fill=TURQUOISE,
        text_color=WHITE,
    )


def redact_pdf(
    pdf_path: str,
    output_path: str,
    entity_map: Dict[str, Tuple[str, str]],
    progress_callback=None,
) -> str:
    """
    Create a redacted copy of *pdf_path* at *output_path*.

    For every occurrence of an entity key the text is permanently redacted
    (underlying text removed) and replaced with a turquoise box showing the
    assigned variable label.

    *entity_map*: {original_text: (variable_id, category)}

    Returns the output path.
    """
    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    # Sort entities by length descending so longer matches are processed first
    sorted_entities = sorted(entity_map.keys(), key=len, reverse=True)

    for page_idx, page in enumerate(doc):
        if progress_callback:
            progress_callback(int((page_idx / total_pages) * 100))

        for entity_text in sorted_entities:
            var_id, _category = entity_map[entity_text]

            # Search for all occurrences on this page
            text_instances = page.search_for(entity_text)

            for inst in text_instances:
                _add_redaction(page, inst, var_id)

        # Apply all redactions for this page at once (removes underlying text)
        page.apply_redactions()

    # -- Append summary page listing all variable assignments --
    _append_summary_page(doc, entity_map)

    if progress_callback:
        progress_callback(100)

    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    return output_path


def _append_summary_page(doc: fitz.Document, entity_map: Dict[str, Tuple[str, str]]):
    """Append a page at the end of *doc* listing all variable → category mappings."""
    # A4 page size
    page_w, page_h = 595.28, 841.89
    page = doc.new_page(width=page_w, height=page_h)

    margin = 50
    y = margin

    # Title
    page.insert_text(
        fitz.Point(margin, y + 20),
        "Anonymisierungs-Verzeichnis",
        fontname="helv",
        fontsize=18,
        color=TURQUOISE_DARK,
    )
    y += 45

    # Subtitle
    page.insert_text(
        fitz.Point(margin, y + 12),
        "Zuordnung der verwendeten Variablen zu Kategorien",
        fontname="helv",
        fontsize=10,
        color=(0.4, 0.4, 0.4),
    )
    y += 30

    # Horizontal rule
    shape = page.new_shape()
    shape.draw_line(fitz.Point(margin, y), fitz.Point(page_w - margin, y))
    shape.finish(color=TURQUOISE, width=1.5)
    shape.commit()
    y += 15

    # Table header
    col_var = margin
    col_cat = margin + 80
    col_note = margin + 240

    page.insert_text(fitz.Point(col_var, y + 10), "Variable", fontname="helv", fontsize=9, color=TURQUOISE_DARK)
    page.insert_text(fitz.Point(col_cat, y + 10), "Kategorie", fontname="helv", fontsize=9, color=TURQUOISE_DARK)
    page.insert_text(fitz.Point(col_note, y + 10), "Hinweis", fontname="helv", fontsize=9, color=TURQUOISE_DARK)
    y += 20

    # Sorted by variable name
    entries = sorted(entity_map.items(), key=lambda x: x[1][0])

    for original_text, (var_id, category) in entries:
        if y > page_h - margin - 20:
            # New page if we run out of space
            page = doc.new_page(width=page_w, height=page_h)
            y = margin

        cat_label = CATEGORY_LABELS.get(category, category)

        # Draw a small turquoise chip for the variable
        var_w = fitz.get_text_length(var_id, fontname="helv", fontsize=9) + 8
        chip_rect = fitz.Rect(col_var, y, col_var + var_w, y + 14)
        shape = page.new_shape()
        shape.draw_rect(chip_rect)
        shape.finish(color=TURQUOISE_DARK, fill=TURQUOISE, width=0.3)
        shape.commit()
        page.insert_text(
            fitz.Point(col_var + 4, y + 10),
            var_id,
            fontname="helv",
            fontsize=9,
            color=WHITE,
        )

        # Category
        page.insert_text(
            fitz.Point(col_cat, y + 10),
            cat_label,
            fontname="helv",
            fontsize=9,
            color=(0.2, 0.2, 0.2),
        )

        # Hint: show how many characters the original had (no cleartext!)
        hint = f"{len(original_text)} Zeichen"
        page.insert_text(
            fitz.Point(col_note, y + 10),
            hint,
            fontname="helv",
            fontsize=8,
            color=(0.5, 0.5, 0.5),
        )

        y += 20

    # Footer
    y = page_h - margin
    page.insert_text(
        fitz.Point(margin, y),
        "Erstellt mit PDF Anonymizer",
        fontname="helv",
        fontsize=8,
        color=(0.6, 0.6, 0.6),
    )


def get_page_count(pdf_path: str) -> int:
    """Return the number of pages in a PDF."""
    doc = fitz.open(pdf_path)
    count = len(doc)
    doc.close()
    return count
