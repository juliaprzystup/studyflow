import spacy
import re
import random

try:
    nlp = spacy.load("pl_core_news_sm")
except Exception as e:
    print("UWAGA: Nie udało się załadować modelu 'pl_core_news_sm':", e)
    nlp = None


# ── Bramka jakości zdań ───────────────────────────────────────────────────────

_LIST_MARKER = re.compile(
    r'^\s*(?:\d+[.\):]|[a-zA-ZĄĆĘŁŃÓŚŹŻąćęłńóśźż][.\):]|[•\-*\–])\s'
)

_CODE_SIGNAL = re.compile(
    r'(?:def |class |import |return |if |else:|elif |for |while |print\(|>>>|#\s'
    r'|\w+\s*=\s*\w+\('
    r'|\w+\s*=\s*\d+'
    r'|dla każdego|zwróć |algorytm )',
    re.IGNORECASE
)

_DEF_PATTERN = re.compile(
    r'([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:(?:\s|-)[A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż]+){0,4})'
    r'\s+(?:to|jest|oznacza|definiuje się jako)\s+'
    r'(.+?)\.'
)

BAD_TERMS = {
    'było', 'był', 'była', 'jest', 'to', 'to jest', 'jest to', 'to było',
    'miał', 'miała', 'ma', 'mieć', 'odbyło się', 'stało się', 'wydarzyło się'
}


def is_good_sentence(text: str, min_chars: int = 28) -> bool:
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


def is_valid_definition_term(term: str) -> bool:
    term_clean = term.lower().strip('.,!?()').strip()

    bad_starts = (
        'było', 'był', 'była', 'jest', 'to', 'w', 'z', 'na', 'o',
        'ten', 'ta', 'te', 'który', 'która', 'które'
    )

    if term_clean.startswith(bad_starts):
        return False

    words = term_clean.split()
    if not (1 <= len(words) <= 5):
        return False

    if any(c.isdigit() for c in term_clean):
        return False

    return True


def validate_question(question: dict) -> bool:
    q_text = question['question'].strip()

    if len(q_text) < 15:
        return False

    if q_text.count('___') > 1:
        return False

    if '___' not in q_text and 'Czym jest' not in q_text and 'Co oznacza' not in q_text:
        return False

    bad_starts = ['było?', 'był?', 'była?', 'jest?']
    if any(q_text.lower().startswith(bad) for bad in bad_starts):
        return False

    words_without_gap = q_text.replace('___', '').split()
    if len(words_without_gap) < 3:
        return False

    return True


def generate_smart_quiz(text, num_questions=5):
    """Główna funkcja generująca quiz z różnych typów pytań."""
    if not nlp or not text.strip():
        return []

    text = text.replace('•', '').replace('Najważniejsze informacje z tekstu:', '')
    text = re.sub(r'\s+', ' ', text)

    doc = nlp(text)
    all_questions = []

    all_questions.extend(extract_definition_questions(doc))
    all_questions.extend(extract_number_questions(doc))
    all_questions.extend(extract_date_questions(doc))
    all_questions.extend(extract_person_questions(doc))
    all_questions.extend(extract_location_questions(doc))

    seen = set()
    unique_questions = []
    for q in all_questions:
        q_hash = q['question'][:60]
        if q_hash not in seen:
            seen.add(q_hash)
            unique_questions.append(q)

    random.shuffle(unique_questions)
    return unique_questions[:num_questions]


def extract_date_questions(doc):
    questions = []

    for sent in doc.sents:
        sent_text = sent.text.strip()

        if not is_good_sentence(sent_text):
            continue

        m = re.search(r'\b(1[0-9]|20)\d{2}\b', sent_text)
        if not m:
            continue

        date = m.group(0)
        q_text = sent_text.replace(date, "___", 1)

        if not validate_question({'question': q_text, 'answers': ['test']}):
            continue

        year = int(date)
        wrong = list({
            str(year + random.choice([3, 5, 7])),
            str(year - random.choice([2, 5, 10])),
            str(year + random.choice([12, 15, 20]))
        } - {date})

        while len(wrong) < 3:
            candidate = str(year + random.randint(-15, 15))
            if candidate != date and candidate not in wrong:
                wrong.append(candidate)

        answers = [date] + wrong[:3]
        random.shuffle(answers)

        questions.append({
            'question': f"Uzupełnij brakującą datę w zdaniu:\n{q_text.strip()}",
            'answers': answers,
            'correct': answers.index(date),
            'correct_answer': date
        })

    return questions


def extract_person_questions(doc):
    questions = []

    persons = list(dict.fromkeys(
        ent.text.strip() for ent in doc.ents if ent.label_ in ("PER", "PERSON")
    ))

    if len(persons) < 4:
        return questions

    for sent in doc.sents:
        sent_text = sent.text.strip()

        if not is_good_sentence(sent_text):
            continue

        for person in persons:
            if person in sent_text:
                q_text = sent_text.replace(person, "___", 1)

                if not validate_question({'question': q_text, 'answers': ['test']}):
                    continue

                wrong = [p for p in persons if p != person]
                wrong = list(dict.fromkeys(wrong))

                if len(wrong) < 3:
                    continue

                random.shuffle(wrong)
                answers = [person] + wrong[:3]
                random.shuffle(answers)

                questions.append({
                    'question': f"O kim mowa w poniższym zdaniu?\n{q_text}",
                    'answers': answers,
                    'correct': answers.index(person),
                    'correct_answer': person
                })
                break

    return questions


def extract_location_questions(doc):
    questions = []

    locations = list(dict.fromkeys(
        ent.text.strip() for ent in doc.ents if ent.label_ in ("LOC", "GPE")
    ))

    if len(locations) < 4:
        return questions

    for sent in doc.sents:
        sent_text = sent.text.strip()

        if not is_good_sentence(sent_text):
            continue

        for location in locations:
            if location in sent_text:
                q_text = sent_text.replace(location, "___", 1)

                if not validate_question({'question': q_text, 'answers': ['test']}):
                    continue

                wrong = [loc for loc in locations if loc != location]
                wrong = list(dict.fromkeys(wrong))

                if len(wrong) < 3:
                    continue

                random.shuffle(wrong)
                answers = [location] + wrong[:3]
                random.shuffle(answers)

                questions.append({
                    'question': f"Gdzie miało miejsce to wydarzenie?\n{q_text}",
                    'answers': answers,
                    'correct': answers.index(location),
                    'correct_answer': location
                })
                break

    return questions


def extract_number_questions(doc):
    """
    Generuje pytania o liczby.
    Pomija lata oraz próbuje odróżnić numerację list od prawdziwej treści.
    """
    questions = []

    for sent in doc.sents:
        sent_text = sent.text.strip()

        if not is_good_sentence(sent_text):
            continue

        if re.search(r'\b(1[0-9]|20)\d{2}\b', sent_text):
            continue

        numbers = re.findall(r'\b\d+(?:[.,]\d+)?(?:\s*%|°C|km|m|kg|g)?\b', sent_text)
        if not numbers:
            continue

        number = numbers[0]
        raw_val = re.sub(r'[%°CkmgKG ]', '', number)

        try:
            num_float = float(raw_val.replace(',', '.'))
        except ValueError:
            continue

        unit_match = re.search(r'[%°CkmgKG]+', number)

        # Odrzuć numerację typu "1.", "2)", "3:" na początku zdania
        if re.match(r'^\s*\d+[.):]', sent_text):
            continue

        first_token_match = re.match(r'^\s*(\S+)', sent_text)
        first_token = first_token_match.group(1) if first_token_match else ''

        if num_float <= 10 and not unit_match and first_token.rstrip('.,):') == number.strip():
            # Bardzo ostrożny filtr dla małych liczb na początku zdania
            # aby nie łapać numeracji list
            continue

        q_text = sent_text.replace(number, "___", 1)

        if not validate_question({'question': q_text, 'answers': ['test']}):
            continue

        try:
            if '.' in raw_val or ',' in raw_val:
                base = float(raw_val.replace(',', '.'))
                wrong = [str(round(base * f, 1)) for f in (0.5, 1.5, 2.0)]
            else:
                base = int(raw_val)
                wrong = [
                    str(base + random.randint(2, 5)),
                    str(base + random.randint(10, 20))
                ]
                if base > 2:
                    wrong.append(str(base - random.randint(1, base - 1)))
                else:
                    wrong.append(str(base + random.randint(6, 9)))
        except Exception:
            wrong = ["10", "20", "50"]

        unit = unit_match.group(0) if unit_match else ""
        formatted_wrong = [f"{w}{unit}" for w in wrong]

        answers = [number] + formatted_wrong[:3]
        random.shuffle(answers)

        questions.append({
            'question': f"Uzupełnij brakującą wartość:\n{q_text}",
            'answers': answers,
            'correct': answers.index(number),
            'correct_answer': number
        })

    return questions


def extract_definition_questions(doc):
    """
    Generuje pytania definicyjne.
    Pomija encje nazwane typu PERSON/PER,
    żeby uniknąć pytań w stylu „Czym jest Ada Lovelace?”.
    """
    questions = []

    good_sentences = [
        s.text.strip() for s in doc.sents if is_good_sentence(s.text.strip())
    ]

    # Zbiór osób rozpoznanych przez spaCy
    blocked_terms = set()
    for ent in doc.ents:
        if ent.label_ in {"PER", "PERSON"}:
            blocked_terms.add(ent.text.strip().lower())

    definition_items = []
    for sent_text in good_sentences:
        match = _DEF_PATTERN.search(sent_text)
        if not match:
            continue

        term = match.group(1).strip()
        definition = match.group(2).strip()

        if not is_valid_definition_term(term):
            continue

        # Kluczowa poprawka: pomiń osoby
        if term.lower() in blocked_terms:
            continue

        # Dodatkowe zabezpieczenie dla wariantów nazw
        if any(
            term.lower() in blocked or blocked in term.lower()
            for blocked in blocked_terms
        ):
            continue

        if len(definition) < 10:
            continue

        definition_items.append({
            "term": term,
            "definition": definition,
            "sentence": sent_text
        })

    if not definition_items:
        return questions

    for item in definition_items:
        term = item["term"]
        definition = item["definition"]

        question_text = f'Czym jest **{term}**?'
        if not validate_question({'question': question_text, 'answers': ['test']}):
            continue

        short_def = definition[:100] + ("..." if len(definition) > 100 else "")

        distractor_candidates = []

        # 1. Najpierw inne definicje z tekstu
        for other in definition_items:
            if other["term"] == term:
                continue

            other_def = other["definition"].strip()
            other_short = other_def[:100] + ("..." if len(other_def) > 100 else "")

            if abs(len(other_short) - len(short_def)) > 70:
                continue

            if other_short.lower() != short_def.lower() and other_short not in distractor_candidates:
                distractor_candidates.append(other_short)

        # 2. Jeśli nadal za mało, dobierz z dobrych zdań
        if len(distractor_candidates) < 3:
            for sent_text in good_sentences:
                if sent_text == item["sentence"]:
                    continue

                candidate = sent_text.strip()

                if len(candidate) > 110:
                    continue

                if candidate.count(",") > 2:
                    continue

                if candidate.endswith("."):
                    candidate = candidate[:-1]

                if candidate and candidate not in distractor_candidates and candidate.lower() != short_def.lower():
                    distractor_candidates.append(candidate)

                if len(distractor_candidates) >= 3:
                    break

        # 3. Ostateczny fallback
        fallback_pool = [
            "Proces zachodzący w komórce.",
            "Zjawisko związane z ruchem ciał.",
            "Element budowy organizmu.",
            "Właściwość materii lub układu.",
            "Mechanizm zachodzący w przyrodzie."
        ]

        for fallback in fallback_pool:
            if fallback not in distractor_candidates and fallback.lower() != short_def.lower():
                distractor_candidates.append(fallback)
            if len(distractor_candidates) >= 3:
                break

        answers = [short_def] + distractor_candidates[:3]
        random.shuffle(answers)

        questions.append({
            'question': question_text,
            'answers': answers,
            'correct': answers.index(short_def),
            'correct_answer': short_def
        })

    return questions