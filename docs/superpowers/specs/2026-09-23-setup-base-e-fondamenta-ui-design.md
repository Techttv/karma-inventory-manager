# Setup base dell'app e fondamenta UI — Design

Data: 2026-09-23
Stato: approvato

## Contesto

Il progetto `karma-inventory-manager` è uno scheletro NiceGUI + FastAPI + SQLModel +
PostgreSQL per la gestione del magazzino di Karma Montaggi. `app/main.py`,
`app/config.py`, `app/database.py` e tutti i moduli in `app/ui/` esistono come file
vuoti. L'unico modello di dominio presente è `Prodotto`
(`app/models/prodotto.py`). Non esiste ancora nessuna infrastruttura applicativa:
niente configurazione, niente connessione al database, niente autenticazione,
niente layout.

Questo documento definisce il design della prima iterazione: mettere in piedi lo
scheletro applicativo (configurazione, database, autenticazione con ruoli, layout
responsive) senza ancora costruire le pagine di dominio (Prodotti/Fatture), che
restano fuori scope e verranno affrontate in una sessione successiva.

## Decisioni prese durante il brainstorming

- **Autenticazione**: login con ruoli (`admin` vs `operatore`), non solo un
  login condiviso senza permessi — coerente con l'esistenza già pianificata di
  `app/ui/pages_admin.py`.
- **Navigazione**: pagine multiple classiche (`@ui.page` per rotta), non
  `ui.sub_pages`. Motivo: `ui.sub_pages` è una feature NiceGUI più recente con
  diverse issue aperte upstream (parametri di path, routing dietro reverse
  proxy, conflitti con `app.include_router()`); per uno strumento aziendale che
  deve essere affidabile si preferisce la via matura. Il "flash" di transizione
  tra pagine multiple è impercettibile su rete locale/aziendale. L'autenticazione
  via cookie di sessione (`app.storage.user`) funziona identica in entrambi gli
  approcci, quindi questo non è un fattore discriminante.
- **Stile/design**: si resta su NiceGUI puro (che sotto il cofano è già Vue/Quasar),
  personalizzato con tema Quasar + Tailwind, invece di costruire un frontend
  React/Vue separato. Un frontend separato richiederebbe due codebase, build
  TypeScript, sincronizzazione dell'autenticazione tra due app e deploy doppio:
  va contro l'obiettivo di codice facile/veloce/leggibile in un solo linguaggio.
- **Database di sviluppo**: solo PostgreSQL (quello aziendale, già raggiungibile
  via `.env` esistente), nessun fallback SQLite. Meno complessità, un solo
  dialetto SQL da mantenere compatibile con le migrazioni Alembic.
- **Hashing password**: `argon2-cffi` (raccomandazione OWASP corrente), non
  bcrypt/passlib.
- **Scope di questa iterazione**: solo lo scheletro applicativo (config,
  database, Alembic collegato ai modelli, modello Utente, autenticazione con
  ruoli, layout responsive). Le pagine Prodotti/Fatture restano placeholder
  "in costruzione" — servono solo a validare che navigazione e permessi
  funzionino end-to-end. Nessuna logica di dominio in questa sessione.

## Componenti

### 1. `app/config.py`

Classe `Settings(BaseSettings)` (pydantic-settings) che legge da `.env`:
- `database_url: str`
- `secret_key: str` — usato per firmare le sessioni NiceGUI (`storage_secret`).
  **Deve essere un valore diverso dalla password del database**, generato ad hoc
  (es. `python -c "import secrets; print(secrets.token_hex(32))"`), e aggiunto
  al `.env` (mai committato).
- `app_name: str` con default sensato (es. `"Karma Inventory Manager"`).

Pydantic valida tutto all'avvio: se manca una variabile richiesta, l'app fallisce
subito con un errore leggibile invece che più avanti in modo criptico.

Un'istanza singleton `settings = Settings()` esportata dal modulo, importata
ovunque serva configurazione.

### 2. `app/database.py`

- Un `engine` SQLModel creato una volta sola da `settings.database_url`.
- Una funzione `get_session()` che apre e chiude una `Session` per operazione
  (context manager o generatore), da usare nei repository/servizi che
  seguiranno nelle prossime sessioni.
- Nessuna creazione automatica di tabelle (niente `SQLModel.metadata.create_all`
  in produzione): la creazione/modifica dello schema resta esclusivamente
  compito di Alembic.

### 3. Alembic collegato ai modelli (`migrations/env.py`)

Attualmente `target_metadata = None` e l'URL è quello placeholder di
`alembic.ini`. Modifiche:
- Importare `settings` da `app.config` e usare `settings.database_url` come URL
  di connessione (sia in modalità offline che online).
- Importare tutti i modelli SQLModel (`app.models`) e impostare
  `target_metadata = SQLModel.metadata`, così `alembic revision --autogenerate`
  rileva correttamente le tabelle.
- Necessario perché il punto successivo introduce un nuovo modello che deve
  diventare una tabella reale nel database condiviso.

### 4. Modello Utente e ruoli (`app/models/utente.py`)

```python
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

Le password non si salvano mai in chiaro: si salva solo `password_hash`,
calcolato con Argon2 (`argon2-cffi`).

Non esiste auto-registrazione (app interna aziendale). Per creare il primo
utente admin: script `app/scripts/crea_utente.py`, eseguibile con
`uv run python -m app.scripts.crea_utente`, che chiede a terminale username,
password (non echeggiata) e ruolo, e inserisce la riga nel database tramite
`get_session()`.

### 5. Autenticazione (`app/auth.py` + middleware)

- `hash_password(password: str) -> str` e
  `verifica_password(password: str, password_hash: str) -> bool` con Argon2.
- `autentica(username: str, password: str) -> Optional[Utente]`: cerca
  l'utente per username, verifica che sia `attivo`, verifica la password.
  Messaggio di errore generico ("credenziali non valide") sia per utente
  inesistente che per password sbagliata, per non rivelare quali username
  esistono.
- Pagina `/login` (`app/ui/pages_login.py`): form username/password, su submit
  chiama `autentica`, se ok salva in `app.storage.user`:
  `{'authenticated': True, 'username': ..., 'ruolo': ...}`, poi
  `ui.navigate.to('/')`. Se fallisce: `ui.notify('Credenziali non valide', type='negative')`.
- Middleware `AuthMiddleware` (Starlette `BaseHTTPMiddleware`, registrato in
  `main.py`): per ogni richiesta, se il path non è tra quelli pubblici
  (`/login` e gli asset statici) e `app.storage.user.get('authenticated')` è
  falso, reindirizza a `/login` (pattern ufficiale dell'esempio
  `examples/authentication` di NiceGUI).
- Logout: bottone che fa `app.storage.user.clear()` seguito da
  `ui.navigate.to('/login')`.
- Pagine riservate agli admin (es. `/admin`): controllo esplicito
  `app.storage.user.get('ruolo') == 'admin'` all'inizio della funzione pagina,
  altrimenti redirect a `/` con un `ui.notify` di accesso negato.

### 6. Layout responsive (`app/ui/layout.py`)

Componente condiviso, richiamato da ogni pagina protetta:
- `ui.header()` in alto: titolo app, nome utente loggato, bottone logout.
- `ui.left_drawer()` con i link di navigazione (Prodotti, Fatture, e Admin
  visibile solo se `ruolo == admin`). Su schermi stretti Quasar trasforma
  automaticamente il drawer in un menu a comparsa con hamburger — comportamento
  nativo, nessun media query scritta a mano.
- Contenuto della pagina in un container centrale con larghezza massima e
  padding responsive (classi Tailwind tipo `p-4 md:p-8`).

### 7. Stile moderno

- Palette colori personalizzata via `ui.colors(primary=..., secondary=..., ...)`
  invece dei colori di default Quasar.
- Card con ombra leggera (`shadow-sm` / `shadow`) e angoli arrotondati
  (`rounded-lg`), spaziature generose, font di sistema pulito.
- Nessun CSS scritto a mano dove una classe Tailwind o un'opzione del tema
  Quasar già disponibile basta.

### 8. `app/main.py`

Punto d'ingresso dell'app:
- Importa i moduli pagina (`app.ui.pages_login`, `app.ui.pages_prodotti`,
  `app.ui.pages_fatture`, `app.ui.pages_admin`, e una pagina indice `/`) per
  registrare le rotte `@ui.page`.
- Registra `AuthMiddleware`.
- Chiama `ui.run(storage_secret=settings.secret_key, title=settings.app_name, ...)`.

### 9. Pagine placeholder

`pages_prodotti.py`, `pages_fatture.py`, `pages_admin.py` diventano pagine
minime protette ("in costruzione", dentro il layout condiviso) — solo per
validare che navigazione, permessi e layout responsive funzionino
concretamente end-to-end. Nessuna logica di dominio (tabelle, form, CRUD) in
questa iterazione.

## Nuove dipendenze

- `argon2-cffi` (hashing password) — da aggiungere con `uv add argon2-cffi`.

## Fuori scope (sessioni successive)

- Logica di dominio delle pagine Prodotti/Fatture (tabelle, form, CRUD reale).
- Generazione PDF (WeasyPrint) — dipendenza già presente ma non ancora usata.
- Test automatici per l'infrastruttura di auth (`tests/conftest.py` è vuoto).
- Gestione utenti da UI (creazione/modifica utenti solo via script per ora).

## Testing previsto per questa iterazione

- Verifica manuale: avvio app, login con utente creato via script, redirect
  a login se non autenticato, navigazione tra le pagine placeholder, voce
  Admin visibile solo per ruolo admin, layout che si adatta correttamente a
  finestra stretta (drawer collassato).
- `uv run ruff check .` e `uv run ruff format .` prima di considerare il lavoro
  concluso.
