# Omnisearch MCP

Servidor [Model Context Protocol (MCP)](https://modelcontextprotocol.io) para agentes LLM pesquisarem literatura acadêmica, resolverem PDFs open-access, baixarem/lerem papers e pesquisarem bibliotecas locais de PDFs.

## Fontes suportadas

- IEEE Xplore via API oficial ou CAPES/CAFe proxy + cookies persistidos
- arXiv
- ACM Digital Library metadata via CrossRef
- CrossRef
- Semantic Scholar
- CORE
- Scite.ai
- Consensus.app
- Unpaywall para resolver PDFs open-access por DOI
- PDF local: indexação, busca e extração de texto

## Instalação

```bash
git clone https://github.com/all3yp/omnisearch-mcp
cd omnisearch-mcp
uv sync
uv run playwright install chromium
cp .env.example .env
```

Edite `.env` conforme necessário:

```env
CONTACT_EMAIL=seu-email@example.com
SEMANTIC_SCHOLAR_API_KEY=
CORE_API_KEY=
IEEE_XPLORE_API_KEY=

CAFE_INSTITUTION_ID=
CAFE_USERNAME=
CAFE_PASSWORD=
SCITE_EMAIL=
SCITE_PASS=
CONSENSUS_EMAIL=
CONSENSUS_PASS=
PLAYWRIGHT_BROWSER_PATH=
```

## Comandos para usuário humano

### Rodar servidor MCP

```bash
uv run omnisearch-mcp
```

### Login e persistência de sessão

Recomendado: rode em modo visível na primeira vez, principalmente CAPES/IEEE, para completar MFA/CAPTCHA/SSO se aparecer.

```bash
uv run omnisearch-login-all
uv run omnisearch-capes-login
uv run omnisearch-scite-login
uv run omnisearch-consensus-login
```

Depois que funcionar visivelmente, você pode tentar headless:

```bash
uv run omnisearch-login-all --headless
uv run omnisearch-capes-login --headless
uv run omnisearch-scite-login --headless
uv run omnisearch-consensus-login --headless
```

Os scripts salvam:

- estado do navegador em `.omnisearch/sessions/*.storage.json`;
- cookies derivados no `.env` para os adapters HTTP.

Esses arquivos contêm segredos de sessão e são ignorados pelo Git.

### Testes

```bash
uv run --group dev pytest
```

Se o `uv` falhar no Git Bash/Windows por trampoline, use:

```bash
/c/Users/alley/Code/alley/python/omnisearch-mcp/.venv/Scripts/python.exe -m pytest tests/ -v --tb=short
```

## Como configurar no Claude Code

Na raiz do projeto, adicione o MCP ao Claude Code:

```bash
claude mcp add omnisearch-mcp -- uv run omnisearch-mcp
```

Ou use configuração JSON equivalente:

```json
{
  "mcpServers": {
    "omnisearch-mcp": {
      "command": "uv",
      "args": ["run", "omnisearch-mcp"],
      "cwd": "C:/Users/alley/Code/alley/python/omnisearch-mcp"
    }
  }
}
```

Depois reinicie/recarregue o Claude Code e use ferramentas como:

- `search_all`
- `search_ieee`
- `resolve_oa_url`
- `download_paper`
- `read_paper_content`
- `index_pdf_library`
- `search_pdf_library`

## Como configurar no Codex / OpenAI Codex CLI

Adicione o servidor MCP no arquivo de configuração do Codex com o comando abaixo:

```toml
[mcp_servers.omnisearch-mcp]
command = "uv"
args = ["run", "omnisearch-mcp"]
cwd = "C:/Users/alley/Code/alley/python/omnisearch-mcp"
```

Se seu cliente Codex usar JSON em vez de TOML, use:

```json
{
  "mcpServers": {
    "omnisearch-mcp": {
      "command": "uv",
      "args": ["run", "omnisearch-mcp"],
      "cwd": "C:/Users/alley/Code/alley/python/omnisearch-mcp"
    }
  }
}
```

## Ferramentas MCP principais

| Tool | Uso |
|---|---|
| `search_all(query, max_results_each=5)` | Busca em todas as fontes, preserva seções por fonte e retorna `papers` deduplicado + `total`. |
| `search_ieee(query, max_results=10)` | Busca IEEE por API key ou sessão CAPES/IEEE. A busca via navegador pagina os resultados até atingir `max_results` ou esgotar a busca. |
| `search_arxiv(query, max_results=10)` | Busca arXiv aberta com retry para rate-limit. |
| `search_acm(query, max_results=10)` | Busca ACM via CrossRef metadata. |
| `search_crossref(query, max_results=10)` | Busca CrossRef. |
| `search_semantic_scholar(query, max_results=10)` | Busca Semantic Scholar com retry para 429. |
| `search_core(query, max_results=10)` | Busca CORE; requer `CORE_API_KEY`. |
| `search_scite(query, max_results=10)` | Busca Scite; requer sessão/cookies. |
| `search_consensus(query, max_results=10)` | Busca Consensus; requer sessão/cookies. |
| `get_doi_metadata(doi)` | Normaliza metadata CrossRef por DOI. |
| `resolve_oa_url(doi)` | Resolve PDF open-access via Unpaywall. |
| `download_paper(doi, title='', pdf_url=None, save_path='./downloads', use_scihub=False)` | Baixa PDF por fallback: URL direta → Unpaywall → CORE → Sci-Hub opcional. |
| `read_paper_content(...)` | Baixa paper e extrai texto do PDF. |
| `index_pdf_library(folder_path, force=False)` | Indexa PDFs locais. |
| `search_pdf_library(folder_path, query, ...)` | Pesquisa texto em PDFs indexados. |
| `read_pdf_text(path, max_chars=20000)` | Extrai texto de PDF local. |

## Como a busca IEEE/CAPES funciona

O login CAPES abre navegador via CloakBrowser/Playwright, persiste `storage_state` e deriva cookies HTTP.

Antes de salvar, o script CAPES valida a sessão com uma busca real:

```text
POST {CAPES_PROXY_URL}/rest/search
```

Payload mínimo:

```json
{
  "newsearch": true,
  "queryText": "machine learning",
  "returnType": "SEARCH",
  "rowsPerPage": 1
}
```

Só salva se o endpoint retornar JSON compatível com IEEE. Se receber HTML/login/401/403/redirect, não salva e pede relogin humano.

Quando não há `IEEE_XPLORE_API_KEY`, o adapter `search_ieee` usa uma sessão CAPES/IEEE persistida no navegador. Ele seleciona até 50 itens por página e avança pelas páginas até atingir `max_results` ou esgotar os resultados da IEEE.

## Skill para agentes consumidores

Agentes que usam este MCP devem seguir [`.github/skills/omnisearch-mcp/SKILL.md`](.github/skills/omnisearch-mcp/SKILL.md). A skill documenta o contrato das tools, limites por fonte, formato dos resultados, autenticação e a responsabilidade do agente chamador por qualquer síntese ou saída estruturada.

## Instruções para agentes quando auth falhar

Se uma tool retornar `auth_required: true`:

1. **Pare de tentar a mesma busca em loop.**
2. Leia `provider`, `command` e `agent_instruction`.
3. Peça ao humano para rodar o comando indicado.
4. Aguarde o humano confirmar que o login terminou.
5. Tente a tool novamente **uma vez**.
6. Se falhar de novo, reporte bloqueio de autenticação e use fontes públicas se possível.

Exemplo de resposta de auth:

```json
{
  "auth_required": true,
  "provider": "ieee",
  "action": "human_relogin_required",
  "command": "uv run omnisearch-capes-login --headless",
  "agent_instruction": "Stop retrying this provider. Ask the human to run the command, wait for login completion, then retry the same tool once.",
  "results": []
}
```

Para `search_all`, veja também:

```json
{
  "auth_required_sources": ["ieee", "scite", "consensus"],
  "agent_instruction": "For sources in auth_required_sources, do not retry in a loop..."
}
```

### Prioridade de relogin

1. CAPES/IEEE: `uv run omnisearch-capes-login` em modo visível é o caminho mais confiável.
2. Scite: `uv run omnisearch-scite-login`.
3. Consensus: `uv run omnisearch-consensus-login`.

## Notas de segurança

- `.env`, `.omnisearch/` e `*.storage.json` contêm segredos de sessão.
- Não imprima cookies, storage state, senhas ou tokens em logs/prompts.
- `use_scihub` é `False` por padrão. Use apenas quando você tiver direito legítimo de acesso ao paper e aceitar o risco legal local.

## Créditos

Fork ampliado de [ieee-research-mcp](https://github.com/kevinzhao-tech/ieee-research-mcp), criado por Kevin Zhao.
