# PR Review AI Agent

Projeto acadêmico da disciplina **IA Generativa para Engenharia de Software**. A aplicação oferece uma interface em Streamlit para revisar trechos de código ou um conjunto de arquivos simulando um Pull Request, combinando heurísticas locais com apoio opcional de LLM.

## O que o projeto faz

- Analisa código de **arquivo único** ou de **múltiplos arquivos**.
- Detecta problemas comuns com heurísticas locais.
- Tenta complementar a análise com **Gemini** e, se não estiver disponível, faz fallback para **OpenAI**.
- Aplica regras de governança definidas em [`blueprint.md`](/home/maxmelodia/PUC/IA/code-review-ai-agent/blueprint.md).
- Exibe o relatório na UI com:
  - resumo da análise
  - achados com severidade, categoria, linha e sugestão
  - estatísticas básicas
  - próximos passos
  - status de governança
  - exportação em JSON e Markdown

## Arquitetura

```text
pr-review-ai-agent
├── app.py                 # Interface Streamlit
├── agent_core.py          # Heurísticas, integração com LLM e agregação do relatório
├── validators.py          # Leitura e validação das regras do blueprint
├── blueprint.md           # Contrato de governança e instruções de saída
├── tests/test_agent_core.py
├── requirements.txt
└── Dockerfile
```

## Tecnologias

- Python 3
- Streamlit
- python-dotenv
- OpenAI SDK
- Google GenAI SDK
- Pytest

## Como rodar com Docker

Esse é o fluxo mais direto para executar o projeto:

```bash
docker build -t pr-review-agent .
docker run -p 8501:8501 --env-file .env pr-review-agent
```

Depois disso, acesse:

```text
http://localhost:8501
```

### Observações sobre o Docker

- O container expõe a porta `8501`.
- O comando de inicialização já está definido no [`Dockerfile`](/home/maxmelodia/PUC/IA/code-review-ai-agent/Dockerfile): o app sobe com `streamlit run app.py --server.port=8501 --server.address=0.0.0.0`.
- O arquivo `.env` é carregado no container via `--env-file .env`.

## Como rodar localmente

1. Crie e ative um ambiente virtual:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Instale as dependências:

```bash
pip install -r requirements.txt
```

3. Execute a aplicação:

```bash
python -m streamlit run app.py
```

Se quiser fixar host e porta:

```bash
python -m streamlit run app.py --server.port=8501 --server.address=0.0.0.0
```

## Variáveis de ambiente

O projeto usa `load_dotenv()`, então um arquivo `.env` na raiz já é suficiente para disponibilizar as chaves para a aplicação.

Variáveis suportadas pelo código:

- `GEMINI_API_KEY`
- `GEMINI_MODEL` (opcional, padrão: `gemini-2.0-flash`)
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (opcional, padrão: `gpt-4o-mini`)

### Prioridade dos provedores

No core, a ordem de tentativa é:

1. Gemini
2. OpenAI

Se nenhuma chave estiver configurada, ou se a chamada ao LLM falhar, a aplicação continua funcionando com as **heurísticas locais**.

## Heurísticas implementadas

Atualmente o projeto detecta, entre outros padrões:

- `TODO` e `FIXME`
- credenciais hardcoded
- uso de `eval` e `exec`
- SQL possivelmente vulnerável a injeção
- `except` genérico
- funções muito longas
- `print` em Python
- divisão por zero
- acesso inválido a coleção vazia
- argumento mutável como valor default
- uso incorreto de `is`
- comparação com `None` usando `==`
- variável não utilizada
- `while True` sem saída aparente
- uso incorreto de retorno `None`
- placeholders inconsistentes em `.format()`
- uso de módulos sem import
- arquivo aberto sem `with`
- `var`, `==` e `console.log` em JavaScript/TypeScript
- erro ignorado em Go

Linguagens previstas na interface:

- Python
- JavaScript
- TypeScript
- Go

## Blueprint e governança

O arquivo [`blueprint.md`](/home/maxmelodia/PUC/IA/code-review-ai-agent/blueprint.md) é parte central do projeto. Ele não é apenas documentação: ele define regras que são lidas e aplicadas em tempo de execução por [`validators.py`](/home/maxmelodia/PUC/IA/code-review-ai-agent/validators.py).

### O que o blueprint controla

- severidades válidas
- categorias permitidas
- quantidade máxima de achados
- formato esperado da resposta do LLM
- regras de conteúdo e priorização

### Metadados lidos automaticamente

No topo do blueprint existem metadados em comentário HTML:

```html
<!-- blueprint:severity-levels=Critical,High,Medium,Low,Info -->
<!-- blueprint:max-findings=5 -->
<!-- blueprint:required-categories=bug-risk,security,best-practice -->
```

Esses valores são carregados automaticamente pela função `load_blueprint_rules()`.

### Efeito prático na análise

- Achados fora das categorias permitidas são descartados.
- Achados com severidade inválida são rejeitados na validação.
- O total final é limitado por `max-findings`.
- O relatório inclui um bloco de governança com `is_compliant`, `issues` e `limits`.

### Troca do blueprint

Na interface, o usuário pode informar outro caminho no campo `Blueprint`. Se o arquivo não existir, a aplicação exibe erro.

## Como usar a interface

### Modo Arquivo único

- Cole código diretamente no campo de texto; ou
- envie um arquivo `.py`, `.js`, `.ts`, `.go` ou `.yaml`

A interface mostra:

- o código com destaque nas linhas problemáticas
- os achados filtráveis por severidade e categoria
- estatísticas do arquivo
- próximos passos
- exportação do relatório

### Modo Múltiplos arquivos (PR)

- Envie vários arquivos de uma vez
- Cada arquivo é analisado individualmente
- O app consolida o resultado em um resumo geral do PR

## Estrutura do relatório

O core expõe duas entradas principais:

- `analyze_code_snippet(...)`
- `analyze_pull_request(...)`

O relatório de arquivo único retorna um `AnalysisReport` com:

- `summary`
- `findings`
- `governance`
- `statistics`
- `next_steps`

Também existe exportação em Markdown com `report.to_markdown()` e em dicionário com `report.to_dict()`.

## Testes

Para executar os testes:

```bash
pytest
```

Os testes atuais cobrem cenários básicos do core, incluindo:

- detecção de `TODO`
- conformidade com a governança
- comportamento quando não há problemas relevantes

## Comportamentos importantes do projeto

- O app funciona mesmo sem LLM, usando apenas heurísticas.
- O campo `reference` dos achados é preenchido com o nome do arquivo quando disponível.
- Quando não há achados, o core adiciona uma observação informativa ao relatório.
- Os próximos passos são gerados com base nas categorias encontradas.

## O que foi removido desta documentação

As instruções antigas usando apenas `API_KEY` foram removidas porque **não correspondem ao código atual**. Hoje o projeto espera explicitamente `GEMINI_API_KEY` e/ou `OPENAI_API_KEY`.
