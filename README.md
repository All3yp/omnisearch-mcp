# Omnisearch MCP (based on ieee-research-mcp)

Um servidor [Model Context Protocol (MCP)](https://modelcontextprotocol.io) projetado para que agentes LLM (como Claude, Copilot, Cursor, etc.) possam pesquisar literatura acadêmica de forma unificada através de múltiplas fontes, além de permitir indexação local de PDFs.

## 🚀 Fontes Suportadas

Atualmente, o servidor busca simultaneamente em 7 bases de dados:
1. **IEEE Xplore**
2. **arXiv**
3. **ACM Digital Library** (via CrossRef)
4. **Semantic Scholar**
5. **CORE (core.ac.uk)**
6. **Scite.ai**
7. **Consensus.app**

Além disso, possui ferramentas para ler e pesquisar dentro da sua **biblioteca local de PDFs**.

---

## 🛠 Instalação

O projeto requer Python 3.12+ e o gerenciador de pacotes [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/all3yp/omnisearch-mcp
cd omnisearch-mcp

# 1. Instalar dependências (incluindo o Playwright)
uv sync

# 2. Instalar navegadores necessários para a automação de login
uv run playwright install chromium

# 3. Preparar o arquivo de ambiente
cp .env.example .env
```

---

## 🔐 Configuração e Login Automático

Muitas plataformas cobram por acesso a APIs oficiais ou barram o conteúdo completo. Para contornar isso e buscar metadados de forma eficiente, este projeto utiliza as próprias sessões logadas do seu navegador para injetar cookies nas ferramentas de busca (Scite, Consensus e IEEE via proxy CAPES CAFe).

### Usando os Scripts de Login (Cookies)

Disponibilizamos comandos interativos para você fazer login facilmente e salvar os cookies de acesso automaticamente no seu arquivo `.env`:

* **Todas as Plataformas (CAPES + Scite + Consensus em sequência):**
  ```bash
  uv run omnisearch-login-all
  ```
* **CAPES / IEEE Xplore:**
  ```bash
  uv run omnisearch-capes-login
  ```
* **Scite.ai:**
  ```bash
  uv run omnisearch-scite-login
  ```
* **Consensus.app:**
  ```bash
  uv run omnisearch-consensus-login
  ```

**Execução do servidor**

```bash
uv run omnisearch-mcp
```

**Execução dos testes unitários**
```bash
uv run pytest --cov=src/omnisearch_mcp --cov-report=term-missing
```

> **Como funciona:** O script abrirá uma janela do navegador. Basta realizar o seu login normalmente na plataforma. Assim que você for autenticado, a janela será fechada sozinha e o seu arquivo `.env` será atualizado com os cookies capturados da sessão!

*Dica: Após o primeiro login, caso deseje automatizar em segundo plano, você pode tentar passar a flag `--headless` no comando.*

### APIs Oficiais (Tokens)

Para as ferramentas que possuem APIs abertas e oficiais, você pode adicionar a chave diretamente editando o arquivo `.env`:
- `SEMANTIC_SCHOLAR_API_KEY`: Chave da API do Semantic Scholar (opcional, mas evita rate-limit).
- `CORE_API_KEY`: Chave da API v3 do CORE (obtida gratuitamente no [site deles](https://core.ac.uk/services/api/)).
- `IEEE_XPLORE_API_KEY`: Chave oficial do IEEE (opcional caso esteja utilizando o login da CAPES/proxy).

---

## 🤖 Ferramentas MCP (Tools) Disponíveis

| Ferramenta | Descrição | Requisitos de Autenticação |
|------------|-------------|----------------------------|
| `search_all` | Busca simultânea em todas as 7 bases (IEEE, arXiv, ACM, S2, CORE, Scite, Consensus). | Recomendado rodar os scripts de login |
| `search_ieee` | Busca no IEEE Xplore. | Login CAPES (`omnisearch-capes-login`) ou API Key |
| `search_scite` | Busca smart citations no Scite.ai. | Login Scite (`omnisearch-scite-login`) |
| `search_consensus` | Busca de papers no Consensus.app. | Login Consensus (`omnisearch-consensus-login`) |
| `search_semantic_scholar` | Busca no Semantic Scholar (Graph API). | Opcional API Key |
| `search_core` | Busca no CORE v3. | Necessário CORE API Key |
| `search_arxiv` | Busca aberta no arXiv. | Nenhum |
| `search_acm` / `search_crossref` | Busca de metadados no CrossRef/ACM. | Nenhum |
| `index_pdf_library` | Lê seus PDFs locais e extrai textos para cache. | Caminho Local |
| `search_pdf_library` | Pesquisa por trechos dentro dos seus PDFs locais. | Caminho Local |

---

## 💻 Uso com Clientes (Cursor, Claude, etc.)

Adicione o servidor nas configurações do seu cliente MCP apontando para o comando de inicialização deste diretório:

```json
{
  "mcpServers": {
    "omnisearch-mcp": {
      "command": "uv",
      "args": ["run", "omnisearch-mcp"],
      "env": {},
      "cwd": "/caminho/absoluto/para/este/projeto/omnisearch-mcp"
    }
  }
}
```

---

## 📜 Créditos

Este projeto é um fork ampliado e modificado do projeto original [ieee-research-mcp](https://github.com/kevinzhao-tech/ieee-research-mcp) criado por **Kevin Zhao**. A base do servidor e as integrações originais com IEEE, arXiv e CrossRef são creditadas ao trabalho inicial dele.
