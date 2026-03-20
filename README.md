# PR Review AI Agent

Projeto acadêmico da disciplina **IA Generativa para Engenharia de Software**.

O objetivo é desenvolver um agente de IA capaz de analisar trechos de código (simulando um Pull Request) e fornecer sugestões de melhoria, identificação de problemas e boas práticas.

## Funcionalidades

- **Análise heurística** de riscos comuns (TODO/FIXME pendentes, `eval/exec`, secrets hardcoded, `except` genérico, funções gigantes, `print` de debug).
- **Governança configurável** via `blueprint.md`, limitando quantidade de achados, severidades válidas e categorias permitidas.
- **Interface Streamlit** (`app.py`) para colar ou fazer upload de arquivos e visualizar os achados com métricas e próximos passos.
- **Exportação em JSON** do relatório completo para integração futura com pipelines de CI.

## Arquitetura

```
pr-review-ai-agent
├── app.py            # Front-end em Streamlit
├── agent_core.py     # Heurísticas e agregação das respostas
├── validators.py     # Carrega/valida regras definidas no blueprint
├── blueprint.md      # Regras de governança e template de resposta
├── requirements.txt
└── README.md
```

- `agent_core.py` expõe `analyze_code_snippet` (um arquivo) e `analyze_pull_request` (vários arquivos) retornando um `AnalysisReport` com resumo, achados, próximos passos e estado de governança.
- `validators.py` interpreta os metadados do blueprint e garante que os achados respeitem os limites definidos (categorias, severidade, quantidade máxima).
- `app.py` encapsula o fluxo em uma UI: entrada de código, chamada ao core, renderização de métricas, achados e governança.

## Como executar

1. Crie e ative um ambiente virtual (opcional mas recomendado):

```pwsh
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Instale as dependências:

```pwsh
pip install -r requirements.txt
```

3. Rode a interface Streamlit:

```pwsh
streamlit run app.py
```

Cole um trecho no campo de texto ou envie um arquivo. Ajuste o caminho do `blueprint.md` na barra lateral caso personalize as regras.

## Configurando a variável `API_KEY`

1. Gere a chave no provedor desejado (ex.: [OpenAI](https://platform.openai.com/) ou [Gemini](https://aistudio.google.com/app/apikey)).
2. Defina a variável de ambiente antes de iniciar o Streamlit:

```pwsh
setx API_KEY "seu-token"
$Env:API_KEY = "seu-token"  # mantém na sessão atual
```

Em sistemas Unix/macOS use:

```bash
export API_KEY="seu-token"
```

3. Opcionalmente, crie um arquivo `.env` na raiz contendo `API_KEY=seu-token`. O app já executa `python-dotenv` automaticamente (`app.py` e `agent_core.py` chamam `load_dotenv()`), então as variáveis ficam disponíveis assim que você iniciar o Streamlit ou qualquer script que importe esses módulos.

A aplicação não envia chamadas à API por padrão, mas a variável já fica disponível para futuras integrações no `agent_core.py` ou em novos serviços.

## Governança

- `blueprint.md` define missão, formato da resposta e limites (máx. 5 achados, severidades válidas e categorias permitidas).
- Os metadados no topo (`<!-- blueprint:... -->`) são lidos automaticamente pelos validadores para sincronizar regras sem alterar código.
- As respostas exibem o status de governança e eventuais pendências (ex.: número de achados acima do limite, severidade inválida etc.).

## Testes rápidos

O projeto ainda usa heurísticas simples, mas já é possível validar a integridade dos módulos com:

```pwsh
pytest
```

> Caso ainda não existam testes personalizados, o comando conferirá se os arquivos podem ser importados corretamente.

## Próximos passos

- Integrar um LLM (OpenAI ou similar) para gerar insights mais sofisticados usando o `AnalysisReport` como contexto fixo.
- Adicionar Docker/Docker Compose para facilitar execuções em laboratório.
- Conectar a ferramenta a um repositório Git real para analisar diffs automaticamente.