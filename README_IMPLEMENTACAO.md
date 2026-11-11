# Residencial Aurora — implementação em desenvolvimento

## Arquitetura
A API FastAPI em `aurora/api.py` usa um `Runner` Google ADK e três especialistas: reservas, visitantes e regulamento (`aurora/agent.py`). O agente principal apenas encaminha tarefas. Persistência de sessões ADK em SQLite e dados de negócio em SQLite separados.

## Garantias
1. **Confirmação**: `make_reservation` e `authorize_visitor` geram pendências; `storage.resolve` exige ID pendente, marca como consumido e aplica a alteração numa transação. A aprovação é feita pela rota HTTP, não por texto da conversa.
2. **Isolamento**: `ToolContext.state["apartment"]` é definido ao criar a sessão; nenhuma tool de leitura/escrita aceita apartamento externo. Disponibilidade só retorna booleano.
3. **Persistência**: `storage.py` mantém reservas, visitantes, confirmações e eventos em SQLite; `DatabaseSessionService` mantém sessões ADK.
4. **Regulamento**: `regulation_search` recupera somente um artigo relevante, sem injetar o documento inteiro nas instruções.
5. **Concorrência**: índice único parcial `unique_active_area_date` no SQLite impede duas reservas ativas da mesma área/data. `storage.resolve` usa `BEGIN IMMEDIATE` para serializar aprovações.

## Como rodar
Requer Python 3.12+, uv e chave Gemini. Copie `.env.example` para `.env` e preencha `GOOGLE_API_KEY`.
Execute `uv sync`, `uv run python -m aurora.reset`, `uv run uvicorn aurora.api:app --host 0.0.0.0 --port 8000`.
Teste com `uv run pytest` e `uv run ruff check .`.

**Estado:** implementação inicial não validada em ambiente com Google ADK e Gemini. Falta gerar/versionar `uv.lock`, executar testes end-to-end e validar as APIs exatas do ADK. Não considerar entrega concluída.
