# Wdrożenie StudyFlow na serwerze (DigitalOcean VPS)

Instrukcja krok po kroku, jak uruchomić aplikację StudyFlow na własnym serwerze
(VPS) DigitalOcean, tak aby działała pod publicznym adresem przez całą dobę.

Stack docelowy: **Ubuntu 24.04 + Gunicorn + Nginx (+ HTTPS przez Certbot)**.

> Wszystkie komendy z linijki zaczynającej się od `#` wykonujesz jako root,
> a z `$` jako użytkownik `studyflow`. Symbol nie jest częścią komendy.

---

## 0. Zanim zaczniesz — kod na GitHub

Serwer pobierze kod z GitHuba. Repozytorium może być **prywatne**.

Na swoim komputerze (PowerShell), w folderze `fiszki_app`:

```powershell
cd ścieżka\do\fiszki_app
git init
git add .
git commit -m "StudyFlow - wersja do wdrozenia"
```

Następnie utwórz repozytorium na GitHub (np. `studyflow`, prywatne) i:

```powershell
git remote add origin https://github.com/TWOJA_NAZWA/studyflow.git
git branch -M main
git push -u origin main
```

> Dzięki plikowi `.gitignore` na GitHub NIE trafią: `.venv/`, baza `*.db`,
> wgrane pliki użytkowników ani sekrety. To prawidłowe i bezpieczne.

---

## 1. Utworzenie serwera (Droplet)

1. Zaloguj się na DigitalOcean (kredyty z **GitHub Student Pack**).
2. **Create → Droplets**.
3. **Region:** Frankfurt (FRA1) — najniższy ping z Polski.
4. **Image:** Ubuntu 24.04 (LTS) x64.
5. **Size:** Basic → Regular → **2 GB RAM / 1 CPU** (ok. 12 $/mc z kredytów, spokojnie pociągnie spaCy).
6. **Authentication:** SSH key (zalecane) lub hasło.
7. **Create Droplet** i zapisz adres **IP** serwera.

---

## 2. Pierwsze logowanie i podstawowa konfiguracja

Z komputera (PowerShell ma wbudowane `ssh`):

```powershell
ssh root@TWOJE_IP
```

Aktualizacja systemu i instalacja pakietów:

```bash
# apt update && apt upgrade -y
# apt install -y python3-venv python3-pip nginx git
```

Utwórz zwykłego użytkownika (nie pracujemy na root):

```bash
# adduser studyflow
# usermod -aG sudo studyflow
# su - studyflow
```

---

## 3. Pobranie kodu i instalacja zależności

Jako użytkownik `studyflow` (powinieneś być w `/home/studyflow`):

```bash
$ git clone https://github.com/TWOJA_NAZWA/studyflow.git fiszki_app
$ cd fiszki_app
$ python3 -m venv .venv
$ source .venv/bin/activate
$ pip install --upgrade pip
$ pip install -r requirements.txt
$ pip install gunicorn
```

> Instalacja potrwa kilka minut — pobiera m.in. spaCy i model `pl_core_news_sm`
> (jest w `requirements.txt`).

Pobierz dane NLTK używane przez moduł przetwarzania tekstu:

```bash
$ python -m nltk.downloader punkt stopwords
```

Szybki test, że aplikacja w ogóle startuje (Ctrl+C aby przerwać):

```bash
$ gunicorn -c gunicorn.conf.py wsgi:app
```

Jeśli nie ma błędów (widać `Listening at: http://127.0.0.1:8000`) — działa. Przerwij (Ctrl+C).

---

## 4. Uruchomienie jako usługa (systemd)

Dzięki temu aplikacja wstaje sama po restarcie serwera i działa w tle.

Wygeneruj bezpieczny klucz sesji:

```bash
$ python3 -c "import secrets; print(secrets.token_hex(32))"
```

Skopiuj wynik. Następnie (jako root) utwórz plik usługi:

```bash
$ sudo cp deploy/studyflow.service /etc/systemd/system/studyflow.service
$ sudo nano /etc/systemd/system/studyflow.service
```

W pliku **wklej wygenerowany klucz** w miejsce `ZMIEN_TEN_KLUCZ_...`
i upewnij się, że ścieżki to `/home/studyflow/fiszki_app`. Zapisz (Ctrl+O, Enter, Ctrl+X).

Uruchom usługę:

```bash
$ sudo systemctl daemon-reload
$ sudo systemctl enable studyflow
$ sudo systemctl start studyflow
$ sudo systemctl status studyflow
```

Status powinien być **active (running)**. Logi podejrzysz przez:

```bash
$ sudo journalctl -u studyflow -f
```

---

## 5. Nginx (reverse proxy)

```bash
$ sudo cp deploy/nginx-studyflow.conf /etc/nginx/sites-available/studyflow
$ sudo nano /etc/nginx/sites-available/studyflow
```

Wpisz adres **IP serwera** (lub domenę) w miejsce `TWOJ_ADRES_IP_LUB_DOMENA`. Zapisz.

```bash
$ sudo ln -s /etc/nginx/sites-available/studyflow /etc/nginx/sites-enabled/
$ sudo rm -f /etc/nginx/sites-enabled/default
$ sudo nginx -t          # test konfiguracji
$ sudo systemctl restart nginx
```

Teraz wejdź w przeglądarce na `http://TWOJE_IP` — powinna pojawić się aplikacja.

---

## 6. Firewall

```bash
$ sudo ufw allow OpenSSH
$ sudo ufw allow 'Nginx Full'
$ sudo ufw enable
```

---

## 7. (Opcjonalnie, ale robi wrażenie) Domena + HTTPS

Jeśli masz darmową domenę (np. z Student Pack — Namecheap) albo dowolną własną:

1. W panelu domeny ustaw rekord **A** wskazujący na IP serwera.
2. W pliku Nginx wpisz domenę w `server_name`, zrestartuj Nginx.
3. Zainstaluj certyfikat (Let's Encrypt):

```bash
$ sudo apt install -y certbot python3-certbot-nginx
$ sudo certbot --nginx -d twoja-domena.pl
```

Certbot sam doda HTTPS i przekierowanie z http → https. Od teraz adres to
`https://twoja-domena.pl` (zielona kłódka — świetnie wygląda na obronie).

---

## 8. Aktualizacja aplikacji po zmianach w kodzie

Gdy zmienisz coś lokalnie i wypchniesz na GitHub:

```bash
$ cd /home/studyflow/fiszki_app
$ git pull
$ source .venv/bin/activate
$ pip install -r requirements.txt   # tylko jeśli zmieniły się zależności
$ sudo systemctl restart studyflow
```

---

## 9. Konto administratora

Panel administratora wymaga konta z flagą `is_admin=True`. Najprościej:

1. Zarejestruj zwykłe konto w aplikacji (przez `/register`).
2. Na serwerze nadaj mu uprawnienia administratora skryptem `grant_admin.py`:

```bash
$ cd /home/studyflow/fiszki_app
$ source .venv/bin/activate
$ python grant_admin.py twoj@email.pl
```

Powinno pojawić się: `Nadano uprawnienia administratora kontu: twoj@email.pl`.

---

## 10. Ważne na koniec (koszty)

- Po obronie **wyłącz / usuń Droplet** (Destroy), żeby nie zużywać kredytów.
- W panelu DigitalOcean ustaw **Billing alert**, by dostać maila przy zużyciu kredytu.

---

## Najczęstsze problemy

| Objaw | Przyczyna / rozwiązanie |
|-------|--------------------------|
| `502 Bad Gateway` | Usługa `studyflow` nie działa → `sudo systemctl status studyflow`, sprawdź `journalctl -u studyflow`. |
| `413 Request Entity Too Large` | Plik > limitu Nginx → zwiększ `client_max_body_size` (jest już 20M). |
| Błąd `punkt`/`stopwords` | Brak danych NLTK → `python -m nltk.downloader punkt stopwords`. |
| Aplikacja mielenie / brak RAM | Za mały Droplet → wybierz 2 GB; w `gunicorn.conf.py` zmniejsz `workers` do 1. |
| Sesje wylogowują po restarcie | Brak stałego `SECRET_KEY` w pliku usługi systemd. |
