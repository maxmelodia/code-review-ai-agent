# PR Review AI Agent

Projeto acadêmico da disciplina **IA Generativa para Engenharia de Software**. A aplicação oferece uma interface em Streamlit para revisar trechos de código ou um conjunto de arquivos simulando um Pull Request, combinando heurísticas locais, validação por regras de governança e apoio opcional de LLM.

## Objetivo

O objetivo do projeto é demonstrar uma arquitetura de revisão de código assistida por IA em que as regras de governança ficam externalizadas em um arquivo Markdown. Com isso, critérios de severidade, categorias permitidas, limites de achados e diretrizes de resposta podem ser ajustados sem alteração do código Python da aplicação.

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
├── docker-compose.yml     # Execução portável com blueprint montado como volume
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

Esse é o fluxo mais direto para executar o projeto em container:

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
- Nesse fluxo, o `blueprint.md` fica embutido na imagem criada no build.

## Como rodar com Docker Compose

Este é o fluxo recomendado para demonstração acadêmica do requisito de governança portável.

Para atender ao requisito de governança portável, o projeto agora possui [`docker-compose.yml`](/home/maxmelodia/PUC/IA/code-review-ai-agent/docker-compose.yml) com montagem explícita do blueprint como volume.

Suba a aplicação com:

```bash
docker compose up --build
```

Ou em background:

```bash
docker compose up --build -d
```

Depois disso, acesse:

```text
http://localhost:8501
```

### O que o Compose garante

- build padronizado da imagem a partir do [`Dockerfile`](/home/maxmelodia/PUC/IA/code-review-ai-agent/Dockerfile)
- carregamento das variáveis do arquivo `.env`
- publicação da porta `8501`
- montagem de [`blueprint.md`](/home/maxmelodia/PUC/IA/code-review-ai-agent/blueprint.md) em `/app/blueprint.md` dentro do container

Trecho principal da configuração:

```yaml
services:
  pr-review-agent:
    build:
      context: .
    ports:
      - "8501:8501"
    env_file:
      - .env
    volumes:
      - ./blueprint.md:/app/blueprint.md:ro
```

O volume foi configurado como `read-only` para manter o blueprint controlado no host e evitar modificações acidentais a partir do container.

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

Se nenhuma chave estiver configurada, ou se a chamada ao LLM falhar, a aplicação continua funcionando com as **heurísticas locais**, preservando a execução da demonstração.

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

O arquivo [`blueprint.md`](/home/maxmelodia/PUC/IA/code-review-ai-agent/blueprint.md) é parte central do projeto. Ele não atua apenas como documentação: seu conteúdo é lido e aplicado em tempo de execução por [`validators.py`](/home/maxmelodia/PUC/IA/code-review-ai-agent/validators.py) e também compõe o prompt enviado ao LLM.

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
- O texto completo do blueprint também é enviado ao LLM a cada análise, influenciando o comportamento do agente sem alterar o código Python.

### Troca do blueprint

Na interface, o usuário pode informar outro caminho no campo `Blueprint`. Se o arquivo não existir, a aplicação exibe erro.

### Demonstração da governança portável

Com o Compose, o [`blueprint.md`](/home/maxmelodia/PUC/IA/code-review-ai-agent/blueprint.md) não depende de rebuild para surtir efeito. O container lê `/app/blueprint.md`, que está apontando para o arquivo do host montado como volume.

Fluxo recomendado para demonstrar isso:

1. Suba a aplicação com `docker compose up --build`.
2. Execute uma análise e observe as severidades, categorias e limite de achados.
3. Edite o [`blueprint.md`](/home/maxmelodia/PUC/IA/code-review-ai-agent/blueprint.md) no host.
4. Altere, por exemplo, `max-findings`, categorias permitidas ou a redação das diretrizes de segurança.
5. Rode uma nova análise sem rebuildar a imagem e sem mudar o código Python.

Resultado esperado:

- as regras validadas por [`validators.py`](/home/maxmelodia/PUC/IA/code-review-ai-agent/validators.py) mudam na próxima análise executada
- o prompt enviado ao LLM passa a refletir o novo conteúdo do blueprint
- o comportamento do agente muda sem alteração nas chamadas de API nem no código da aplicação

### Teste prático de hot-reload do blueprint

O teste abaixo demonstra, de forma objetiva, que a governança foi externalizada no Markdown e que o comportamento do agente muda sem rebuild da imagem.

#### 1. Suba a aplicação

```bash
docker compose up --build
```

Abra a interface em:

```text
http://localhost:8501
```

#### 2. Use este código de teste

No modo `Arquivo único`, cole o snippet abaixo:

```python
def insecure_process(user_input, items=[]):
    # TODO: remover antes do merge
    api_key = "1234567890ABCDEFSECRET"
    print("processando", user_input)

    try:
        query = f"SELECT * FROM users WHERE id = {user_input}"
        result = eval(user_input)
        value = 10 / 0
        if user_input == None:
            print("entrada nula")
        if "x" is "x":
            print("comparacao incorreta")
        return result
    except Exception:
        pass
```

Esse exemplo foi escolhido porque tende a gerar múltiplos achados no projeto atual, como:

- `TODO`
- secret hardcoded
- `print`
- `eval`
- divisão por zero
- comparação com `None` usando `==`
- uso incorreto de `is`
- `except Exception`
- argumento mutável como default

#### 3. Rode a análise com o blueprint original

Com o valor padrão atual:

```html
<!-- blueprint:max-findings=5 -->
```

o resultado esperado é um relatório com até `5` achados, priorizados por severidade.

#### 4. Altere o blueprint sem parar o container

No arquivo [`blueprint.md`](/home/maxmelodia/PUC/IA/code-review-ai-agent/blueprint.md), altere:

```html
<!-- blueprint:max-findings=5 -->
```

para:

```html
<!-- blueprint:max-findings=2 -->
```

Salve o arquivo.

#### 5. Rode a mesma análise novamente

Sem alterar o código de teste e sem rebuildar a imagem, clique em analisar de novo.

Resultado esperado:

- antes da mudança: até `5` achados
- depois da mudança: no máximo `2` achados
- o bloco de governança passa a refletir o novo limite configurado

#### 6. Por que não é necessário executar `docker compose` novamente

Não é necessário reiniciar o Compose nesse cenário porque o [`docker-compose.yml`](/home/maxmelodia/PUC/IA/code-review-ai-agent/docker-compose.yml) monta o arquivo do host diretamente dentro do container:

```yaml
volumes:
  - ./blueprint.md:/app/blueprint.md:ro
```

Isso significa que:

- o container não usa uma cópia isolada do blueprint
- ele enxerga o arquivo montado a partir do diretório do projeto
- ao salvar mudanças no `blueprint.md`, o conteúdo disponível em `/app/blueprint.md` muda imediatamente

Além disso, o código da aplicação relê o blueprint a cada nova análise, em vez de carregar as regras apenas na inicialização. Por isso, basta editar o Markdown e executar uma nova análise na interface para observar o efeito da mudança.

Em outras palavras, o projeto implementa um hot-reload funcional das regras de governança: o arquivo é atualizado no host, refletido no container pelo volume montado e reaplicado pelo sistema na próxima execução da análise.

Você só precisa rodar `docker compose up --build` novamente se mudar:

- o [`Dockerfile`](/home/maxmelodia/PUC/IA/code-review-ai-agent/Dockerfile)
- o próprio [`docker-compose.yml`](/home/maxmelodia/PUC/IA/code-review-ai-agent/docker-compose.yml)
- dependências do projeto
- código da aplicação que precise ser reconstruído dentro da imagem

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
