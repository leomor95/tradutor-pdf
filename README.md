# Tradutor de PDF (EN → pt-BR)

Aplicativo desktop de uso pessoal que traduz documentos técnicos em PDF do inglês para o português do Brasil usando um LLM **100% local** (Ollama). A estrutura do documento é preservada: títulos, listas, ênfase, notas de rodapé, blocos de código, tabelas e imagens. O resultado é salvo em Markdown e pode ser exportado para PDF ou EPUB.

Nenhum conteúdo sai da máquina e, depois do setup, tudo funciona offline. Todos os arquivos do projeto (ambiente Python, binários, modelos, cache e logs) ficam dentro da pasta do repositório.

## Funcionalidades

- **Arrastar e soltar** um PDF na janela (ou escolher pelo diálogo) para iniciar a tradução.
- **OCR seletivo:** detecta, página a página, se há camada de texto; aplica Tesseract só nas páginas escaneadas, removendo hifenização e cabeçalhos/rodapés repetidos.
- **Tradução por unidades semânticas** (parágrafo, item de lista, título), nunca por linha física do PDF.
- **Glossário editável:** termos que nunca são traduzidos (`bug`, `pipeline`, `deploy`…) e termos com tradução fixa, verificados após cada trecho.
- **Contexto entre trechos:** cada trecho recebe o contexto do anterior, mantendo a terminologia consistente.
- **Proteção de conteúdo técnico:** código inline, URLs e caminhos de arquivo são substituídos por marcadores durante a tradução e restaurados depois; blocos de código, tabelas e imagens nem passam pelo LLM.
- **Validação da resposta:** checa estrutura Markdown, proporção de tamanho e resíduos de conversa do modelo. Até 3 tentativas; se todas falharem, o texto original é mantido com a marca `<!-- NÃO TRADUZIDO -->`.
- **Checkpoint e retomada:** cada trecho traduzido é gravado em disco. Um processo interrompido continua de onde parou, sem retraduzir.
- **Streaming:** o PDF é processado em janelas de páginas, com memória limitada independentemente do tamanho, e o `.md` é atualizado incrementalmente.
- **Exportação** para Markdown (com `assets/`), PDF (Pandoc + Typst) ou EPUB (validado com `epubcheck`).
- **Conversão avulsa** entre PDF, MD e EPUB, sem tradução.
- **Interface em pt-BR:** etapa atual, "página X de N", tempo restante estimado, cancelar/retomar e mensagens de erro que dizem o que fazer.

## Requisitos

| Item | Observação |
|---|---|
| Linux x86_64 | Único sistema suportado |
| [`uv`](https://docs.astral.sh/uv/getting-started/installation/) | Gerencia o Python 3.12 e as dependências |
| Tesseract | `pacman -S tesseract` · `apt install tesseract-ocr` · `dnf install tesseract`. Se o idioma `eng` não estiver instalado, o setup baixa para `bin/tessdata/` |
| GPU NVIDIA + driver/CUDA | Opcional. Sem GPU, o Ollama roda na CPU (bem mais lento) |
| `curl`, `tar` com suporte a zstd, `unzip` | Usados pelo setup para baixar os componentes |

O próprio setup baixa, **dentro da pasta do projeto**: as dependências Python, o binário do Ollama, o modelo LLM, uma JRE portátil (só se não houver Java no sistema) e o `epubcheck`.

## Instalação

```bash
git clone <url-do-repositorio> tradutor-pdf
cd tradutor-pdf
./scripts/setup.sh          # idempotente: pode ser executado de novo sem problemas
./scripts/run.sh --check    # sobe o Ollama local e testa se o modelo responde
```

O setup tem 6 etapas: pré-requisitos do sistema → `uv sync` → Ollama em `bin/` → JRE + epubcheck → leitura do modelo em `config/settings.toml` → download do modelo em `models/` (cerca de 4,4 GB para o modelo padrão).

**Desinstalar:** apague a pasta do projeto.

## Uso

### Interface gráfica

```bash
./scripts/run.sh
```

O script exporta as variáveis de isolamento, inicia o Ollama em `127.0.0.1:11434` (se ainda não estiver rodando; log em `logs/ollama.log`) e abre a janela.

Fluxo principal (até 4 interações): **arrastar o PDF → acompanhar o progresso → escolher o formato (MD, PDF ou EPUB) → escolher a pasta**. O Markdown traduzido é salvo automaticamente em `.cache/<sha256-do-pdf>/output/<nome>.pt-BR.md` antes da exportação. A última pasta de destino é lembrada entre execuções.

Atalhos: `Ctrl+K` abre a conversão de formatos · `Ctrl+Q` sai.

### Linha de comando

Com o Ollama rodando (`./scripts/run.sh --check` o inicia), passe os argumentos pelo `run.sh`:

```bash
# Traduzir um PDF sem interface gráfica
./scripts/run.sh --cli livro.pdf -o livro.pt-BR.md

# Ignorar o checkpoint existente e traduzir do zero
./scripts/run.sh --cli livro.pdf --restart

# Converter formatos sem traduzir (md, pdf, epub)
./scripts/run.sh --convert livro.pt-BR.md --to epub -o livro.epub
./scripts/run.sh --convert livro.epub --to md
```

Se o modelo ou a versão do prompt mudaram desde a última execução, a CLI pergunta se deve reaproveitar os trechos já traduzidos.

## Configuração

### `config/settings.toml`

```toml
[translation]
model = "qwen2.5:7b-instruct-q4_K_M"   # qualquer modelo do Ollama; rode setup.sh após trocar
target_language = "pt-BR"
chunk_max_tokens = 800                  # tamanho máximo de cada trecho
max_retries = 3                         # tentativas por trecho antes de marcar NÃO TRADUZIDO
temperature = 0.2

[ocr]
engine = "tesseract"
languages = ["eng"]
# min_chars = 50                        # abaixo disso, a página é tratada como escaneada

[output]
default_dir = "~/Documentos"
```

### `config/glossario.yaml`

```yaml
preservar:            # nunca traduzir
  - bug
  - pipeline
  - deploy
traduzir_como:        # tradução fixa
  "machine learning": "aprendizado de máquina"
```

## Arquitetura

O pipeline tem 5 etapas substituíveis, cada uma atrás de um `Protocol` definido em `src/tradutor_pdf/pipeline.py`:

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│ 1. Extração │──▶│ 2. Segmen-  │──▶│ 3. Tradução │──▶│ 4. Montagem │──▶│5. Exportação│
│    + OCR    │   │    tação    │   │    (LLM)    │   │     MD      │   │  PDF / EPUB │
└─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘
   Docling +        blocos            Ollama +          Markdown +        Pandoc /
   Tesseract        semânticos        glossário +       assets/           Typst
                                      contexto
                          │                 │
                          └── .cache/<sha256-do-pdf>/ (manifest + trechos = checkpoint)
```

| Módulo (`src/tradutor_pdf/`) | Responsabilidade |
|---|---|
| `extraction/` | Extração com Docling, detecção de camada de texto por página, OCR seletivo e limpeza |
| `segmentation/` | Segmentador semântico (padrão) e segmentador ingênuo por tokens |
| `translation/` | Cliente Ollama, prompt versionado, glossário, placeholders e validador |
| `assembly/` | Montagem incremental do Markdown com blocos preservados e tabelas |
| `checkpoint/` | Persistência atômica (manifest + trechos) e retomada |
| `export/` | Exportadores MD, PDF e EPUB e conversor entre formatos |
| `ui/` | Janela PySide6; o pipeline roda num `QThread` e a UI nunca congela |
| `config.py` · `logging_setup.py` | Leitura/validação das configurações; logs rotativos em `logs/` com tempo por etapa |

**Stack:** Python 3.12 + `uv` · PySide6 · Docling (backend Tesseract) · Ollama com `qwen2.5:7b-instruct` Q4_K_M · `pypandoc-binary` · `typst` · `epubcheck` · pytest + pytest-qt · ruff.

## Isolamento

Nada é escrito em `~/.config`, `~/.ollama`, `~/.cache`, `/tmp` ou em diretórios do sistema. As únicas dependências externas são o driver NVIDIA/CUDA e o Tesseract.

| Pasta | Conteúdo |
|---|---|
| `.venv/` | Ambiente Python |
| `bin/`, `lib/` | Ollama e suas bibliotecas, JRE portátil, `epubcheck`, `tessdata` (quando necessário) |
| `models/` | Modelos do Ollama (`OLLAMA_MODELS`) |
| `.cache/` | Checkpoints, saídas intermediárias, cache do Hugging Face/uv e `TMPDIR` |
| `logs/` | Logs da aplicação e do Ollama |
| `config/` | `settings.toml`, `glossario.yaml` e `state.json` (última pasta usada, não versionado) |

`./scripts/audit_isolation.sh` compara snapshots de `$HOME` e `/tmp` antes e depois de `setup.sh` + uma tradução completa e reprova se algo mudar fora do projeto.

## Desempenho medido

Medido em 30/09/2026 numa NVIDIA RTX 4060 Laptop (8 GB), com o modelo padrão:

| Métrica | Resultado | Meta |
|---|---|---|
| PDF de 100 páginas (`book_100p.pdf`) | 4,63 min (2,78 s/página) | ≤ 50 min · ≤ 30 s/página |
| OCR (`scanned.pdf`) | 1,87 s/página | ≤ 5 s/página |
| Pico de RAM (100 / 1000 páginas) | 3,23 GB / 3,17 GB | ≤ 8 GB |
| VRAM do modelo no Ollama | 4,65 GB (pico de 5,99 GB sob carga) | ≤ 7 GB |

A tradução pelo LLM responde por cerca de 96% do tempo total. Para reproduzir:

```bash
uv run python scripts/benchmark.py tests/fixtures/book_100p.pdf   # relatório em logs/
```

## Desenvolvimento

```bash
uv run pytest            # testes rápidos (padrão; LLM simulado pela fixture fake_llm)
uv run pytest -m slow    # integração com Ollama real, offline e clone limpo
uv run ruff check
uv run ruff format
```

- Os PDFs de teste em `tests/fixtures/` são gerados a partir de fontes Typst versionadas (`tests/fixtures/sources/*.typ`) por `tests/fixtures/build_fixtures.py`.
- `scripts/gen_big_pdf.py` gera PDFs sintéticos grandes para testes de memória.
- Convenções: código, comentários e logs em inglês; textos da interface em pt-BR; dependências via `uv add`; um commit por tarefa com Conventional Commits. Detalhes em [`AGENTS.md`](./AGENTS.md).

## Limitações

- O idioma de destino é só pt-BR.
- O conteúdo de tabelas e imagens não é traduzido (é mantido original de propósito).
- Não é possível editar o texto traduzido dentro do aplicativo.
- Suporta só Linux; sem GPU, as metas de desempenho não valem.
