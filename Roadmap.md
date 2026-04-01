
# FlexClaw — Roadmap & Implementazioni Future

> ⚠️ **Nota:** Le voci elencate di seguito rappresentano possibili idee e direzioni di sviluppo, non una roadmap certa o vincolante. Le priorità e le implementazioni effettive potranno variare nel tempo.

> Ultimo aggiornamento: aprile 2026

---

## 🔴 Alta priorità

### 1. API REST (FastAPI) se utili tramite plugin
- Endpoint HTTP per interagire col team (FastAPI è già nelle dipendenze)
- Supporto streaming via WebSocket/SSE
- Autenticazione API key / JWT
- Sblocca: web UI, integrazioni esterne, testing automatizzato

### 2. Comandi Telegram ✅
- ~~`/help` — elenco comandi disponibili~~
- ~~`/reset` — cancella sessione corrente~~
- ~~`/history` — cronologia conversazioni~~
- ~~`/knowledge` — cerca/elenca contenuti nella knowledge base~~
- ~~`/model` — cambia modello al volo~~
- ~~`/status` — stato sistema, plugin attivi, modello in uso~~

### 3. Comandi Admin Telegram ✅
- ~~`admin_user_id` è configurato ma inutilizzato~~
- ~~`/users` — gestione utenti autorizzati~~
- ~~`/logs` — consulta log recenti~~
- ~~`/reload` — ricarica configurazione senza riavvio~~


### 4. Sicurezza
- ~~Sanitizzazione input utente prima di inviarli all'agente~~
- ~~Validazione file upload (dimensione max, tipi ammessi)~~
- ~~Audit log strutturato (chi, cosa, quando)~~
- ~~Secrets management per produzione (vault)~~

---

## 🟡 Media priorità

### 5. Multi-modello / Model Routing
- Modello configurabile per agente da `main.config.yaml`
- Fallback model automatico se il primario fallisce
- Model selection per complessità (gpt-4o-mini per task semplici)
- I modelli in `main.config.yaml` (gpt-4o, gpt-4o-mini, gemini-3-flash) non vengono usati per il routing

### 6. Token Tracking & Costi
- Tracciamento token consumati per utente/sessione
- Dashboard costi con soglie di allerta
- Limite giornaliero/mensile per utente
- Report costi per admin

### 7. Gestione sessioni e memoria
- TTL sessioni — pulizia/archiviazione automatica delle sessioni scadute
- Sessioni per utente separate nei gruppi Telegram
- Export conversazione in PDF/Markdown
- Pulizia periodica SQLite

### 8. Nuovi agenti specializzati
- **Coder** — scrive/analizza codice con sandbox sicura
- **Summarizer** — riassume documenti, video YouTube, podcast
- **Scheduler** — task programmati, promemoria periodici
- **Translator** — traduzioni con context awareness

### 9. Nuovi tool plugin
- **Image generation** — DALL-E / Stable Diffusion
- **Speech-to-Text** — trascrizione audio/vocali (il bot gestisce audio ma non li trascrive)
- **Text-to-Speech** — sintesi vocale per risposte audio
- **Email tool** — invio/lettura email
- **Code execution** — esecuzione Python in sandbox isolata
- **Database query** — interrogazione database SQL/NoSQL

### 10. Monitoring e observability
- Dashboard metriche (richieste, tempi risposta, errori)
- Health check endpoint per deployment
- Alerting admin su errori critici
- Structured logging (JSON) per analisi automatizzata

---

## 🟢 Bassa priorità

### 11. Canali aggiuntivi
- **Discord bot** — secondo canale chat (pattern plugin già pronto)
- **CLI interattiva** — per debug e sviluppo locale
- **Slack bot** — integrazione workspace aziendali
- **WhatsApp** — via API Business

### 12. UX Telegram avanzata
- Inline keyboard con pulsanti interattivi
- Callback query per workflow multi-step ("Vuoi salvare questo file?")
- Typing indicator ("sta scrivendo...") durante l'elaborazione
- Formattazione Markdown nelle risposte (attualmente testo semplice)
- Reply-to-message per dare contesto specifico

---
