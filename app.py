"""Interface Streamlit para o PR Review AI Agent."""
from __future__ import annotations

import json

from dotenv import load_dotenv
import streamlit as st

from agent_core import analyze_code_snippet, analyze_pull_request, _llm_error, _SEVERITY_ORDER

load_dotenv()

_LANG_EXT = {"py": "python", "js": "javascript", "ts": "typescript", "go": "go"}
_SEVERITY_COLORS = {
    "Critical": "#ff4b4b", "High": "#ffa534", "Medium": "#f0c929",
    "Low": "#4b9bff", "Info": "#8c8c8c",
}

st.set_page_config(page_title="PR Review AI Agent", layout="wide")
st.title("🔍 PR Review AI Agent")
st.write("Cole um trecho de código ou envie arquivos para receber uma revisão simulada.")

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Configurações")
    mode = st.radio("Modo", ["Arquivo único", "Múltiplos arquivos (PR)"])
    language = st.selectbox("Linguagem", ["python", "javascript", "typescript", "go"])
    file_path = st.text_input("Nome do arquivo", value="main.py")
    blueprint_path = st.text_input("Blueprint", value="blueprint.md")

    st.markdown("---")
    st.header("🔎 Filtros")
    filter_sev = st.multiselect("Severidade", list(_SEVERITY_ORDER.keys()), default=list(_SEVERITY_ORDER.keys()))
    filter_cat = st.multiselect("Categoria", ["bug-risk", "security", "best-practice"],
                                default=["bug-risk", "security", "best-practice"])

# --- Input ---
if mode == "Arquivo único":
    code_input = st.text_area("Código", height=300, placeholder="Cole aqui o trecho...")
    file_upload = st.file_uploader("Ou envie um arquivo", type=["py", "js", "ts", "go"])
    if file_upload is not None and not code_input:
        code_input = file_upload.read().decode("utf-8")
        file_path = file_upload.name
        ext = file_path.rsplit(".", 1)[-1] if "." in file_path else ""
        language = _LANG_EXT.get(ext, language)
else:
    code_input = ""
    file_uploads = st.file_uploader("Envie os arquivos do PR", type=["py", "js", "ts", "go"],
                                    accept_multiple_files=True)

run_button = st.button("🚀 Analisar", type="primary")

if run_button:
    # --- Single file ---
    if mode == "Arquivo único":
        if not code_input or not code_input.strip():
            st.warning("Forneça um código antes de rodar a análise.")
        else:
            try:
                report = analyze_code_snippet(
                    code_input, language=language,
                    file_path=file_path, blueprint_path=blueprint_path)
            except FileNotFoundError as exc:
                st.error(f"Blueprint não encontrado: {exc}")
            else:
                _render_report(report, code_input, language, filter_sev, filter_cat) if False else None

                # Inline render to avoid function-before-definition issue
                st.success(report.summary)
                if _llm_error:
                    st.warning(f"⚠️ LLM indisponível (heurísticas apenas): {_llm_error}")

                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("📊 Estatísticas")
                    c1, c2 = st.columns(2)
                    c1.metric("Linhas", report.statistics["loc"])
                    c2.metric("Em branco", report.statistics["blank_lines"])
                with col2:
                    st.subheader("📋 Próximos passos")
                    for step in report.next_steps:
                        st.markdown(f"- {step}")

                # Code with highlighted lines
                st.subheader("📝 Código analisado")
                problem_lines = {f.line for f in report.findings if f.line}
                code_lines = code_input.splitlines()
                highlighted = []
                for idx, line in enumerate(code_lines, 1):
                    prefix = "→ " if idx in problem_lines else "  "
                    highlighted.append(f"{prefix}{idx:4d} | {line}")
                st.code("\n".join(highlighted), language=language)

                # Findings with filters
                filtered = [f for f in report.findings
                            if f.severity in filter_sev and f.category in filter_cat]
                st.subheader(f"🔍 Achados ({len(filtered)}/{len(report.findings)})")

                for finding in filtered:
                    color = _SEVERITY_COLORS.get(finding.severity, "#8c8c8c")
                    line_info = f" · linha {finding.line}" if finding.line else ""
                    st.markdown(
                        f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;'
                        f'font-size:0.85em">{finding.severity}</span> '
                        f'<span style="font-size:0.85em;color:#666">{finding.category}{line_info}</span>',
                        unsafe_allow_html=True)
                    st.markdown(f"**{finding.description}**")
                    st.markdown(f"💡 {finding.recommendation}")
                    if finding.code_snippet:
                        st.markdown("❌ **Código problemático:**")
                        st.code(finding.code_snippet, language=language)
                    if finding.fix_snippet:
                        st.markdown("✅ **Correção sugerida:**")
                        st.code(finding.fix_snippet, language=language)
                    if finding.reference:
                        st.caption(f"Referência: {finding.reference}")
                    st.markdown("---")

                # Governance
                st.subheader("🏛️ Governança")
                if report.governance.get("is_compliant"):
                    st.success("✅ Todas as regras foram respeitadas.")
                else:
                    st.error("❌ Existem pendências de governança.")
                st.json(report.governance)

                # Exports
                col_json, col_md = st.columns(2)
                with col_json:
                    with st.expander("📦 Exportar JSON"):
                        json_str = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
                        st.code(json_str, language="json")
                        st.download_button("⬇️ Baixar JSON", json_str, "relatorio.json", "application/json")
                with col_md:
                    with st.expander("📄 Exportar Markdown"):
                        md_str = report.to_markdown()
                        st.code(md_str, language="markdown")
                        st.download_button("⬇️ Baixar Markdown", md_str, "relatorio.md", "text/markdown")

    # --- Multi-file PR ---
    else:
        if not file_uploads:
            st.warning("Envie pelo menos um arquivo.")
        else:
            snippets = []
            for f in file_uploads:
                content = f.read().decode("utf-8")
                ext = f.name.rsplit(".", 1)[-1] if "." in f.name else ""
                lang = _LANG_EXT.get(ext, "python")
                snippets.append({"code": content, "language": lang, "file_path": f.name})

            try:
                result = analyze_pull_request(snippets, blueprint_path=blueprint_path)
            except FileNotFoundError as exc:
                st.error(f"Blueprint não encontrado: {exc}")
            else:
                st.success(result["summary"])
                if _llm_error:
                    st.warning(f"⚠️ LLM indisponível (heurísticas apenas): {_llm_error}")

                st.metric("Total de achados", result["total_findings"])

                for i, (snippet, rep) in enumerate(zip(snippets, result["reports"])):
                    with st.expander(f"📄 {snippet['file_path']} — {len(rep['findings'])} achados"):
                        st.markdown(f"**{rep['summary']}**")

                        # Highlighted code
                        problem_lines = {f.get("line") for f in rep["findings"] if f.get("line")}
                        code_lines = snippet["code"].splitlines()
                        highlighted = []
                        for idx, line in enumerate(code_lines, 1):
                            prefix = "→ " if idx in problem_lines else "  "
                            highlighted.append(f"{prefix}{idx:4d} | {line}")
                        st.code("\n".join(highlighted), language=snippet["language"])

                        for finding in rep["findings"]:
                            sev = finding.get("severity", "Info")
                            color = _SEVERITY_COLORS.get(sev, "#8c8c8c")
                            ln = f" · linha {finding.get('line')}" if finding.get("line") else ""
                            st.markdown(
                                f'<span style="background:{color};color:white;padding:2px 8px;'
                                f'border-radius:4px;font-size:0.85em">{sev}</span> '
                                f'<span style="font-size:0.85em;color:#666">'
                                f'{finding.get("category", "")}{ln}</span>',
                                unsafe_allow_html=True)
                            st.markdown(f"**{finding.get('description', '')}**")
                            st.markdown(f"💡 {finding.get('recommendation', '')}")
                            if finding.get("code_snippet"):
                                st.markdown("❌ **Código problemático:**")
                                st.code(finding["code_snippet"], language=snippet["language"])
                            if finding.get("fix_snippet"):
                                st.markdown("✅ **Correção sugerida:**")
                                st.code(finding["fix_snippet"], language=snippet["language"])
                            st.markdown("---")

                # Governance
                st.subheader("🏛️ Governança")
                if result["governance"].get("is_compliant"):
                    st.success("✅ Todas as regras foram respeitadas.")
                else:
                    st.error("❌ Existem pendências de governança.")
                st.json(result["governance"])

                # Export
                json_str = json.dumps(result, indent=2, ensure_ascii=False)
                st.download_button("⬇️ Baixar relatório JSON", json_str, "pr_report.json", "application/json")

# --- Footer ---
st.markdown("---")
st.markdown(
    "<small>Projeto acadêmico — IA Generativa para Engenharia de Software.</small>",
    unsafe_allow_html=True)
