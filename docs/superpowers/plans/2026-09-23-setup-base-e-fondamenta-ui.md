# Setup base app e fondamenta UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mettere in piedi lo scheletro applicativo di Karma Inventory Manager: configurazione, connessione al database, autenticazione con ruoli, layout responsive — senza ancora la logica di dominio (Prodotti/Fatture).

**Architecture:** App NiceGUI (multi-pagina classica con `@ui.page`) montata su FastAPI, dati letti/scritti tramite SQLModel su PostgreSQL, schema gestito da Alembic. Autenticazione basata su sessione firmata (`app.storage.user`) con un middleware Starlette che protegge tutte le pagine tranne `/login`.

**Tech Stack:** Python 3.12, NiceGUI, FastAPI, SQLModel, PostgreSQL (psycopg 3), Alembic, pydantic-settings, argon2-cffi, uv, ruff.

**Spec:** `docs/superpowers/specs/2026-09-23-setup-base-e-fondamenta-ui-design.md`

## Global Constraints

- Solo PostgreSQL in sviluppo: nessun fallback SQLite.
- Navigazione con pagine multiple classiche (`@ui.page`): niente `ui.sub_pages`.
- Stile con NiceGUI puro (tema Quasar + Tailwind): niente frontend React/Vue separato.
- Password hashate con Argon2 (`argon2-cffi`): mai bcrypt/passlib, mai testo in chiaro.
- Test automatici per l'infrastruttura di auth sono fuori scope in questa iterazione (vedi spec, sezione "Fuori scope"): la verifica è manuale + `ruff check`/`ruff format`.
- Nessuna logica di dominio (CRUD Prodotti/Fatture) in questo piano: le relative pagine restano placeholder "in costruzione".
- `alembic upgrade head` scrive sul database Postgres condiviso configurato in `.env`: da eseguire solo dopo conferma esplicita dell'utente (vedi README, sezione 7 — "database condiviso").

---

## Come leggere questo piano

Ogni task produce un pezzetto dell'app che puoi far girare e verificare da solo, prima di passare al successivo. L'ordine segue le dipendenze reali: prima le fondamenta (configurazione, database), poi i modelli, poi l'autenticazione, poi l'interfaccia. Ogni task spiega **cosa scrivi**, **cosa fa** e **come si collega** al resto tramite il blocco "Interfaces".

---

### Task 1: Dipendenza Argon2 e chiave segreta di sessione

**Cosa fa:** Aggiunge la libreria per l'hashing delle password e genera la chiave usata da NiceGUI per firmare/cifrare i cookie di sessione (`app.storage.user`). Senza questa chiave, nessuna pagina protetta può ricordare "chi sei loggato" tra una richiesta e l'altra.

**Files:**
- Modify: `pyproject.toml` (via `uv add`, non a mano)
- Modify: `.env` (non tracciato da git — verificalo con `git status`)

**Interfaces:**
- Produce: la dipendenza Python `argon2` importabile come `from argon2 import PasswordHasher` (usata nel Task 6).
- Produce: la variabile d'ambiente `SECRET_KEY`, letta dal Task 2 (`app/config.py`).

- [ ] **Step 1: Installa argon2-cffi**

```bash
uv add argon2-cffi
```

- [ ] **Step 2: Genera una chiave segreta**

```bash
uv run python -c "import secrets; print(secrets.token_hex(32))"
```

Copia l'output (una stringa esadecimale lunga).

- [ ] **Step 3: Aggiungi la chiave a `.env`**

Apri `.env` e aggiungi una riga (sostituendo `INCOLLA_QUI_LA_CHIAVE` con il valore generato):

```dotenv
SECRET_KEY=INCOLLA_QUI_LA_CHIAVE
```

**Importante:** questa chiave deve essere diversa dalla password del database, e non va mai condivisa in chat/commit. Se un giorno cambia, tutti gli utenti loggati vengono disconnessi (è previsto, non un bug).

- [ ] **Step 4: Verifica che `.env` non sia tracciato da git**

```bash
git status
```

`.env` non deve comparire tra i file modificati/da committare.

- [ ] **Step 5: Commit della sola dipendenza**

```bash
git add pyproject.toml uv.lock
git commit -m "Aggiunge argon2-cffi per l'hashing delle password

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Configurazione (`app/config.py`)

**Cosa fa:** Legge le variabili d'ambiente (da `.env` in sviluppo) e le valida con pydantic. Se manca `DATABASE_URL` o `SECRET_KEY`, l'app si rifiuta di partire subito con un errore leggibile, invece di fallire più avanti in modo criptico. Ogni altro modulo dell'app importa `settings` da qui invece di leggere `os.environ` direttamente — un solo punto di verità per la configurazione.

**Files:**
- Create: `app/config.py`

**Interfaces:**
- Consuma: variabili d'ambiente `DATABASE_URL`, `SECRET_KEY` (da `.env`, Task 1).
- Produce: `settings: Settings` — istanza con attributi `settings.database_url: str`, `settings.secret_key: str`, `settings.app_name: str`. Usata da: `app/database.py` (Task 3), `migrations/env.py` (Task 5), `app/main.py` (Task 11).

- [ ] **Step 1: Scrivi `app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    secret_key: str
    app_name: str = "Karma Inventory Manager"


settings = Settings()
```

Nota su come funziona: `pydantic-settings` associa automaticamente `database_url` alla variabile d'ambiente `DATABASE_URL` (case-insensitive), e la legge dal file indicato in `env_file` se non è già impostata nell'ambiente di sistema. `app_name` ha un default, quindi è opzionale nel `.env`.

- [ ] **Step 2: Verifica che la configurazione si carichi correttamente**

```bash
uv run python -c "from app.config import settings; print(settings.app_name, bool(settings.database_url), bool(settings.secret_key))"
```

Output atteso: `Karma Inventory Manager True True`. Se vedi un errore di validazione, manca una variabile in `.env` (probabilmente `SECRET_KEY`, se hai saltato il Task 1).

- [ ] **Step 3: Commit**

```bash
git add app/config.py
git commit -m "Aggiunge la configurazione dell'app basata su pydantic-settings

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Connessione al database (`app/database.py`)

**Cosa fa:** Crea l'`engine` SQLAlchemy/SQLModel una sola volta (riutilizzato da tutta l'app) e offre `get_session()` per aprire una sessione di database per singola operazione, chiudendola automaticamente. Non crea tabelle: quello è compito esclusivo di Alembic (Task 5), per evitare che schema "reale" (migrazioni) e schema "implicito" (creato al volo dai modelli) divergano.

**Files:**
- Create: `app/database.py`

**Interfaces:**
- Consuma: `settings.database_url` da `app/config.py` (Task 2).
- Produce: `engine` (oggetto SQLAlchemy `Engine`), usato da `migrations/env.py` (Task 5, indirettamente tramite `settings`) e da `app/scripts/crea_utente.py` (Task 7). Produce anche `get_session() -> Generator[Session, None, None]`, pensato per essere usato dalle pagine/servizi nelle prossime sessioni di sviluppo.

- [ ] **Step 1: Scrivi `app/database.py`**

```python
from collections.abc import Generator

from sqlmodel import Session, create_engine

from app.config import settings

engine = create_engine(settings.database_url)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
```

- [ ] **Step 2: Verifica la connessione reale al database**

```bash
uv run python -c "
from sqlmodel import Session, text
from app.database import engine

with Session(engine) as session:
    print(session.exec(text('SELECT version()')).first())
"
```

Output atteso: una riga con la versione di PostgreSQL. Se vedi `connection refused`/`timeout`, controlla VPN/`DATABASE_URL` (vedi README sezione 6) prima di proseguire — i task successivi dipendono da una connessione funzionante.

- [ ] **Step 3: Commit**

```bash
git add app/database.py
git commit -m "Aggiunge l'engine SQLModel e get_session()

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Modello Utente e ruoli

**Cosa fa:** Definisce la tabella `Utente` (username, password hashata, ruolo, attivo) e l'enum dei ruoli. Aggrega anche tutti i modelli in `app/models/__init__.py`, cosicché un solo `import app.models` (usato da Alembic nel Task 5) registri sia `Prodotto` che `Utente` nel metadata di SQLModel.

**Files:**
- Create: `app/models/utente.py`
- Modify: `app/models/__init__.py` (attualmente vuoto)

**Interfaces:**
- Produce: `RuoloUtente` (enum con valori `"admin"`, `"operatore"`) e `Utente` (SQLModel table: `id`, `username`, `password_hash`, `ruolo`, `attivo`). Usati da: `app/auth.py` (Task 6), `app/scripts/crea_utente.py` (Task 7), `migrations/env.py` (Task 5).

- [ ] **Step 1: Scrivi `app/models/utente.py`**

```python
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class RuoloUtente(str, Enum):
    ADMIN = "admin"
    OPERATORE = "operatore"


class Utente(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    ruolo: RuoloUtente = Field(default=RuoloUtente.OPERATORE)
    attivo: bool = Field(default=True)
```

- [ ] **Step 2: Scrivi `app/models/__init__.py`**

```python
from app.models.prodotto import Prodotto
from app.models.utente import RuoloUtente, Utente

__all__ = ["Prodotto", "RuoloUtente", "Utente"]
```

Questo è l'unico posto dove "tutti i modelli" sono elencati: quando in futuro aggiungerai un nuovo modello (es. `Fattura`), lo importerai anche qui — altrimenti Alembic non lo vedrà nelle autogenerazioni.

- [ ] **Step 3: Verifica che i modelli si importino senza errori**

```bash
uv run python -c "from app.models import Prodotto, RuoloUtente, Utente; print(RuoloUtente.ADMIN.value)"
```

Output atteso: `admin`.

- [ ] **Step 4: Commit**

```bash
git add app/models/utente.py app/models/__init__.py
git commit -m "Aggiunge il modello Utente con ruoli admin/operatore

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Alembic collegato ai modelli + prima migrazione

**Cosa fa:** Finora Alembic non sapeva né come connettersi al database reale (`alembic.ini` ha solo un URL segnaposto) né quali tabelle dovesse gestire (`target_metadata = None`). Questo task collega Alembic a `settings.database_url` e a `SQLModel.metadata`, poi genera la prima migrazione reale (che crea le tabelle `prodotto` e `utente`, dato che finora `migrations/versions/` è vuota).

**Files:**
- Modify: `migrations/env.py`
- Create: `migrations/versions/<hash>_creazione_tabelle_iniziali.py` (generato da Alembic, non scritto a mano)

**Interfaces:**
- Consuma: `settings` (Task 2), `app.models` (Task 4).
- Produce: le tabelle `prodotto` e `utente` nel database Postgres condiviso (dopo l'apply nello Step 5) — da cui dipendono tutti i task successivi che leggono/scrivono utenti.

- [ ] **Step 1: Sostituisci il contenuto di `migrations/env.py`**

```python
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlmodel import SQLModel

from alembic import context

from app import models  # noqa: F401 - importarlo registra le tabelle in SQLModel.metadata
from app.config import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Cosa cambia rispetto a prima: importiamo `app.models` (registra le tabelle), leggiamo l'URL vero da `settings` invece che dal placeholder in `alembic.ini` (`config.set_main_option(...)` lo sovrascrive a runtime), e `target_metadata` ora punta davvero a `SQLModel.metadata` invece di `None`.

- [ ] **Step 2: Verifica lo stato attuale (sola lettura, sempre sicuro)**

```bash
uv run alembic current
uv run alembic history
```

Con `migrations/versions/` vuota, `history` non mostra nulla: è atteso, non hai ancora generato migrazioni.

- [ ] **Step 3: Genera la prima migrazione**

```bash
uv run alembic revision --autogenerate -m "creazione tabelle iniziali"
```

- [ ] **Step 4: Apri e rileggi il file generato in `migrations/versions/`**

Verifica che `upgrade()` crei le tabelle `prodotto` e `utente` con le colonne attese (vedi Task 4 per `utente`, `app/models/prodotto.py` per `prodotto`). L'autogenerazione a volte dimentica dettagli (indici, unique constraint) — se manca qualcosa, correggilo a mano nel file prima di applicarlo.

- [ ] **Step 5: Applica la migrazione (scrive sul database condiviso — chiedi conferma esplicita all'utente prima di eseguirla)**

```bash
uv run alembic upgrade head
```

- [ ] **Step 6: Verifica che le tabelle esistano**

```bash
uv run python -c "
from sqlmodel import Session, text
from app.database import engine

with Session(engine) as session:
    tabelle = session.exec(text(\"SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'\")).all()
    print(tabelle)
"
```

Output atteso: una lista che include `prodotto`, `utente` e `alembic_version`.

- [ ] **Step 7: Commit**

```bash
git add migrations/env.py migrations/versions/
git commit -m "Collega Alembic ai modelli e crea le tabelle iniziali

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Autenticazione (`app/auth.py`)

**Cosa fa:** Un solo file responsabile di tutto ciò che riguarda "sei chi dici di essere e puoi entrare?": hashing/verifica password con Argon2, ricerca dell'utente e verifica delle credenziali, e il middleware che intercetta ogni richiesta HTTP e reindirizza a `/login` chi non è autenticato. Il pattern del middleware è quello ufficiale della demo `examples/authentication` di NiceGUI: usa `Client.page_routes.values()` per riconoscere solo le vere pagine dell'app (non asset statici o endpoint interni di NiceGUI), evitando falsi positivi.

**Files:**
- Create: `app/auth.py`

**Interfaces:**
- Consuma: `Utente` da `app/models/utente.py` (Task 4).
- Produce: `hash_password(password: str) -> str`, `verifica_password(password: str, password_hash: str) -> bool`, `autentica(session: Session, username: str, password: str) -> Optional[Utente]`, `AuthMiddleware` (classe Starlette) — usati da: `app/scripts/crea_utente.py` (Task 7, `hash_password`), `app/ui/pages_login.py` (Task 9, `autentica`), `app/main.py` (Task 11, `AuthMiddleware`).

- [ ] **Step 1: Scrivi `app/auth.py`**

```python
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import Client, app
from sqlmodel import Session, select
from starlette.middleware.base import BaseHTTPMiddleware

from app.models.utente import Utente

_password_hasher = PasswordHasher()

PERCORSI_PUBBLICI = {"/login"}


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verifica_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def autentica(session: Session, username: str, password: str) -> Optional[Utente]:
    utente = session.exec(select(Utente).where(Utente.username == username)).first()
    if utente is None or not utente.attivo:
        return None
    if not verifica_password(password, utente.password_hash):
        return None
    return utente


class AuthMiddleware(BaseHTTPMiddleware):
    """Reindirizza a /login chi non è autenticato e prova ad accedere a una pagina protetta."""

    async def dispatch(self, request: Request, call_next):
        autenticato = app.storage.user.get("authenticated", False)
        percorso_e_pagina_protetta = (
            request.url.path in Client.page_routes.values()
            and request.url.path not in PERCORSI_PUBBLICI
        )
        if not autenticato and percorso_e_pagina_protetta:
            app.storage.user["referrer_path"] = request.url.path
            return RedirectResponse("/login")
        return await call_next(request)
```

Perché `autentica` restituisce sempre lo stesso `None` sia per username inesistente sia per password sbagliata: così chi prova a fare login non può dedurre quali username esistono nel sistema (evita "enumerazione utenti").

- [ ] **Step 2: Verifica hashing e verifica password**

```bash
uv run python -c "
from app.auth import hash_password, verifica_password

hashed = hash_password('prova123')
print(verifica_password('prova123', hashed))   # atteso: True
print(verifica_password('sbagliata', hashed))  # atteso: False
"
```

- [ ] **Step 3: Commit**

```bash
git add app/auth.py
git commit -m "Aggiunge autenticazione: hashing Argon2 e middleware di protezione pagine

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Script per creare il primo utente admin

**Cosa fa:** Essendo un'app interna senza auto-registrazione, serve un modo per creare utenti. Questo script a riga di comando chiede username, password (senza mostrarla a schermo) e ruolo, e inserisce la riga nel database. Lo userai subito dopo per creare il tuo utente admin e poter fare login.

**Files:**
- Create: `app/scripts/__init__.py` (vuoto, serve per eseguire lo script come modulo)
- Create: `app/scripts/crea_utente.py`

**Interfaces:**
- Consuma: `hash_password` (Task 6), `engine` (Task 3), `RuoloUtente`/`Utente` (Task 4).
- Produce: una riga nella tabella `utente` del database.

- [ ] **Step 1: Crea `app/scripts/__init__.py`**

File vuoto (segna la cartella come pacchetto Python importabile).

- [ ] **Step 2: Scrivi `app/scripts/crea_utente.py`**

```python
import getpass

from sqlmodel import Session

from app.auth import hash_password
from app.database import engine
from app.models.utente import RuoloUtente, Utente


def main() -> None:
    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    ruolo_input = input("Ruolo (admin/operatore) [operatore]: ").strip() or "operatore"
    ruolo = RuoloUtente(ruolo_input)

    with Session(engine) as session:
        utente = Utente(username=username, password_hash=hash_password(password), ruolo=ruolo)
        session.add(utente)
        session.commit()
        session.refresh(utente)

    print(f"Utente '{utente.username}' creato con ruolo '{utente.ruolo.value}'.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Esegui lo script e crea il tuo utente admin**

```bash
uv run python -m app.scripts.crea_utente
```

Rispondi con un username a tua scelta, una password, e `admin` come ruolo. Tienitela a mente: la userai per il primo login nel Task 12.

- [ ] **Step 4: Verifica che l'utente sia stato creato**

```bash
uv run python -c "
from sqlmodel import Session, select
from app.database import engine
from app.models.utente import Utente

with Session(engine) as session:
    utenti = session.exec(select(Utente)).all()
    print([(u.username, u.ruolo.value, u.attivo) for u in utenti])
"
```

Output atteso: una lista con l'utente appena creato.

- [ ] **Step 5: Commit**

```bash
git add app/scripts/__init__.py app/scripts/crea_utente.py
git commit -m "Aggiunge script CLI per creare utenti (crea il primo admin)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: Layout condiviso (`app/ui/layout.py`)

**Cosa fa:** Un "guscio" grafico riutilizzabile da ogni pagina protetta: header in alto (titolo, bottone menu, nome utente, logout) e drawer laterale con i link di navigazione (Admin visibile solo se il ruolo è admin). È un *context manager* Python: ogni pagina lo richiama con `with layout("Titolo"):` e scrive il proprio contenuto dentro, senza duplicare header/drawer in ogni file.

**Files:**
- Create: `app/ui/layout.py`

**Interfaces:**
- Consuma: `app.storage.user` (popolato dal login, Task 9) per leggere `ruolo` e `username`.
- Produce: `layout(titolo_pagina: str)` — context manager, usato da: `app/ui/pages_prodotti.py`, `app/ui/pages_fatture.py`, `app/ui/pages_admin.py` (Task 10).

- [ ] **Step 1: Scrivi `app/ui/layout.py`**

```python
from contextlib import contextmanager

from nicegui import app, ui


@contextmanager
def layout(titolo_pagina: str):
    ruolo = app.storage.user.get("ruolo")
    username = app.storage.user.get("username", "")

    def logout() -> None:
        app.storage.user.clear()
        ui.navigate.to("/login")

    with ui.left_drawer().classes("bg-gray-50") as drawer:
        with ui.column().classes("gap-1 p-2"):
            ui.link("Prodotti", "/prodotti").classes("p-2 rounded hover:bg-gray-200")
            ui.link("Fatture", "/fatture").classes("p-2 rounded hover:bg-gray-200")
            if ruolo == "admin":
                ui.link("Admin", "/admin").classes("p-2 rounded hover:bg-gray-200")

    with ui.header().classes("items-center justify-between px-4"):
        with ui.row().classes("items-center gap-2"):
            ui.button(on_click=drawer.toggle, icon="menu").props("flat color=white")
            ui.label("Karma Inventory Manager").classes("text-lg font-semibold")
        with ui.row().classes("items-center gap-4"):
            ui.label(username)
            ui.button("Esci", on_click=logout).props("flat color=white")

    with ui.column().classes("w-full max-w-5xl mx-auto p-4 md:p-8 gap-4"):
        ui.label(titolo_pagina).classes("text-2xl font-bold")
        with ui.column().classes("w-full gap-4"):
            yield
```

Perché il bottone menu (`icon="menu"`) e non un drawer che si apre "da solo" su schermi stretti: il drawer di Quasar si adatta già da solo tra modalità overlay (mobile) e fissa (desktop), ma serve comunque un bottone esplicito per aprirlo/chiuderlo — è lo standard anche nei siti "veri", non una limitazione di NiceGUI.

Questo file non ha un modo automatico di essere "verificato da riga di comando" (è pura UI): lo controlli visivamente nel Task 12, quando le pagine che lo usano esistono davvero.

- [ ] **Step 2: Verifica che il file non abbia errori di sintassi/import**

```bash
uv run python -c "from app.ui.layout import layout; print(layout)"
```

Output atteso: qualcosa come `<function layout at 0x...>`.

- [ ] **Step 3: Commit**

```bash
git add app/ui/layout.py
git commit -m "Aggiunge il layout condiviso (header + drawer responsive)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: Pagina di login (`app/ui/pages_login.py`)

**Cosa fa:** L'unica pagina raggiungibile senza essere autenticati. Mostra un form username/password; se le credenziali sono corrette, salva lo stato "autenticato" nella sessione (`app.storage.user`) e reindirizza alla pagina che l'utente stava cercando di raggiungere (`referrer_path`, salvato dal middleware nel Task 6) o alla home.

**Files:**
- Create: `app/ui/pages_login.py`

**Interfaces:**
- Consuma: `autentica` (Task 6), `engine`/`Session` (Task 3).
- Produce: la rotta `/login`, e popola `app.storage.user` con `authenticated`, `username`, `ruolo` — da cui dipendono `app/ui/layout.py` (Task 8) e le pagine protette (Task 10).

- [ ] **Step 1: Scrivi `app/ui/pages_login.py`**

```python
from nicegui import app, ui
from sqlmodel import Session

from app.auth import autentica
from app.database import engine


@ui.page("/login")
def pagina_login():
    if app.storage.user.get("authenticated", False):
        ui.navigate.to("/")
        return

    def prova_login() -> None:
        with Session(engine) as session:
            utente = autentica(session, campo_username.value, campo_password.value)
        if utente is None:
            ui.notify("Credenziali non valide", type="negative")
            return
        app.storage.user.update(
            {
                "authenticated": True,
                "username": utente.username,
                "ruolo": utente.ruolo.value,
            }
        )
        destinazione = app.storage.user.pop("referrer_path", "/")
        ui.navigate.to(destinazione)

    with ui.column().classes("absolute-center items-stretch gap-4 w-80"):
        ui.label("Karma Inventory Manager").classes("text-xl font-bold text-center")
        campo_username = ui.input("Username").classes("w-full")
        campo_password = ui.input(
            "Password", password=True, password_toggle_button=True
        ).classes("w-full")
        campo_password.on("keydown.enter", prova_login)
        ui.button("Accedi", on_click=prova_login).classes("w-full")
```

Nota: `campo_password.on("keydown.enter", prova_login)` permette di fare login premendo Invio, non solo cliccando il bottone — piccolo dettaglio che fa sentire l'app "professionale".

- [ ] **Step 2: Verifica che il file non abbia errori di sintassi/import**

```bash
uv run python -c "import app.ui.pages_login"
```

Nessun errore atteso (registra la pagina, non la esegue: la vedremo davvero nel Task 12).

- [ ] **Step 3: Commit**

```bash
git add app/ui/pages_login.py
git commit -m "Aggiunge la pagina di login

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 10: Pagine placeholder (Prodotti, Fatture, Admin)

**Cosa fa:** Tre pagine minime, ciascuna dentro il layout condiviso, che mostrano solo "sezione in costruzione". Servono a validare che navigazione, layout responsive e permessi funzionino concretamente — la pagina Admin in particolare verifica che un `operatore` non possa accedervi nemmeno digitando l'URL a mano.

**Files:**
- Modify: `app/ui/pages_prodotti.py` (attualmente vuoto)
- Modify: `app/ui/pages_fatture.py` (attualmente vuoto)
- Modify: `app/ui/pages_admin.py` (attualmente vuoto)

**Interfaces:**
- Consuma: `layout` (Task 8), `app.storage.user` (per il controllo ruolo in `pages_admin.py`).
- Produce: le rotte `/prodotti`, `/fatture`, `/admin`, importate da `app/main.py` (Task 11).

- [ ] **Step 1: Scrivi `app/ui/pages_prodotti.py`**

```python
from nicegui import ui

from app.ui.layout import layout


@ui.page("/prodotti")
def pagina_prodotti():
    with layout("Prodotti"):
        ui.label("Sezione in costruzione.")
```

- [ ] **Step 2: Scrivi `app/ui/pages_fatture.py`**

```python
from nicegui import ui

from app.ui.layout import layout


@ui.page("/fatture")
def pagina_fatture():
    with layout("Fatture"):
        ui.label("Sezione in costruzione.")
```

- [ ] **Step 3: Scrivi `app/ui/pages_admin.py`**

```python
from nicegui import app, ui

from app.ui.layout import layout


@ui.page("/admin")
def pagina_admin():
    if app.storage.user.get("ruolo") != "admin":
        ui.notify("Accesso riservato agli amministratori", type="negative")
        ui.navigate.to("/")
        return
    with layout("Admin"):
        ui.label("Sezione in costruzione.")
```

- [ ] **Step 4: Verifica che i tre file non abbiano errori di sintassi/import**

```bash
uv run python -c "import app.ui.pages_prodotti, app.ui.pages_fatture, app.ui.pages_admin"
```

- [ ] **Step 5: Commit**

```bash
git add app/ui/pages_prodotti.py app/ui/pages_fatture.py app/ui/pages_admin.py
git commit -m "Aggiunge pagine placeholder Prodotti/Fatture/Admin

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 11: Punto d'ingresso (`app/main.py`)

**Cosa fa:** Il file che avvii davvero. Importa tutte le pagine (l'`import` da solo basta a registrarle, grazie a `@ui.page`), registra il middleware di autenticazione, imposta la palette colori del tema, e infine avvia il server con `ui.run(...)`.

**Files:**
- Modify: `app/main.py` (attualmente ha solo `from nicegui import ui`)

**Interfaces:**
- Consuma: `AuthMiddleware` (Task 6), `settings` (Task 2), i moduli pagina (Task 9, Task 10).
- Produce: l'app in esecuzione su `http://localhost:8080`.

- [ ] **Step 1: Scrivi `app/main.py`**

```python
from nicegui import app, ui

from app.auth import AuthMiddleware
from app.config import settings
from app.ui import pages_admin, pages_fatture, pages_login, pages_prodotti  # noqa: F401


@ui.page("/")
def indice():
    ui.navigate.to("/prodotti")


app.add_middleware(AuthMiddleware)

ui.colors(primary="#2563eb", secondary="#64748b", accent="#0ea5e9")

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(storage_secret=settings.secret_key, title=settings.app_name)
```

Perché `if __name__ in {"__main__", "__mp_main__"}`: è l'idioma richiesto da NiceGUI quando usi il reload automatico in sviluppo (avvia un sotto-processo che reimporta questo file con `__name__ == "__mp_main__"`); senza questa guardia rischi di avviare il server due volte.

Perché gli `import` di `pages_admin`, `pages_fatture`, ecc. sembrano "inutilizzati" (da qui il `# noqa: F401`, che dice a Ruff di non segnalarli come errore): non li chiami mai direttamente, ma importarli esegue il decoratore `@ui.page(...)` in ciascun file, che è ciò che registra davvero le rotte.

- [ ] **Step 2: Avvia l'app**

```bash
uv run python -m app.main
```

Dovrebbe aprirsi il browser su `http://localhost:8080`, con redirect automatico a `/login` (perché non sei ancora autenticato). Lascialo in esecuzione per il Task 12.

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "Assembla il punto d'ingresso dell'app: middleware, tema, avvio

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 12: Verifica end-to-end e pulizia finale

**Cosa fa:** Con l'app in esecuzione (Task 11, Step 2), verifichi manualmente l'intero flusso che questo piano doveva costruire, poi passi gli strumenti di qualità del codice.

**Files:** nessuno (solo verifica)

- [ ] **Step 1: Verifica il redirect per utenti non autenticati**

Apri `http://localhost:8080/` (o `/prodotti`, `/admin`) in una finestra in incognito. Atteso: redirect automatico a `/login`.

- [ ] **Step 2: Login con l'utente admin creato nel Task 7**

Inserisci username/password, premi Invio o clicca "Accedi". Atteso: redirect a `/prodotti`, header con il tuo username, drawer con Prodotti/Fatture/**Admin** (visibile perché sei admin).

- [ ] **Step 3: Verifica il layout responsive**

Restringi la finestra del browser (o apri i DevTools in modalità mobile). Atteso: il drawer si nasconde, resta visibile solo il bottone menu (☰) nell'header; cliccandolo il drawer appare come overlay sopra il contenuto.

- [ ] **Step 4: Verifica la navigazione e il logout**

Clicca su "Fatture", poi "Prodotti", poi "Admin" — tutte devono mostrare "Sezione in costruzione." dentro il layout. Clicca "Esci": atteso redirect a `/login`, e visitando di nuovo `/prodotti` atteso nuovo redirect a `/login` (la sessione è stata cancellata).

- [ ] **Step 5: Verifica il controllo di ruolo**

Crea un secondo utente con ruolo `operatore` (`uv run python -m app.scripts.crea_utente`), fai login con quello, e prova a visitare `http://localhost:8080/admin` **digitando l'URL a mano**. Atteso: notifica "Accesso riservato agli amministratori" e redirect a `/prodotti` — il link "Admin" non deve nemmeno comparire nel drawer per questo utente.

- [ ] **Step 6: Controllo di stile con Ruff**

```bash
uv run ruff check .
uv run ruff format .
```

Correggi eventuali segnalazioni prima di committare. Se `ruff format` modifica dei file, rivedili prima di committare.

- [ ] **Step 7: Commit finale (se `ruff format` ha modificato qualcosa)**

```bash
git add -A
git status   # controlla che non compaia .env o altro file sensibile
git commit -m "Applica la formattazione Ruff allo scheletro applicativo

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Cosa resta per la prossima sessione

- Logica di dominio reale nelle pagine Prodotti/Fatture (tabelle, form, CRUD collegato al database).
- Test automatici per `app/auth.py` e per le pagine (attualmente `tests/conftest.py` è vuoto).
- Gestione utenti da interfaccia (oggi solo via script CLI).
- Generazione PDF con WeasyPrint (dipendenza già presente, non ancora usata).
