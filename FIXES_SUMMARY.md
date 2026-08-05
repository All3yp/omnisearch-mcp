# Correções e Novas Features - omnisearch-mcp

## Resumo Executivo
**6 bugs corrigidos** + **3 novas features portadas do paper-search-mcp**  
**47 testes → 63 testes** (+16 novos testes cobrindo features)

---

## Parte 1: Correções de Bugs (6 issues)

### 🔴 Bug Crítico
**#1 - `json` não importado em scite.py**
- **Problema:** `json.JSONDecodeError` causava `NameError` ao invés de `SciteAuthMissingError`
- **Arquivo:** `src/omnisearch_mcp/sources/scite.py:1`
- **Fix:** Adicionado `import json` no topo

### 🟡 Bugs Funcionais
**#2 - CORE não seguia redirects**
- **Problema:** HTTP 301 não tratado (httpx não segue redirects por padrão)
- **Arquivo:** `src/omnisearch_mcp/sources/core.py:59`
- **Fix:** `httpx.AsyncClient(follow_redirects=True)`

**#3 - Semantic Scholar sem retry para 429**
- **Problema:** Rate-limiting (429) falhava imediatamente
- **Arquivo:** `src/omnisearch_mcp/sources/semantic_scholar.py:48`
- **Fix:** Retry com backoff exponencial (máx 3 tentativas, 2s→4s→8s)

**#4 - arXiv sem retry para 429/503**
- **Problema:** Rate-limiting sem retry automático
- **Arquivo:** `src/omnisearch_mcp/sources/arxiv.py:55`
- **Fix:** Retry com backoff exponencial (máx 2 tentativas, 3s→6s)

**#5 - Configuração estática em crossref.py e arxiv.py**
- **Problema:** Usavam `CONFIG` importado, não recarregava `.env` dinamicamente
- **Arquivos:** `crossref.py`, `arxiv.py`
- **Fix:** Substituído `CONFIG` por `get_config()` (igual aos outros adapters)

**#6 - search_all sem timeout individual**
- **Problema:** Uma fonte lenta bloqueava todas as outras
- **Arquivo:** `src/omnisearch_mcp/server.py:112`
- **Fix:** `asyncio.wait_for()` com 15s timeout por fonte

---

## Parte 2: Novas Features (portadas do paper-search-mcp)

### 🚀 Feature #1: Deduplicação de Resultados
**Problema:** `search_all` retornava papers duplicados (mesmo DOI em múltiplas fontes)  
**Solução:** Algoritmo de deduplicação por DOI → título+autores → ID

**Arquivos:**
- `src/omnisearch_mcp/utils.py` (novo) - `extract_doi()`, `dedupe_papers()`, `paper_unique_key()`
- `src/omnisearch_mcp/server.py:173-179` - Integrado ao `search_all`

**Impacto:**
```python
# Antes: 50 results com 15 duplicados
# Depois: 35 results únicos
"papers": deduped_papers,  # Lista deduplicada
"total": 35                # Contagem precisa
```

### 🚀 Feature #2: Unpaywall Integration (Open Access Resolver)
**Problema:** Papers paywalled (IEEE, ACM) não tinham fallback para PDFs open-access  
**Solução:** Resolver Unpaywall encontra versões OA de papers pagos

**Arquivos:**
- `src/omnisearch_mcp/unpaywall.py` (novo) - `UnpaywallResolver` class
- `src/omnisearch_mcp/server.py:195-207` - Novo tool `resolve_oa_url`

**Usage:**
```python
@mcp.tool()
async def resolve_oa_url(doi: str) -> dict:
    """Resolve open-access PDF URL for a DOI using Unpaywall."""
    # Retorna: {"url": "https://...", "source": "unpaywall"}
```

**Config:** Usa `CONTACT_EMAIL` do `.env` (já existente)

### 🚀 Feature #3: Download com Fallback Chain
**Problema:** Não havia tool para baixar PDFs automaticamente  
**Solução:** Cascade de download: URL direta → Unpaywall → (futuro: Sci-Hub)

**Arquivos:**
- `src/omnisearch_mcp/downloader.py` (novo) - `download_from_url()`, `download_with_fallback()`
- `src/omnisearch_mcp/server.py:209-223` - Novo tool `download_paper`

**Usage:**
```python
@mcp.tool()
async def download_paper(
    doi: str,
    title: str = "",
    pdf_url: str | None = None,
    save_path: str = "./downloads"
) -> dict:
    """Download PDF with fallback chain."""
    # Retorna: {"path": "./downloads/paper.pdf", "error": None}
```

**Fallback Chain:**
1. Tenta `pdf_url` direto (se fornecido)
2. Fallback para Unpaywall (resolve OA URL via DOI)
3. (Futuro) Sci-Hub como último recurso

---

## Validação

### Testes
- **Antes:** 47 testes
- **Depois:** 63 testes (+16 novos)
- **Coverage:** 100% das novas features testadas
- **Todos passam:** ✅ 63/63 passed in 1.33s

### Clean Code (Robert C. Martin)
**Princípios aplicados:**
- ✅ **G30:** Funções fazem uma coisa só (`extract_doi()`, `dedupe_papers()`)
- ✅ **G25:** Constantes nomeadas (`DOWNLOAD_TIMEOUT`, `PDF_SIGNATURE`)
- ✅ **G19:** Variáveis explicativas (`content_type_lower`, `is_pdf_candidate`)
- ✅ **F1:** Máx 3 argumentos (funções principais)
- ✅ **N1:** Nomes descritivos (`resolve_best_pdf_url`, `paper_unique_key`)
- ✅ **G28:** Condicionais encapsulados (`is_pdf_content()`)
- ✅ **G5:** DRY (helper `safe_filename` reutilizado)

### Breaking Changes
**Nenhum.** Todas as mudanças são aditivas ou correções internas.

---

## Próximos Passos Recomendados

### 🔴 Crítico (para produção)
1. **Renovar cookies expirados:**
   ```bash
   uv run omnisearch-login-all --headless
   ```

2. **Testar features novas:**
   ```python
   # Testar deduplicação
   result = await search_all("machine learning", max_results_each=10)
   print(f"Total único: {result['total']}")
   
   # Testar Unpaywall
   oa = await resolve_oa_url("10.1109/ACCESS.2023.1234567")
   print(f"PDF URL: {oa['url']}")
   
   # Testar download
   pdf = await download_paper(
       doi="10.1109/ACCESS.2023.1234567",
       title="Test Paper",
       save_path="./downloads"
   )
   print(f"Salvo em: {pdf['path']}")
   ```

3. **Monitorar logs para retry behavior:**
   ```bash
   tail -f omnisearch.log | grep -E "(retry|rate-limit)"
   ```

### 🟡 Futuro (Fase 2 do plano)
- **Sci-Hub integration** (último recurso para PDFs paywalled)
- **Leitura de papers** (`read_paper()` com extração de texto)
- **Mais fontes:** PubMed, OpenAlex, Google Scholar (top 5 do paper-search-mcp)

### 🟢 Opcional
- **Enriquecer modelo Paper:** adicionar `citations`, `references`, `categories`
- **Refatorar para classes:** `PaperSource` base class (G23: polimorfismo)
- **Cache de downloads:** evitar re-baixar PDFs já obtidos

---

## Referências
- **paper-search-mcp:** `C:\Users\alley\custom_tools\paper-search-mcp`
- **Clean Code:** Robert C. Martin, Chapter 17
- **Unpaywall API:** https://unpaywall.org/products/api
