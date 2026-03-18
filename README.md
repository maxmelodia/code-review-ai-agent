# PR Review AI Agent

Projeto acadêmico da disciplina **IA Generativa para Engenharia de Software**.

O objetivo é desenvolver um agente de IA capaz de analisar trechos de código (simulando Pull Requests) e fornecer sugestões de melhoria, identificação de problemas e boas práticas.

## Proposta

O sistema recebe um código como entrada e utiliza um modelo de IA para:

- identificar possíveis bugs  
- apontar problemas de segurança  
- sugerir melhorias de código  
- aplicar boas práticas de desenvolvimento  

Além disso, o agente terá um mecanismo de governança baseado em um arquivo `blueprint.md`, que define regras de comportamento e validação das respostas.

## Estrutura inicial

pr-review-ai-agent
│
├── app.py
├── agent_core.py
├── validators.py
├── blueprint.md
├── requirements.txt
└── README.md

## Tecnologias previstas

- Python  
- Streamlit  
- API de IA (OpenAI ou similar)  
- Docker / Docker Compose  

## Status

Em desenvolvimento.