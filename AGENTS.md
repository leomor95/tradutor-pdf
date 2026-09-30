# Guia para Agentes de IA — Tradutor de PDF

> Este arquivo é versionado no Git e serve de referência rápida para agentes trabalhando no projeto, especialmente em worktrees ou clones limpos (onde `docs/` está no `.gitignore`).

---

## 1. Visão Geral e Arquitetura

O **Tradutor de PDF** é um aplicativo desktop local e isolado para traduzir documentos técnicos do inglês para português brasileiro (**pt-BR**), preservando a estrutura (títulos, listas, tabelas, imagens e códigos intactos).

### Arquitetura em Pipeline (5 etapas substituíveis — spec §5):
1. **Extração / OCR**: Converte o PDF em lista ordenada de blocos estruturais (`Block`).
2. **Segmentação**: Agrupa blocos em unidades semânticas (`Chunk`), marcando blocos não traduzíveis.
3. **Tradução (LLM local)**: Traduz via Ollama com prompt fixo, glossário e contexto anterior.
4. **Montagem MD**: Reúne trechos traduzidos e elementos preservados em Markdown final.
5. **Exportação**: Gera PDF, EPUB ou mantém Markdown conforme escolha do usuário.

---

## 2. Isolamento e Variáveis de Ambiente (RNF24)

**Regra absoluta:** Nenhum arquivo pode ser criado ou modificado fora da pasta do projeto. Nada em `~/.config`, `~/.ollama`, `~/.cache` ou diretórios de sistema.

Variáveis de ambiente isoladas (configuradas por `scripts/run.sh`):
- `OLLAMA_MODELS=./models`
- `OLLAMA_HOST=127.0.0.1:11434`
- `XDG_CACHE_HOME=./.cache`
- `HF_HOME=./.cache/hf`
- `UV_CACHE_DIR=./.cache/uv`
- `TMPDIR=./.cache/tmp` (também `TEMP` e `TMP`)
- `HOME=./.cache` apenas para o processo `ollama serve` (evita `~/.ollama`)
- `TESSDATA_PREFIX=./bin/tessdata` (se pacote de idioma 'eng' não estiver no sistema)

---

## 3. Convenções de Código e Desenvolvimento

- **Idiomas:**
  - Código, identificadores, comentários e logs: **inglês**.
  - Textos de interface exibidos ao usuário: **pt-BR**.
- **Ambiente:** Python 3.12 gerenciado exclusivamente com `uv`.
  - Novas dependências devem ser adicionadas via `uv add <pacote>` ou `uv add --dev <pacote>`.
- **Commits:**
  - **Um commit por tarefa**, seguindo Conventional Commits (`feat:`, `fix:`, `test:`, `chore:`, `docs:`).
- **Testes:**
  - Testes unitários padrão **nunca** chamam LLM real, GPU ou dependências externas pesadas (usar fixture `fake_llm`).
  - Testes de integração pesados usam marcador `@pytest.mark.slow` e são ignorados por padrão no `uv run pytest`.
  - `uv run pytest` deve estar 100% verde ao final de cada tarefa.
- **Qualidade de código:**
  - Verificar linter: `uv run ruff check`
  - Formatar código: `uv run ruff format`

---

## 4. Comandos Principais

```bash
# Setup inicial idempotente (baixa uv deps, Ollama em bin/ e modelo em models/)
./scripts/setup.sh

# Verificar saúde do Ollama local e modelo configurado
./scripts/run.sh --check

# Executar a aplicação
./scripts/run.sh

# Rodar testes unitários rápidos
uv run pytest

# Rodar testes lentos (requer Ollama rodando com modelo carregado)
uv run pytest -m slow

# Lint e formatação
uv run ruff check
uv run ruff format
```

---

## 5. Estrutura de Pastas

```
tradutor-pdf/
├── AGENTS.md             # Este guia versionado
├── README.md             # Visão geral para usuários e desenvolvedores
├── bin/                  # Ollama, JRE portátil, epubcheck e tessdata (ignorado pelo git)
├── lib/                  # Bibliotecas do Ollama extraídas pelo setup (ignorado pelo git)
├── config/
│   ├── settings.toml     # Configurações do app (modelo, OCR, diretórios)
│   ├── glossario.yaml    # Termos a preservar e traduções fixas
│   └── state.json        # Última pasta de destino usada (ignorado pelo git)
├── docs/                 # Documentação e sprints (ignorado pelo git)
├── logs/                 # Logs rotativos da aplicação e do Ollama
├── models/               # Modelos locais do Ollama (ignorado pelo git)
├── out/                  # Saídas de build/exportação locais (ignorado pelo git)
├── scripts/
│   ├── setup.sh          # Script de instalação idempotente
│   ├── run.sh            # Script de inicialização isolada
│   ├── benchmark.py      # Benchmark de tempo, RAM e VRAM por etapa (relatório em logs/)
│   ├── audit_isolation.sh # Auditoria de arquivos criados fora do projeto
│   └── gen_big_pdf.py    # Gera PDF sintético grande (padrão: 1000 páginas)
├── src/tradutor_pdf/
│   ├── extraction/       # Extração e OCR de PDFs
│   ├── segmentation/     # Divisão semântica em trechos
│   ├── translation/      # Integração Ollama, prompts e glossário
│   ├── assembly/         # Montagem e recomposição em Markdown
│   ├── export/           # Exportadores (MD/PDF/EPUB) e conversor de formatos
│   ├── checkpoint/       # Persistência atômica e retomada
│   ├── ui/               # Interface gráfica PySide6
│   ├── config.py         # Leitura e validação de configurações
│   ├── logging_setup.py  # Configuração de logs e medição de tempo
│   └── pipeline.py       # Protocols e estruturas de dados
├── tests/                # Testes unitários, testes de UI (tests/ui/) e fixtures (conftest.py)
│   └── fixtures/         # PDFs de teste gerados de fontes Typst por build_fixtures.py
├── .cache/               # Cache local isolado, checkpoints e TMPDIR
├── .venv/                # Ambiente virtual Python 3.12
└── pyproject.toml        # Metadados e dependências do projeto
```
