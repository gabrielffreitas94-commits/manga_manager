# MangaTrack

PoC de um gerenciador pessoal de mangás em Python (**FastAPI** + **SQLite** + **HTML/Tailwind CSS**).

## Funcionalidades

- Cadastro manual de mangás (título, capítulo lido, capítulo atual, status, nota, link de leitura, capa, dia de lançamento e observações).
- Suporte a capítulos inteiros e decimais (ex.: `12.1`, `31.1`).
- Controles rápidos nos cards (`-1`, `+1 Lido`, `✓ Em dia`) e cálculo automático de capítulos acumulados.
- Filtros por status, filtro de capítulos acumulados, busca instantânea e ordenação.
- Importação em lote via texto colado (`Viewed : Chapter X Current : Chapter Y`) e backup/restauração em JSON.

## Como executar

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Ou no Windows, basta executar `run.bat`. Depois acesse `http://localhost:8000`.

## Testes

```powershell
.\.venv\Scripts\python -m pytest -v
```

## Licença

Distribuído sob a licença MIT. Veja `LICENSE` para mais informações.
