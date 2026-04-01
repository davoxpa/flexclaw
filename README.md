# FlexClaw3

Framework AI modulare basato su [Agno](https://docs.agno.com), con architettura a plugin per canali e tool, team di agenti dichiarato via YAML e integrazione Telegram pronta all'uso.

## Funzionalità

### Team di agenti dichiarativo

Il team principale `flexclaw` è definito in `config/agents.config.yaml`. Gli agenti attivi:

- **researcher** — ricerca web, Wikipedia, YouTube, articoli
- **file_manager** — gestione file nella sandbox, generazione PDF, knowledge base
- **analyst** — calcoli e ragionamento strutturato
- **weather_expert** — workflow meteo con output grafico PNG

Ruoli, istruzioni, tool assegnati e routing sono tutti configurabili da YAML senza toccare il codice. Il modello può essere cambiato a runtime e la scelta viene persistita in `data/state.yaml`.

### Sistema a plugin

I plugin abilitati sono definiti in `config/plugin.config.yaml`.

**Channel plugin:**

- `telegram_bot` — canale Telegram con supporto testo, documenti, immagini, audio, video e vocali

**Tool plugin custom:**

- `pdf_tool` — generazione PDF
- `weather_tool` — infografiche meteo PNG
- `knowledge_tool` — salvataggio contenuti nella knowledge base (caricato dal core)

**Tool SDK Agno:**

- web search, file system locale, file tools, calculator, Wikipedia, YouTube, Newspaper4k, WebTools, HackerNews, ReasoningTools, Crawl4AI

### Canale Telegram

Il plugin Telegram offre:

- inoltro messaggi al team principale
- supporto documenti, immagini, audio, video e vocali
- lettura inline dei file testuali supportati
- salvataggio file nella sandbox
- streaming in tempo reale di task e tool step
- invio automatico dei file generati dagli agenti
- gestione risposte lunghe con suddivisione in chunk

Comandi utente: `/help` `/status` `/model` `/reset` `/history` `/knowledge`

Comandi admin: `/users` `/logs` `/reload`

### Core runtime

- **agent_os** — bootstrap Agno, knowledge base, model switching
- **agent_builder** — costruzione dichiarativa agenti e team da YAML
- **loader** — discovery plugin, dependency install, load tool/channel
- **event_stream** — streaming progressivo di task e tool step
- **session** — sessioni per canale/chat con supporto reset
- **audit** — audit log strutturato

### Knowledge base e persistenza

- Sessioni gestite per canale/chat con reset via `/reset`
- Sandbox condivisa per upload e file generati
- Knowledge base su ChromaDB in `data/chromadb`
- Database SQLite in `data/db/`

### Sicurezza

- Sanitizzazione input testuale
- Whitelist estensioni file
- Limite upload 10 MB
- Audit log strutturato
- Controllo utenti autorizzati

## Architettura

```text
main.py
config/
  main.config.yaml        Config globale: sandbox, modelli, tool registry, knowledge
  plugin.config.yaml      Plugin channel/tool abilitati
  agents.config.yaml      Agenti, team, istruzioni e routing
core/
  agent_os.py             Bootstrap runtime Agno, knowledge, model switching
  agent_builder.py        Costruzione dichiarativa di agenti e team da YAML
  loader.py               Discovery plugin, dependency install, load tool/channel
  event_stream.py         Streaming progressivo di task e tool step
  session.py              Sessioni per canale/chat con supporto reset
  audit.py                Audit log strutturato
plugin/
  channel/telegram_bot/   Canale Telegram
  tool/pdf_tool/          Generazione PDF
  tool/weather_tool/      Formattazione infografiche meteo PNG
  tool/knowledge_tool/    Salvataggio contenuti nella knowledge base
sandbox/                  Directory operativa per file letti/generati dagli agenti
docs/                     Documentazione aggiuntiva
```

## Documentazione

- [Primo avvio](docs/primo-avvio.md) — installazione, configurazione e primo test
- [Creare un tool plugin](docs/creare-un-tool-plugin.md) — come aggiungere un tool custom
- [Creare un channel plugin](docs/creare-un-channel-plugin.md) — come aggiungere un canale di comunicazione
- [Providers](docs/providers.md) — configurazione modelli e provider supportati

## Estendere il sistema

### Aggiungere un tool custom

1. crea `plugin/tool/<id>/`
2. implementa una classe `Toolkit`
3. esportala in `__init__.py`
4. aggiungi `config.yaml` e opzionale `requirements.txt`
5. abilita il tool in `config/plugin.config.yaml`

### Aggiungere un channel plugin

1. crea `plugin/channel/<id>/`
2. implementa `start_bot()`
3. aggiungi eventuale `requirements.txt`
4. abilita il canale in `config/plugin.config.yaml`

### Modificare agenti e team

Per cambiare ruoli, routing, tool assegnati o istruzioni, lavora su `config/agents.config.yaml`. Non serve toccare il core finché la modifica resta dentro il modello dichiarativo supportato dal builder.
