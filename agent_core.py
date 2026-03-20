"""Módulo principal do PR Review AI Agent."""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from dotenv import load_dotenv

from validators import load_blueprint_rules, summarize_governance, validate_findings

load_dotenv()


@dataclass
class Finding:
    category: str
    severity: str
    description: str
    recommendation: str
    reference: Optional[str] = None
    line: Optional[int] = None
    code_snippet: Optional[str] = None
    fix_snippet: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
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
            "findings": [f.to_dict() for f in self.findings],
            "governance": self.governance,
            "statistics": self.statistics,
            "next_steps": self.next_steps,
        }


# ---------------------------------------------------------------------------
# LLM integration
# ---------------------------------------------------------------------------

def _load_blueprint_text(path: str) -> str:
    bp = Path(path)
    if bp.exists():
        return bp.read_text(encoding="utf-8")
    return ""


_llm_error: Optional[str] = None


def _call_llm(code: str, language: str, blueprint_text: str) -> List[dict]:
    """Call Gemini and return parsed findings list."""
    global _llm_error
    _llm_error = None
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return []

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            contents=f"{blueprint_text}\n\nLinguagem: {language}\n\n```\n{code}\n```",
            config={"response_mime_type": "application/json", "temperature": 0.2},
        )
        data = json.loads(resp.text)
        return data.get("findings", [])
    except Exception as exc:
        _llm_error = str(exc)[:200]
        return []


def _sanitize_llm_findings(raw: List[dict], rules) -> List[Finding]:
    """Convert raw LLM dicts to Finding objects, dropping invalid ones."""
    valid = []
    for item in raw:
        cat = (item.get("category") or "").strip()
        sev = (item.get("severity") or "").strip()
        desc = (item.get("description") or "").strip()
        rec = (item.get("recommendation") or "").strip()
        if not desc or not rec:
            continue
        if cat not in rules.required_categories:
            continue
        if sev not in rules.severity_levels:
            continue
        valid.append(Finding(
            category=cat, severity=sev,
            description=desc, recommendation=rec,
            line=item.get("line"),
            code_snippet=item.get("code_snippet"),
            fix_snippet=item.get("fix_snippet"),
        ))
    return valid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(lines: list, line_num: int, radius: int = 1) -> str:
    """Return a few lines around line_num (1-based) as a snippet."""
    start = max(0, line_num - 1 - radius)
    end = min(len(lines), line_num + radius)
    return "\n".join(lines[start:end])


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------

def _detect_todo(code: str, **_: str) -> List[Finding]:
    lines = code.splitlines()
    for i, line in enumerate(lines, 1):
        if "TODO" in line or "FIXME" in line:
            return [Finding(
                category="best-practice", severity="Low",
                description="Marcador TODO/FIXME pendente.",
                recommendation="Resolver ou registrar uma issue antes do merge.",
                line=i,
                code_snippet=line.strip(),
            )]
    return []


def _detect_hardcoded_secret(code: str, **_: str) -> List[Finding]:
    pattern = re.compile(
        r"(api|token|secret|password)[\w_-]*\s*=\s*['\"]?[A-Za-z0-9_\-]{12,}['\"]?",
        re.IGNORECASE,
    )
    lines = code.splitlines()
    for i, line in enumerate(lines, 1):
        if pattern.search(line):
            var_match = re.match(r"\s*(\w+)\s*=", line)
            var_name = var_match.group(1) if var_match else "SECRET"
            return [Finding(
                category="security", severity="Critical",
                description="Possível credencial hardcoded detectada.",
                recommendation="Mover para Secret Manager ou variável de ambiente e rotacionar.",
                line=i,
                code_snippet=line.strip(),
                fix_snippet=f'{var_name} = os.getenv("{var_name.upper()}")',
            )]
    return []


def _detect_eval_or_exec(code: str, **_: str) -> List[Finding]:
    lines = code.splitlines()
    for i, line in enumerate(lines, 1):
        if "eval(" in line or "exec(" in line:
            fix = line.strip().replace("eval(", "ast.literal_eval(").replace("exec(", "# exec removido: ")
            return [Finding(
                category="security", severity="High",
                description="Uso de eval/exec abre brechas para execução arbitrária.",
                recommendation="Evitar eval/exec; use `ast.literal_eval` ou parsers seguros.",
                line=i,
                code_snippet=line.strip(),
                fix_snippet=fix,
            )]
    return []


def _detect_bare_except(code: str, **_: str) -> List[Finding]:
    lines = code.splitlines()
    for i, line in enumerate(lines, 1):
        if re.search(r"except\s*:\s*", line):
            return [Finding(
                category="bug-risk", severity="Medium",
                description="Uso de `except` genérico pode mascarar falhas reais.",
                recommendation="Capture exceções específicas e registre detalhes.",
                line=i,
                code_snippet=line.strip(),
                fix_snippet="except ValueError as exc:  # especifique a exceção",
            )]
        if re.search(r"except\s+Exception\b", line):
            return [Finding(
                category="bug-risk", severity="Medium",
                description="Uso de `except Exception` genérico pode mascarar falhas reais.",
                recommendation="Capture exceções específicas e registre detalhes.",
                line=i,
                code_snippet=line.strip(),
                fix_snippet=line.strip().replace("Exception", "ValueError  # especifique a exceção"),
            )]
    return []


def _detect_large_function(code: str, **_: str) -> List[Finding]:
    lines = code.splitlines()
    start, current_len, longest, longest_start = 0, 0, 0, 0
    for i, line in enumerate(lines):
        if line.strip().startswith("def "):
            if current_len > longest:
                longest, longest_start = current_len, start
            start, current_len = i + 1, 1
        elif current_len > 0:
            current_len += 1
    if current_len > longest:
        longest, longest_start = current_len, start
    if longest <= 50:
        return []
    return [Finding(
        category="best-practice", severity="Low",
        description=f"Função com ~{longest} linhas dificulta manutenção.",
        recommendation="Quebrar em funções menores com responsabilidade única.",
        line=longest_start,
        code_snippet=lines[longest_start - 1].strip() if longest_start > 0 else None,
    )]


def _detect_print_statements(code: str, language: str = "python", **_: str) -> List[Finding]:
    if language.lower() != "python":
        return []
    lines = code.splitlines()
    # If code has input() or __name__ == "__main__", it's likely a CLI app — print is expected
    full = "\n".join(lines)
    if "input(" in full or '__name__' in full:
        return []
    # Only flag if "logging" is already imported (suggests print is leftover debug)
    has_logging = "import logging" in full or "from logging" in full
    for i, line in enumerate(lines, 1):
        if "print(" in line:
            fix = line.replace("print(", "logging.info(")
            return [Finding(
                category="best-practice", severity="Info",
                description="`print` encontrado; em código de produção prefira logging." if has_logging
                    else "`print` encontrado; considere usar `logging` para melhor controle.",
                recommendation="Trocar `print` por `logging` com nível adequado." if has_logging
                    else "Se for código de produção (não CLI), considere usar `logging`.",
                line=i,
                code_snippet=line.strip(),
                fix_snippet=fix.strip() if has_logging else None,
            )]
    return []


def _detect_division_by_zero(code: str, **_: str) -> List[Finding]:
    lines = code.splitlines()
    zero_vars: set[str] = set()
    for line in lines:
        m = re.match(r"\s*(\w+)\s*=\s*0\s*$", line)
        if m:
            zero_vars.add(m.group(1))

    for i, line in enumerate(lines, 1):
        if re.search(r"/\s*0\b", line):
            return [Finding(
                category="bug-risk", severity="Critical",
                description="Divisão por zero detectada — causa ZeroDivisionError em runtime.",
                recommendation="Adicionar verificação antes da divisão.",
                line=i,
                code_snippet=line.strip(),
                fix_snippet="if divisor != 0:\n    resultado = total / divisor",
            )]
        for var in zero_vars:
            if re.search(rf"/\s*{re.escape(var)}\b", line):
                return [Finding(
                    category="bug-risk", severity="Critical",
                    description=f"Divisão por `{var}` que foi atribuído como 0 — causa ZeroDivisionError.",
                    recommendation="Validar o divisor antes da operação.",
                    line=i,
                    code_snippet=_ctx(lines, i),
                    fix_snippet=f"if {var} != 0:\n    {line.strip()}",
                )]
    return []


def _detect_index_errors(code: str, **_: str) -> List[Finding]:
    lines = code.splitlines()
    for i, line in enumerate(lines, 1):
        if re.search(r"\[\s*\]\s*\[", line) or re.search(r"\{\s*\}\s*\[", line):
            return [Finding(
                category="bug-risk", severity="High",
                description="Acesso a índice/chave em coleção vazia — causa IndexError/KeyError.",
                recommendation="Verificar se a coleção possui elementos antes de acessar.",
                line=i,
                code_snippet=line.strip(),
                fix_snippet="if colecao:\n    valor = colecao[0]",
            )]
    return []


def _detect_none_return_usage(code: str, **_: str) -> List[Finding]:
    lines = code.splitlines()
    none_funcs: set[str] = set()
    current_func = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("def "):
            m = re.match(r"def\s+(\w+)\s*\(", stripped)
            if m:
                current_func = m.group(1)
        if stripped in ("return", "return None") and current_func:
            none_funcs.add(current_func)

    for i, line in enumerate(lines, 1):
        for func in none_funcs:
            if re.search(rf"\w+\s*=\s*{re.escape(func)}\s*\(", line):
                if any(re.search(rf"\.(\w+)", lines[j]) for j in range(i, min(i + 3, len(lines)))):
                    return [Finding(
                        category="bug-risk", severity="Medium",
                        description=f"Função `{func}` retorna None mas o resultado é usado — possível AttributeError.",
                        recommendation=f"Verificar se `{func}` retorna o valor esperado ou tratar o caso None.",
                        line=i,
                        code_snippet=line.strip(),
                        fix_snippet=f"resultado = {func}(...)\nif resultado is not None:\n    resultado.metodo()",
                    )]
    return []


def _detect_mutable_default(code: str, **_: str) -> List[Finding]:
    lines = code.splitlines()
    for i, line in enumerate(lines, 1):
        m = re.search(r"def\s+(\w+)\s*\([^)]*(\w+)\s*=\s*(\[\]|\{\})\s*[,)]", line)
        if m:
            func, param, default = m.group(1), m.group(2), m.group(3)
            empty = "[]" if default == "[]" else "{}"
            return [Finding(
                category="bug-risk", severity="Medium",
                description="Argumento mutável como valor padrão (list/dict) — compartilhado entre chamadas.",
                recommendation="Usar `None` como default e inicializar dentro da função.",
                line=i,
                code_snippet=line.strip(),
                fix_snippet=f"def {func}({param}=None):\n    if {param} is None:\n        {param} = {empty}",
            )]
    return []


def _detect_comparison_bugs(code: str, **_: str) -> List[Finding]:
    lines = code.splitlines()
    for i, line in enumerate(lines, 1):
        if re.search(r"\bis\s+(\"|\').*(\"|\')", line) or re.search(r"\bis\s+\d+", line):
            fix = re.sub(r"\bis\b", "==", line)
            return [Finding(
                category="bug-risk", severity="Medium",
                description="Uso de `is` para comparar com literal — use `==` em vez de `is`.",
                recommendation="Substituir `is` por `==` para comparação de valores.",
                line=i,
                code_snippet=line.strip(),
                fix_snippet=fix.strip(),
            )]
    return []


def _detect_unused_variable(code: str, **_: str) -> List[Finding]:
    lines = code.splitlines()
    assignments: dict[str, int] = {}
    for i, line in enumerate(lines, 1):
        m = re.match(r"\s+(\w+)\s*=\s*.+", line)
        if m:
            name = m.group(1)
            if not name.startswith("_") and name not in ("self", "cls"):
                assignments[name] = i
    full = "\n".join(lines)
    findings = []
    for name, line_num in assignments.items():
        count = len(re.findall(rf"\b{re.escape(name)}\b", full))
        if count == 1:
            findings.append(Finding(
                category="best-practice", severity="Low",
                description=f"Variável `{name}` atribuída mas nunca usada.",
                recommendation="Remover a variável ou prefixar com `_` se for intencional.",
                line=line_num,
                code_snippet=lines[line_num - 1].strip(),
                fix_snippet=f"# removido: {lines[line_num - 1].strip()}",
            ))
            if len(findings) >= 2:
                break
    return findings


def _detect_infinite_loop(code: str, **_: str) -> List[Finding]:
    lines = code.splitlines()
    for i, line in enumerate(lines, 1):
        if re.search(r"while\s+True\s*:", line):
            # Scan until end of the while block (next def/class at same or lower indent, or EOF)
            indent = len(line) - len(line.lstrip())
            block_lines = []
            for j in range(i, len(lines)):
                l = lines[j]
                if l.strip() and not l.startswith(" " * (indent + 1)) and j > i:
                    stripped = l.strip()
                    if stripped.startswith(("def ", "class ")):
                        break
                block_lines.append(l)
            block = "\n".join(block_lines)
            if "break" not in block and "return" not in block and "sys.exit" not in block:
                return [Finding(
                    category="bug-risk", severity="High",
                    description="`while True` sem `break` ou `return` — possível loop infinito.",
                    recommendation="Adicionar condição de saída com `break` ou `return`.",
                    line=i,
                    code_snippet=_ctx(lines, i, 2),
                    fix_snippet="while True:\n    # ... lógica ...\n    if condicao:\n        break",
                )]
    return []


def _detect_string_format_bugs(code: str, **_: str) -> List[Finding]:
    lines = code.splitlines()
    for i, line in enumerate(lines, 1):
        if re.search(r"f['\"].*\{.*\}.*['\"]", line):
            continue
        fmt_match = re.search(r"['\"].*(\{\}).*['\"]\.format\(", line)
        if fmt_match:
            placeholders = line.count("{}")
            args = line.count(",") + 1 if ".format(" in line else 0
            if placeholders != args and args > 0:
                return [Finding(
                    category="bug-risk", severity="Medium",
                    description="Número de placeholders `{}` não bate com argumentos do `.format()`.",
                    recommendation="Ajustar placeholders e argumentos para que correspondam.",
                    line=i,
                    code_snippet=line.strip(),
                )]
    return []


_HEURISTICS = [
    _detect_todo,
    _detect_hardcoded_secret,
    _detect_eval_or_exec,
    _detect_bare_except,
    _detect_large_function,
    _detect_print_statements,
    _detect_division_by_zero,
    _detect_index_errors,
    _detect_mutable_default,
    _detect_comparison_bugs,
    _detect_unused_variable,
    _detect_infinite_loop,
    _detect_none_return_usage,
    _detect_string_format_bugs,
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_code_snippet(
    code: str,
    *,
    language: str = "python",
    file_path: Optional[str] = None,
    blueprint_path: str = "blueprint.md",
) -> AnalysisReport:
    normalized = code or ""
    rules = load_blueprint_rules(blueprint_path)

    # Layer 1: heuristics
    heuristic_findings: List[Finding] = []
    for h in _HEURISTICS:
        heuristic_findings.extend(h(normalized, language=language, file_path=file_path))

    # Layer 2: LLM (complementary)
    blueprint_text = _load_blueprint_text(blueprint_path)
    llm_raw = _call_llm(normalized, language, blueprint_text)
    llm_findings = _sanitize_llm_findings(llm_raw, rules)

    # Merge: heuristic first, then LLM findings not already covered
    seen_descriptions = {f.description for f in heuristic_findings}
    for lf in llm_findings:
        if lf.description not in seen_descriptions:
            heuristic_findings.append(lf)
            seen_descriptions.add(lf.description)

    findings = heuristic_findings[: rules.max_findings]

    # Set reference
    for f in findings:
        if not f.reference:
            f.reference = file_path

    summary = _build_summary(findings, language)
    governance = summarize_governance([f.to_dict() for f in findings], rules)
    stats = _collect_stats(normalized, language, file_path)
    next_steps = _next_steps_for(findings)

    if not findings:
        findings.append(Finding(
            category="best-practice", severity="Info",
            description="Nenhum problema detectado pelas heurísticas e pelo LLM.",
            recommendation="Considere adicionar testes e ferramentas estáticas (bandit, ruff).",
            reference=file_path,
        ))

    return AnalysisReport(
        summary=summary, findings=findings,
        governance=governance, statistics=stats, next_steps=next_steps,
    )


def analyze_pull_request(
    snippets: Iterable[Dict[str, str]], *, blueprint_path: str = "blueprint.md"
) -> Dict[str, object]:
    reports: List[Dict[str, object]] = []
    all_findings: List[Finding] = []
    for s in snippets:
        r = analyze_code_snippet(
            s.get("code", ""), language=s.get("language", "python"),
            file_path=s.get("file_path"), blueprint_path=blueprint_path,
        )
        reports.append(r.to_dict())
        all_findings.extend(r.findings)

    rules = load_blueprint_rules(blueprint_path)
    return {
        "summary": _build_summary(all_findings, "multi-file"),
        "reports": reports,
        "governance": summarize_governance([f.to_dict() for f in all_findings], rules),
        "total_findings": len(all_findings),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_summary(findings: List[Finding], language: str) -> str:
    if not findings:
        return "Nenhum risco significativo detectado."
    cats: Dict[str, int] = {}
    for f in findings:
        cats[f.category] = cats.get(f.category, 0) + 1
    top = ", ".join(f"{c}: {n}" for c, n in cats.items())
    return f"{len(findings)} achados ({top}) no código {language}. Priorize severidade mais alta."


def _collect_stats(code: str, language: str, file_path: Optional[str]) -> Dict[str, object]:
    lines = code.splitlines()
    return {
        "language": language, "file_path": file_path,
        "loc": len(lines), "blank_lines": sum(1 for l in lines if not l.strip()),
    }


def _next_steps_for(findings: Iterable[Finding]) -> List[str]:
    steps: set[str] = set()
    for f in findings:
        if f.category == "security":
            steps.add("Executar `bandit` ou `semgrep` e revisar secrets.")
        if f.category == "bug-risk":
            steps.add("Adicionar testes unitários e rodar `pytest`.")
        if f.category == "best-practice":
            steps.add("Rodar linters (ruff/flake8) para consistência.")
    return sorted(steps) or ["Solicitar double-check de outro revisor."]
