"""Módulo principal do PR Review AI Agent."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Optional
import re

from dotenv import load_dotenv

from validators import load_blueprint_rules, summarize_governance


load_dotenv()


@dataclass
class Finding:
    category: str
    severity: str
    description: str
    recommendation: str
    reference: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return asdict(self)


@dataclass
class AnalysisReport:
    summary: str
    findings: List[Finding]
    governance: Dict[str, object]
    statistics: Dict[str, object]
    next_steps: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "summary": self.summary,
            "findings": [finding.to_dict() for finding in self.findings],
            "governance": self.governance,
            "statistics": self.statistics,
            "next_steps": self.next_steps,
        }


def analyze_code_snippet(
    code: str,
    *,
    language: str = "python",
    file_path: Optional[str] = None,
    blueprint_path: str = "blueprint.md",
) -> AnalysisReport:
    """Executa heurísticas simples para simular a revisão de PR."""

    normalized_code = code or ""
    rules = load_blueprint_rules(blueprint_path)

    findings: List[Finding] = []
    for heuristic in _HEURISTICS:
        findings.extend(heuristic(normalized_code, language=language, file_path=file_path))

    summary = _build_summary(findings, language)
    governance = summarize_governance(
        [finding.to_dict() for finding in findings], rules
    )
    stats = _collect_stats(normalized_code, language, file_path)
    next_steps = _next_steps_for(findings)

    if not findings:
        findings.append(
            Finding(
                category="best-practice",
                severity="Info",
                description="Nenhum problema crítico detectado a partir das heurísticas disponíveis.",
                recommendation="Considere adicionar testes automatizados e ferramentas estáticas (p.ex. bandit, ruff) para ampliar a cobertura da revisão.",
                reference=file_path,
            )
        )

    return AnalysisReport(
        summary=summary,
        findings=findings,
        governance=governance,
        statistics=stats,
        next_steps=next_steps,
    )


def analyze_pull_request(
    snippets: Iterable[Dict[str, str]], *, blueprint_path: str = "blueprint.md"
) -> Dict[str, object]:
    """Permite analisar múltiplos arquivos simulando um PR completo."""

    reports: List[Dict[str, object]] = []
    aggregated_findings: List[Finding] = []

    for snippet in snippets:
        report = analyze_code_snippet(
            snippet.get("code", ""),
            language=snippet.get("language", "python"),
            file_path=snippet.get("file_path"),
            blueprint_path=blueprint_path,
        )
        reports.append(report.to_dict())
        aggregated_findings.extend(report.findings)

    overall_summary = _build_summary(aggregated_findings, "multi-file")
    rules = load_blueprint_rules(blueprint_path)
    governance = summarize_governance(
        [finding.to_dict() for finding in aggregated_findings], rules
    )

    return {
        "summary": overall_summary,
        "reports": reports,
        "governance": governance,
        "total_findings": len(aggregated_findings),
    }


# --- Heurísticas -----------------------------------------------------------

def _detect_todo(code: str, **_: str) -> List[Finding]:
    if "TODO" not in code and "FIXME" not in code:
        return []
    return [
        Finding(
            category="best-practice",
            severity="Low",
            description="Há marcadores TODO/FIXME pendentes no trecho enviado.",
            recommendation="Resolver o TODO ou registrar uma issue antes do merge para evitar dívida técnica oculta.",
        )
    ]


def _detect_hardcoded_secret(code: str, **_: str) -> List[Finding]:
    secret_pattern = re.compile(r"(api|token|secret|password)[\w_-]*\s*=\s*['\"]?[A-Za-z0-9_\-]{12,}['\"]?", re.IGNORECASE)
    if not secret_pattern.search(code):
        return []
    return [
        Finding(
            category="security",
            severity="Critical",
            description="Possível credencial hardcoded detectada.",
            recommendation="Mover o valor para um Secret Manager ou variável de ambiente e rotacionar a credencial caso já tenha sido exposta.",
        )
    ]


def _detect_eval_or_exec(code: str, **_: str) -> List[Finding]:
    if "eval(" not in code and "exec(" not in code:
        return []
    return [
        Finding(
            category="security",
            severity="High",
            description="Uso de eval/exec encontrado; isso abre brechas para execução arbitrária de código.",
            recommendation="Evitar eval/exec. Se indispensável, sanitize e restrinja as entradas ou use parsers seguros.",
        )
    ]


def _detect_bare_except(code: str, **_: str) -> List[Finding]:
    if not re.search(r"except\s*:\s*", code) and not re.search(
        r"except\s+Exception\b", code
    ):
        return []
    return [
        Finding(
            category="bug-risk",
            severity="Medium",
            description="Uso de `except` genérico que pode mascarar falhas reais.",
            recommendation="Capture exceções específicas ou registre/log os detalhes para facilitar o debug.",
        )
    ]


def _detect_large_function(code: str, **_: str) -> List[Finding]:
    lines = code.splitlines()
    longest_stretch = _longest_function_length(lines)
    if longest_stretch <= 50:
        return []
    return [
        Finding(
            category="best-practice",
            severity="Low",
            description=f"Foi identificada uma função com aproximadamente {longest_stretch} linhas, o que dificulta manutenção.",
            recommendation="Quebrar a função em módulos menores focados em uma única responsabilidade.",
        )
    ]


def _detect_print_statements(code: str, language: str, **_: str) -> List[Finding]:
    if language.lower() != "python":
        return []
    if "print(" not in code:
        return []
    return [
        Finding(
            category="best-practice",
            severity="Info",
            description="Há `print` de depuração no trecho; em produção prefira logging estruturado.",
            recommendation="Trocar `print` por `logging` com níveis adequados (info, warning, error).",
        )
    ]


_HEURISTICS = [
    _detect_todo,
    _detect_hardcoded_secret,
    _detect_eval_or_exec,
    _detect_bare_except,
    _detect_large_function,
    _detect_print_statements,
]


# --- Helpers ---------------------------------------------------------------

def _build_summary(findings: List[Finding], language: str) -> str:
    if not findings:
        return "Nenhum risco significativo detectado pelas heurísticas atuais."

    categories = {}
    for finding in findings:
        categories.setdefault(finding.category, 0)
        categories[finding.category] += 1

    top_categories = ", ".join(
        f"{category}: {count}" for category, count in categories.items()
    )
    return (
        f"{len(findings)} achados relevantes ({top_categories}) detectados "
        f"no código {language}. Priorize os itens com severidade mais alta."
    )


def _collect_stats(code: str, language: str, file_path: Optional[str]) -> Dict[str, object]:
    lines = code.splitlines()
    return {
        "language": language,
        "file_path": file_path,
        "loc": len(lines),
        "blank_lines": len([line for line in lines if not line.strip()]),
    }


def _next_steps_for(findings: Iterable[Finding]) -> List[str]:
    steps = set()
    for finding in findings:
        if finding.category == "security":
            steps.add("Executar scanners como `bandit` ou `semgrep` e revisar secrets no repositório.")
        if finding.category == "bug-risk":
            steps.add("Adicionar testes unitários cobrindo os caminhos impactados e rodar `pytest`." )
        if finding.category == "best-practice":
            steps.add("Rodar linters (ruff/flake8) para reforçar o estilo e manter consistência.")
    if not steps:
        steps.add("Registrar o resultado no PR e solicitar double-check de outro revisor.")
    return sorted(steps)


def _longest_function_length(lines: List[str]) -> int:
    current_len = 0
    longest = 0
    for line in lines:
        if line.strip().startswith("def "):
            current_len = 1
        elif current_len > 0:
            current_len += 1
        if not line.strip() and current_len > 0:
            longest = max(longest, current_len)
    longest = max(longest, current_len)
    return longest
