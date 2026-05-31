import nltk
from nltk.corpus import stopwords
from nltk.tokenize import sent_tokenize, word_tokenize
import fitz  # PyMuPDF
import docx
import re

from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.text_rank import TextRankSummarizer

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')


# ── Bramka jakości zdań ───────────────────────────────────────────────────────
# Wzorce wskazujące na śmieciowe linie (listy, pseudokod)
_LIST_MARKER = re.compile(
    r'^\s*(?:\d+[\.\):]|[a-zA-ZĄĆĘŁŃÓŚŹŻąćęłńóśźż][\.\):]|[•\-\*\–])\s'
)
_CODE_SIGNAL = re.compile(
    r'(?:def |class |import |return |if |else:|elif |for |while |print\(|>>>|#\s|\w+\s*=\s*\w+\()'
)


def is_good_sentence(text: str, min_chars: int = 40) -> bool:
    """
    Zwraca True tylko dla pełnych zdań prozą.
    Odrzuca: nagłówki, elementy list, pseudokod, zbyt krótkie fragmenty.
    """
    t = text.strip()
    if len(t) < min_chars:
        return False
    if _LIST_MARKER.match(t):
        return False
    if _CODE_SIGNAL.search(t):
        return False
    # Pełne zdanie musi kończyć się interpunkcją
    if not re.search(r'[.!?]\s*$', t):
        return False
    # Krótki tekst z dużym udziałem wielkich liter → prawdopodobnie nagłówek
    words = t.split()
    if len(words) <= 8:
        cap_ratio = sum(1 for w in words if w and w[0].isupper()) / len(words)
        if cap_ratio > 0.6:
            return False
    return True
# ─────────────────────────────────────────────────────────────────────────────


def extract_text_from_pdf(file_path):
    """Odczytuje PDF zachowując bloki tekstu i akapity."""
    text = ""
    try:
        doc = fitz.open(file_path)
        for page in doc:
            text += page.get_text("text") + "\n\n"
        doc.close()
    except Exception as e:
        print(f"Błąd podczas czytania PDF (PyMuPDF): {e}")
    return text


def extract_text_from_docx(file_path):
    text = ""
    try:
        doc = docx.Document(file_path)
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text += paragraph.text.strip() + "\n\n"
    except Exception as e:
        print(f"Błąd podczas czytania DOCX: {e}")
    return text


def extract_text_from_txt(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Błąd podczas czytania TXT: {e}")
    return ""


def clean_text(text):
    """
    Czyści tekst:
    - normalizuje spacje,
    - usuwa znaczniki list i numeracji z początków linii,
    - naprawia sklejone nagłówki (brak kropki przed wielką literą).
    """
    text = re.sub(r'[ \t]+', ' ', text)
    # Usuń znaczniki list/numeracji (• 1. a) itp.) z początku linii
    text = re.sub(r'(?m)^[ \t]*(?:\d+[\.\):]|[a-z][\.\):]|[•\-\*\–])\s+', '', text)
    # Jeśli nowa linia zaczyna się wielką literą, a poprzednia nie ma kropki → dodaj
    text = re.sub(r'([^\.\!\?\:\;])\n+([A-ZĄĆĘŁŃÓŚŹŻ])', r'\1.\n\n\2', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def generate_summary(text, num_sentences=7):
    """
    Generuje streszczenie algorytmem TextRank.
    Przed przekazaniem tekstu do algorytmu odfiltrowuje nagłówki,
    listy i pseudokod, żeby nie zaburzały wag.
    """
    if not text or not text.strip():
        return "Brak tekstu do przetworzenia."

    cleaned = clean_text(text)
    all_sents = sent_tokenize(cleaned)

    # Przekaż do TextRank tylko zdania spełniające kryteria jakości
    good_sents = [s for s in all_sents if is_good_sentence(s)]

    if not good_sents:
        return cleaned  # Fallback: zwróć oczyszczony oryginał

    if len(good_sents) <= num_sentences:
        result = "Najważniejsze informacje z tekstu:\n\n"
        for s in good_sents:
            result += f"• {s.strip()}\n"
        return result

    filtered_text = " ".join(good_sents)

    try:
        parser = PlaintextParser.from_string(filtered_text, Tokenizer("polish"))
        summarizer = TextRankSummarizer()
        summary_sentences = summarizer(parser.document, num_sentences)

        result = "Najważniejsze informacje z tekstu:\n\n"
        for sentence in summary_sentences:
            result += f"• {str(sentence).strip()}\n"
        return result

    except Exception as e:
        print(f"Błąd w TextRank: {e}")
        return generate_summary_simple(filtered_text, num_sentences)


def generate_summary_simple(text, num_sentences=5):
    """Prosty fallback: pierwsze N dobrych zdań."""
    sentences = sent_tokenize(clean_text(text))
    good = [s for s in sentences if is_good_sentence(s)]
    if not good:
        good = sentences  # ostateczny fallback

    result = "Wstępne informacje:\n\n"
    for s in good[:num_sentences]:
        result += f"• {s.strip()}\n"
    return result


def extract_key_points(text, num_points=5):
    """
    Wybiera najinformacyjniejsze zdania na podstawie liczby znaczących słów.
    Wstępnie odrzuca nagłówki, listy i pseudokod.
    """
    if not text or not text.strip():
        return []

    text = clean_text(text)
    sentences = sent_tokenize(text)

    try:
        stop_words = set(stopwords.words('polish'))
    except Exception:
        stop_words = set()

    scored = []
    for s in sentences:
        if not is_good_sentence(s):
            continue
        words = word_tokenize(s)
        meaningful = [w.lower() for w in words if w.isalpha() and w.lower() not in stop_words]
        # Zdania zbyt krótkie lub zbyt długie są mniej wartościowe
        if 4 <= len(meaningful) <= 25:
            scored.append((len(meaningful), s))

    scored.sort(key=lambda x: x[0], reverse=True)
    best = [s for _, s in scored[:num_points]]

    if not best:
        best = [s for s in sentences[:num_points] if len(s) > 30]

    return best
