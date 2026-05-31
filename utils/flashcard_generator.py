import random
import spacy
import re
import hashlib

try:
    nlp = spacy.load('pl_core_news_sm')
except Exception as e:
    print("UWAGA: Nie udało się załadować modelu 'pl_core_news_sm':", e)
    nlp = None


# ── Bramka jakości zdań (identyczna jak w text_processor) ────────────────────
_LIST_MARKER = re.compile(
    r'^\s*(?:\d+[\.\):]|[a-zA-ZĄĆĘŁŃÓŚŹŻąćęłńóśźż][\.\):]|[•\-\*\–])\s'
)
_CODE_SIGNAL = re.compile(
    r'(?:def |class |import |return |if |else:|elif |for |while |print\(|>>>|#\s|\w+\s*=\s*\w+\()'
)


def is_good_sentence(text: str, min_chars: int = 40) -> bool:
    t = text.strip()
    if len(t) < min_chars:
        return False
    if _LIST_MARKER.match(t):
        return False
    if _CODE_SIGNAL.search(t):
        return False
    if not re.search(r'[.!?]\s*$', t):
        return False
    words = t.split()
    if len(words) <= 8:
        cap_ratio = sum(1 for w in words if w and w[0].isupper()) / len(words)
        if cap_ratio > 0.6:
            return False
    return True
# ─────────────────────────────────────────────────────────────────────────────


# Regex definicji: zatrzymaj się na kropce (nie na przecinku) → pełna odpowiedź
_DEF_PATTERN = re.compile(
    r'([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:(?:\s|-)[A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż]+){0,4})'
    r'\s+(?:to|jest|oznacza|definiuje się jako)\s+'
    r'(.+?)\.'   # <-- tylko kropka, nie przecinek
)

_BAD_TERM_STARTS = (
    'było', 'był', 'była', 'w', 'z', 'na', 'o', 'ten', 'ta', 'te'
)


def clean_text_for_flashcards(text):
    """Czyści tekst przed generowaniem fiszek."""
    text = re.sub(r'[ \t]+', ' ', text)
    # Usuń znaczniki list z początków linii
    text = re.sub(r'(?m)^[ \t]*(?:\d+[\.\):]|[•\-\*\–])\s+', '', text)
    text = re.sub(r'([^\.\!\?\:\;])\n+([A-ZĄĆĘŁŃÓŚŹŻ])', r'\1.\n\n\2', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def generate_flashcards(text, num_cards=10):
    if not nlp or not text.strip():
        return []

    text = clean_text_for_flashcards(text)
    doc = nlp(text)
    all_flashcards = []

    # 1. FISZKI Z DEFINICJAMI (Pojęcie → Pełne wyjaśnienie)
    for sent in doc.sents:
        sent_text = sent.text.strip()
        if not is_good_sentence(sent_text):
            continue

        match = _DEF_PATTERN.search(sent_text)
        if not match:
            continue

        term = match.group(1).strip()
        definition = match.group(2).strip()

        if term.lower().startswith(_BAD_TERM_STARTS):
            continue
        if any(c.isdigit() for c in term):
            continue
        if len(definition) < 10:   # odrzuć ucięte/puste definicje
            continue

        all_flashcards.append({
            'question': f'Czym jest **{term}**?',
            'answer': definition.capitalize() + '.'
        })

    # 2. FISZKI Z DATAMI (Luka w zdaniu)
    for sent in doc.sents:
        sent_text = sent.text.strip()
        if not is_good_sentence(sent_text):
            continue

        m = re.search(r'\b(1[0-9]|20)\d{2}\b', sent_text)
        if m:
            date = m.group(0)
            q_text = sent_text.replace(date, "___", 1)
            # Zdanie po wstawieniu luki musi mieć sensowną długość
            if 30 < len(q_text) < 200:
                all_flashcards.append({
                    'question': f"W którym roku: {q_text}",
                    'answer': date
                })

    # 3. FISZKI O OSOBACH (NER)
    persons = list(dict.fromkeys(
        ent.text.strip() for ent in doc.ents if ent.label_ in ("PER", "PERSON")
    ))

    for sent in doc.sents:
        sent_text = sent.text.strip()
        if not is_good_sentence(sent_text):
            continue
        for person in persons:
            if person in sent_text:
                q_text = sent_text.replace(person, "___", 1)
                all_flashcards.append({
                    'question': f"Kto to jest?\n{q_text}",
                    'answer': person
                })
                break

    # 4. DEDUPLIKACJA I LOSOWANIE
    seen = set()
    unique = []
    for card in all_flashcards:
        q_hash = hashlib.md5(card['question'].encode('utf-8')).hexdigest()
        if q_hash not in seen:
            seen.add(q_hash)
            unique.append(card)

    random.shuffle(unique)
    return unique[:num_cards]
