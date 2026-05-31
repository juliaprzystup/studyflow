# Routing Refactor Note

## Aktualny stan

Katalog `routes/` nie jest obecnie wykorzystywany przez aplikację.
Wszystkie trasy są zdefiniowane bezpośrednio w `app.py`, razem z inicjalizacją:

- `app = Flask(__name__)`
- `db = SQLAlchemy(app)`
- `login_manager`
- importem modeli przez `init_db(db)`

W kodzie nie ma rejestracji własnych `Blueprint`, importów z `routes/` ani wywołań `app.register_blueprint(...)`.

## Obecne grupy tras w `app.py`

### 1. Auth

- `/` -> `index`
- `/login` -> `login`
- `/register` -> `register`
- `/logout` -> `logout`

### 2. Dashboard i postepy

- `/dashboard` -> `dashboard`
- `/statistics` -> `statistics`
- `/progress` -> `progress`

### 3. Dokumenty

- `/upload` -> `upload_file`
- `/notes` -> `notes_list`
- `/note/<int:note_id>` -> `view_note`
- `/delete_note/<int:note_id>` -> `delete_note`

### 4. Quizy

- `/generate_quiz/<int:note_id>` -> `generate_quiz`
- `/quiz/<int:quiz_id>` -> `take_quiz`
- `/quizzes` -> `quizzes_list`
- `/delete_quiz/<int:quiz_id>` -> `delete_quiz`

### 5. Fiszki

- `/generate_flashcards/<int:note_id>` -> `generate_flashcards_route`
- `/flashcards` -> `flashcards_list`
- `/delete_flashcard/<int:flashcard_id>` -> `delete_flashcard`
- `/update_flashcard/<int:card_id>` -> `update_flashcard`
- `/study_flashcards` -> `study_flashcards`
- `/study_flashcards/<int:document_id>` -> `study_flashcards_deck`

### 6. Funkcje pomocnicze powiazane z routingiem

- `load_user`
- `log_study_activity`
- `allowed_file`
- `apply_sm2`

## Dlaczego nie wykonano teraz refaktoru do Blueprint

Przy aktualnych ograniczeniach projektowych refaktor do `Blueprint` nie jest bezpieczny, bo:

1. Aplikacja korzysta z nieprefiksowanych nazw endpointow, np. `url_for('login')`, `url_for('dashboard')`, `url_for('flashcards_list')`.
2. `Flask-Login` ma ustawione `login_manager.login_view = 'login'`.
3. Po przeniesieniu tras do `Blueprint` Flask automatycznie prefiksuje endpointy nazwa blueprintu, np. `auth.login`, `quizes.quizzes_list`.
4. Zachowanie starych nazw endpointow bez przepisywania wszystkich `url_for(...)`, przekierowan i konfiguracji logowania wymagaloby obejsc lub duplikacji, co zwieksza ryzyko regresji.
5. `app.py` laczy routing z konfiguracja aplikacji, obiektami globalnymi i helperami bazodanowymi, wiec czesciowe wydzielenie tras bez wprowadzenia warstwy inicjalizacyjnej byloby bardziej kruche niz pomocne.

W trakcie oceny sprawdzono tez eksperymentalnie zachowanie Flask `Blueprint` i obecna wersja Flask nie pozwala na pusty `name`, wiec nie da sie w prosty sposob zachowac starych endpointow przez "bezprefixowy" blueprint.

## Jak rozdzielic trasy w przyszlosci

Najbezpieczniejsza sciezka na przyszlosc:

1. Wydzielic inicjalizacje aplikacji do schematu app factory, np. `create_app()`.
2. Przeniesc wspolne obiekty (`db`, `login_manager`) do osobnych modulow lub rozszerzen.
3. Wprowadzic `Blueprint` etapami.
4. Zaktualizowac wszystkie wywolania `url_for(...)` i `login_manager.login_view` do nazw blueprintowych.
5. Dopiero po tym przenosic kolejne grupy tras z `app.py`.

## Ktore grupy najlepiej nadaja sie do wydzielenia

### Najlepszy pierwszy kandydat: `auth`

Powod:

- logicznie spojna grupa,
- niewiele tras,
- najmniej zaleznosci domenowych,
- brak skomplikowanych zapytan SQL poza `User`.

Uwaga:
zanim zostanie wydzielona, trzeba zaakceptowac zmiane nazw endpointow na `auth.login`, `auth.register`, `auth.logout` albo przeprowadzic kontrolowana aktualizacje wszystkich odwolan.

### Drugi dobry kandydat: `dashboard`

Powod:

- trasy sa tematycznie spojne (`dashboard`, `statistics`, `progress`),
- nie zmieniaja URL-i zasobow domenowych,
- latwo je utrzymywac jako osobny modul widokow uzytkownika.

### Bardziej ryzykowne na pozniejszy etap

- `documents`
- `quizzes`
- `flashcards`

Te grupy sa silniej powiazane z modelami, helperami (`allowed_file`, `apply_sm2`, `log_study_activity`) i wzajemnymi przekierowaniami miedzy ekranami.

## Rekomendacja

Na obecnym etapie lepiej pozostawic routing w `app.py`.
Minimalny, bezpieczny kolejny krok to przygotowanie architektury pod przyszly podzial, ale bez przenoszenia dzialajacych endpointow do `Blueprint` w tej iteracji.
