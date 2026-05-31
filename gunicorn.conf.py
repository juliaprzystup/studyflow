# Konfiguracja serwera produkcyjnego Gunicorn dla aplikacji StudyFlow.
# Uruchomienie: gunicorn -c gunicorn.conf.py wsgi:app

# Nasluchiwanie lokalnie - ruch z internetu kieruje do nas Nginx (reverse proxy).
bind = "127.0.0.1:8000"

# 2 procesy robocze - wystarczajace dla dema; przy 2 GB RAM nie obciazy serwera.
workers = 2
threads = 2

# Przetwarzanie NLP (spaCy / sumy) bywa wolniejsze - dluzszy timeout zapobiega
# zabijaniu workera przy wiekszych plikach PDF.
timeout = 120

# Wczytaj aplikacje (i model spaCy) raz w procesie glownym przed forkiem workerow.
# Oszczedza pamiec i przyspiesza start.
preload_app = True

# Logi na stdout/stderr - przechwytuje je systemd (journalctl).
accesslog = "-"
errorlog = "-"
loglevel = "info"
