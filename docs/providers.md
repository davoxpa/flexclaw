# Providers Configuration

La configurazione principale e' [config/agent_os.yaml](config/agent_os.yaml), con stile coerente alla configurazione AgentOS.

Il file [config/providers.yaml](config/providers.yaml) e' inglobato automaticamente come base legacy.

Ordine di merge runtime:
- base: [config/providers.yaml](config/providers.yaml)
- override: [config/agent_os.yaml](config/agent_os.yaml)

In pratica puoi mantenere entrambi i file: se una chiave manca in AgentOS, viene ereditata dal legacy.

## Struttura YAML (AgentOS-style)

```yaml
available_models:
	- openrouter:gpt-4o
	- openai:gpt-4o-mini
	- google:gemini-2.0-flash
	- anthropic:claude-3-5-sonnet-20241022

agent:
	model: openrouter:gpt-4o

embedder:
	model: openai:text-embedding-3-small

system_prompt: |
	You are a helpful assistant.
```

Nel formato nuovo i campi `agent.model` e `embedder.model` usano sempre `provider:model`.

## Provider supportati per agent

- `openrouter` -> `agno.models.openrouter.OpenRouter`
- `openai` -> `agno.models.openai.OpenAIChat`
- `google` -> `agno.models.google.Gemini`
- `anthropic` -> `agno.models.anthropic.Claude`

## Provider supportati per embedder

- `openai` -> `agno.knowledge.embedder.openai.OpenAIEmbedder`
- `google` -> `agno.knowledge.embedder.google.GeminiEmbedder`

Provider come `openrouter` o `anthropic` non sono supportati come embedder in questa implementazione.

## Regole di validazione

- Se `available_models` e' presente, il modello `agent.model` deve comparire nella lista.
- `agent.model` e `embedder.model` devono avere il formato `provider:model`.
- `system_prompt` e' opzionale e viene caricato nelle istruzioni dell'agente.

## Variabili ambiente richieste

- `openrouter`: `OPENROUTER_API_KEY`
- `openai`: `OPENAI_API_KEY`
- `google`: `GOOGLE_API_KEY`
- `anthropic`: `ANTHROPIC_API_KEY`

## Errori comuni

- Se `provider` non e' supportato, viene sollevato `ProviderConfigError` con elenco provider ammessi.
- Se `model` non ha formato `provider:model`, viene sollevato `ProviderConfigError`.
- Se la libreria del provider non e' installata, viene sollevato `ImportError` con messaggio guidato.
