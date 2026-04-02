# Discord Bot — Channel Plugin

Plugin per integrare un bot Discord con FlexClaw, permettendo agli utenti di interagire con gli agenti AI tramite messaggi e comandi slash.

## Setup

### 1. Crea l'applicazione su Discord Developer Portal

1. Vai su [Discord Developer Portal](https://discord.com/developers/applications)
2. Clicca **New Application** e dai un nome al bot
3. Nella sezione **Bot**:
   - Clicca **Reset Token** e copia il token
   - Abilita **Message Content Intent** sotto *Privileged Gateway Intents*
4. Nella sezione **OAuth2 → URL Generator**:
   - Scope: `bot`, `applications.commands`
   - Permessi bot: `Send Messages`, `Read Message History`, `Attach Files`, `Use Slash Commands`, `Embed Links`
   - Copia l'URL generato e aprilo nel browser per invitare il bot nel tuo server

### 2. Configura il token

Aggiungi il token nel file `.env` nella root del progetto:

```env
DISCORD_TOKEN=il_tuo_token_qui
```

### 3. Configura il plugin

Copia il template di configurazione:

```bash
cp plugin/channel/discord_bot/config.example.yaml plugin/channel/discord_bot/config.yaml
```

Modifica `config.yaml` con i tuoi dati:

- `admin_user_id`: il tuo ID Discord (Developer Mode → click destro sul profilo → Copia ID)
- `allowed_users`: `"*"` per tutti, oppure lista di ID `[123, 456]`
- `guild_ids`: lista di ID server (vuota = tutti i server)
- `reply_mode`: `"mention"` (risponde solo quando menzionato) o `"all"` (risponde a tutti)
- `show_tool_steps`: `true` per mostrare i passi dei tool durante l'elaborazione

### 4. Abilita il plugin

In `config/plugin.config.yaml`, verifica che il plugin sia abilitato:

```yaml
channel:
  - id: discord_bot
    status: enabled
```

### 5. Avvia il framework

```bash
python main.py
```

Il bot Discord si avvierà automaticamente insieme agli altri canali.

## Comandi Slash

| Comando | Descrizione |
|---|---|
| `/help` | Mostra i comandi disponibili |
| `/status` | Stato del sistema (modello, plugin, sessione) |
| `/model` | Mostra/cambia il modello AI |
| `/reset` | Resetta la sessione corrente |
| `/history` | Informazioni sulla sessione corrente |
| `/knowledge [query]` | Cerca nella knowledge base |

### Comandi Admin

| Comando | Descrizione |
|---|---|
| `/model_set <modello>` | Cambia il modello AI attivo |
| `/users` | Mostra utenti autorizzati |
| `/users_add <id>` | Aggiungi utente autorizzato |
| `/users_rm <id>` | Rimuovi utente autorizzato |
| `/users_open` | Apri il bot a tutti |
| `/reload` | Ricarica la configurazione |

## Come funziona

- **Messaggi di testo**: il bot riceve il messaggio, lo inoltra al team Agno e risponde con lo streaming della risposta
- **File allegati**: vengono scaricati nella sandbox, analizzati dall'agente e la risposta viene inviata nel canale
- **Reply**: se rispondi a un messaggio, il contesto del messaggio originale viene incluso nella richiesta
- **Step dei tool**: durante l'elaborazione viene mostrato un messaggio aggiornato in tempo reale con i passi dei tool in uso
- **File generati**: se l'agente genera file nella sandbox, vengono automaticamente inviati come allegati

## Note

- Il bot usa il **Message Content Intent** (privileged) che va abilitato manualmente nel Developer Portal
- I comandi slash possono impiegare fino a 1 ora per propagarsi globalmente; per test immediati usa `guild_ids` nel config
- Il limite di un messaggio Discord è 2000 caratteri; le risposte lunghe vengono automaticamente suddivise
