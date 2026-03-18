"""Interface Streamlit para o PR Review AI Agent."""
from __future__ import annotations

import json

from dotenv import load_dotenv
import streamlit as st

from agent_core import analyze_code_snippet

load_dotenv()

st.set_page_config(page_title="PR Review AI Agent", layout="wide")
st.title("🔍 PR Review AI Agent")
st.write(
    "Cole um trecho de código ou faça upload de um arquivo pequeno para receber uma revisão simulada."
)

with st.sidebar:
    st.header("Configurações")
    language = st.selectbox("Linguagem", ["python", "javascript", "typescript", "go"], index=0)
    file_path = st.text_input("Nome do arquivo", value="main.py")
    blueprint_path = st.text_input("Blueprint", value="blueprint.md")
    st.caption("O blueprint controla severidade, categorias e limites de governança.")

code_input = st.text_area("Código", height=300, placeholder="Cole aqui o trecho que será analisado...")
file_upload = st.file_uploader("Ou envie um arquivo", type=["py", "js", "ts", "go"])

if file_upload is not None and not code_input:
    code_input = file_upload.read().decode("utf-8")
    file_path = file_upload.name

run_button = st.button("Analisar trecho")

if run_button:
    if not code_input.strip():
        st.warning("Forneça um código antes de rodar a análise.")
    else:
        try:
            report = analyze_code_snippet(
                code_input,
                language=language,
                file_path=file_path or file_upload.name if file_upload else None,
                blueprint_path=blueprint_path,
            )
        except FileNotFoundError as exc:
            st.error(f"Não foi possível carregar o blueprint: {exc}")
        else:
            st.success(report.summary)

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Estatísticas")
                st.metric("Linhas", report.statistics["loc"])
                st.metric("Linhas em branco", report.statistics["blank_lines"])
            with col2:
                st.subheader("Próximos passos")
                for step in report.next_steps:
                    st.markdown(f"- {step}")

            st.subheader("Achados")
            for finding in report.findings:
                severity_tag = f"{finding.severity} / {finding.category}"
                st.markdown(f"**{severity_tag}** — {finding.description}")
                st.markdown(f"💡 {finding.recommendation}")
                if finding.reference:
                    st.caption(f"Referência: {finding.reference}")
                st.markdown("---")

            st.subheader("Governança")
            st.json(report.governance)

            with st.expander("Exportar JSON"):
                st.code(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), language="json")

footer = st.container()
with footer:
    st.markdown(
        "<small>Projeto acadêmico — IA Generativa para Engenharia de Software. </small>",
        unsafe_allow_html=True,
    )
