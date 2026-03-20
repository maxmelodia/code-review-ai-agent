"""Módulo principal do PR Review AI Agent."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from dotenv import load_dotenv

from validators import load_blueprint_rules, summarize_governance

load_dotenv()

_SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4}


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

    @property
    def severity_score(self) -> int:
        return _SEVERITY_ORDER.get(self.severity, 99)

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

    def to_markdown(self) -> str:
        lines = [f"# Relatório de Revisão\n", f"**Resumo:** {self.summary}\n"]
        lines.append(f"**Linhas:** {self.statistics.get('loc', '?')} | "
                     f"**Linguagem:** {self.statistics.get('language', '?')}\n")
        if self.findings:
            lines.append("## Achados\n")
            for i, f in enumerate(self.findings, 1):
                ln = f" (linha {f.line})" if f.line else ""
                lines.append(f"### {i}. [{f.severity}] {f.category}{ln}\n")
                lines.append(f"{f.description}\n")
                lines.append(f"**Recomendação:** {f.recommendation}\n")
                if f.code_snippet:
                    lines.append(f"```\n# Problemático:\n{f.code_snippet}\n```\n")
                if f.fix_snippet:
                    lines.append(f"```\n# Correção:\n{f.fix_snippet}\n```\n")
        if self.next_steps:
            lines.append("## Próximos Passos\n")
            for s in self.next_steps:
                lines.append(f"- {s}\n")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM integration with cache and retry
# ---------------------------------------------------------------------------

_llm_error: Optional[str] = None
_llm_cache: Dict[str, List[dict]] = {}


def _load_blueprint_text(path: str) -> str:
    bp = Path(path)
    return bp.read_text(encoding="utf-8") if bp.exists() else ""


def _call_llm(code: str, language: str, blueprint_text: str) -> List[dict]:
    global _llm_error
    _llm_error = None
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return []

    cache_key = hashlib.md5(f"{language}:{code}".encode()).hexdigest()
    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        last_exc = None
        for attempt in range(3):
            try:
                resp = client.models.generate_content(
                    model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                    contents=f"{blueprint_text}\n\nLinguagem: {language}\n\n```\n{code}\n```",
                    config={"response_mime_type": "application/json", "temperature": 0.2},
                )
                data = json.loads(resp.text)
                result = data.get("findings", [])
                _llm_cache[cache_key] = result
                return result
            except Exception as exc:
                last_exc = exc
                if "429" in str(exc) and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise
    except Exception as exc:
        _llm_error = str(exc)[:200]
        return []


def _sanitize_llm_findings(raw: List[dict], rules) -> List[Finding]:
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
            category=cat, severity=sev, description=desc, recommendation=rec,
            line=item.get("line"), code_snippet=item.get("code_snippet"),
            fix_snippet=item.get("fix_snippet"),
        ))
    return valid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(lines: list, line_num: int, radius: int = 1) -> str:
    start = max(0, line_num - 1 - radius)
    end = min(len(lines), line_num + radius)
    return "\n".join(lines[start:end])


# ---------------------------------------------------------------------------
# Python heuristics
# ---------------------------------------------------------------------------

def _detect_todo(code: str, **_) -> List[Finding]:
    for i, line in enumerate(code.splitlines(), 1):
        if "TODO" in line or "FIXME" in line:
            return [Finding("best-practice", "Low", "Marcador TODO/FIXME pendente.",
                            "Resolver ou registrar uma issue antes do merge.", line=i,
                            code_snippet=line.strip())]
    return []


def _detect_hardcoded_secret(code: str, **_) -> List[Finding]:
    pat = re.compile(r"(api|token|secret|password)[\w_-]*\s*=\s*['\"]?[A-Za-z0-9_\-]{12,}['\"]?", re.I)
    for i, line in enumerate(code.splitlines(), 1):
        if pat.search(line):
            vm = re.match(r"\s*(\w+)\s*=", line)
            vn = vm.group(1) if vm else "SECRET"
            return [Finding("security", "Critical", "Possível credencial hardcoded detectada.",
                            "Mover para Secret Manager ou variável de ambiente.", line=i,
                            code_snippet=line.strip(), fix_snippet=f'{vn} = os.getenv("{vn.upper()}")')]
    return []


def _detect_eval_or_exec(code: str, **_) -> List[Finding]:
    for i, line in enumerate(code.splitlines(), 1):
        if "eval(" in line or "exec(" in line:
            fix = line.strip().replace("eval(", "ast.literal_eval(").replace("exec(", "# exec removido: ")
            return [Finding("security", "High", "Uso de eval/exec abre brechas para execução arbitrária.",
                            "Usar `ast.literal_eval` ou parsers seguros.", line=i,
                            code_snippet=line.strip(), fix_snippet=fix)]
    return []


def _detect_bare_except(code: str, **_) -> List[Finding]:
    for i, line in enumerate(code.splitlines(), 1):
        if re.search(r"except\s*:\s*", line):
            return [Finding("bug-risk", "Medium", "`except` genérico pode mascarar falhas.",
                            "Capture exceções específicas.", line=i, code_snippet=line.strip(),
                            fix_snippet="except ValueError as exc:  # especifique")]
        if re.search(r"except\s+Exception\b", line):
            return [Finding("bug-risk", "Medium", "`except Exception` genérico pode mascarar falhas.",
                            "Capture exceções específicas.", line=i, code_snippet=line.strip(),
                            fix_snippet=line.strip().replace("Exception", "ValueError  # especifique"))]
    return []


def _detect_large_function(code: str, **_) -> List[Finding]:
    lines = code.splitlines()
    start = current = longest = l_start = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("def "):
            if current > longest:
                longest, l_start = current, start
            start, current = i + 1, 1
        elif current > 0:
            current += 1
    if current > longest:
        longest, l_start = current, start
    if longest <= 50:
        return []
    return [Finding("best-practice", "Low", f"Função com ~{longest} linhas dificulta manutenção.",
                    "Quebrar em funções menores.", line=l_start,
                    code_snippet=lines[l_start - 1].strip() if l_start > 0 else None)]


def _detect_print_statements(code: str, language: str = "python", **_) -> List[Finding]:
    if language.lower() != "python":
        return []
    full = code
    if "input(" in full or "__name__" in full:
        return []
    has_log = "import logging" in full
    for i, line in enumerate(code.splitlines(), 1):
        if "print(" in line:
            return [Finding("best-practice", "Info",
                            "`print` encontrado; prefira logging." if has_log else "`print` encontrado; considere `logging`.",
                            "Trocar `print` por `logging`." if has_log else "Se não for CLI, use `logging`.",
                            line=i, code_snippet=line.strip(),
                            fix_snippet=line.replace("print(", "logging.info(").strip() if has_log else None)]
    return []


def _detect_division_by_zero(code: str, **_) -> List[Finding]:
    lines = code.splitlines()
    zeros: set[str] = set()
    for line in lines:
        m = re.match(r"\s*(\w+)\s*=\s*0\s*$", line)
        if m:
            zeros.add(m.group(1))
    for i, line in enumerate(lines, 1):
        if re.search(r"/\s*0\b", line):
            return [Finding("bug-risk", "Critical", "Divisão por zero — ZeroDivisionError.",
                            "Verificar divisor antes da operação.", line=i, code_snippet=line.strip(),
                            fix_snippet="if divisor != 0:\n    resultado = total / divisor")]
        for v in zeros:
            if re.search(rf"/\s*{re.escape(v)}\b", line):
                return [Finding("bug-risk", "Critical",
                                f"Divisão por `{v}` (= 0) — ZeroDivisionError.", "Validar divisor.",
                                line=i, code_snippet=_ctx(lines, i),
                                fix_snippet=f"if {v} != 0:\n    {line.strip()}")]
    return []


def _detect_index_errors(code: str, **_) -> List[Finding]:
    for i, line in enumerate(code.splitlines(), 1):
        if re.search(r"\[\s*\]\s*\[", line) or re.search(r"\{\s*\}\s*\[", line):
            return [Finding("bug-risk", "High", "Acesso a índice em coleção vazia — IndexError/KeyError.",
                            "Verificar se a coleção tem elementos.", line=i, code_snippet=line.strip(),
                            fix_snippet="if colecao:\n    valor = colecao[0]")]
    return []


def _detect_mutable_default(code: str, **_) -> List[Finding]:
    for i, line in enumerate(code.splitlines(), 1):
        m = re.search(r"def\s+(\w+)\s*\([^)]*(\w+)\s*=\s*(\[\]|\{\})\s*[,)]", line)
        if m:
            fn, p, d = m.group(1), m.group(2), m.group(3)
            e = "[]" if d == "[]" else "{}"
            return [Finding("bug-risk", "Medium", "Argumento mutável como default — compartilhado entre chamadas.",
                            "Usar `None` e inicializar dentro da função.", line=i, code_snippet=line.strip(),
                            fix_snippet=f"def {fn}({p}=None):\n    if {p} is None:\n        {p} = {e}")]
    return []


def _detect_comparison_bugs(code: str, **_) -> List[Finding]:
    for i, line in enumerate(code.splitlines(), 1):
        if re.search(r"\bis\s+(\"|\').*(\"|\')", line) or re.search(r"\bis\s+\d+", line):
            return [Finding("bug-risk", "Medium", "`is` com literal — use `==`.",
                            "Substituir `is` por `==`.", line=i, code_snippet=line.strip(),
                            fix_snippet=re.sub(r"\bis\b", "==", line).strip())]
    return []


def _detect_unused_variable(code: str, **_) -> List[Finding]:
    lines = code.splitlines()
    assigns: dict[str, int] = {}
    for i, line in enumerate(lines, 1):
        m = re.match(r"\s+(\w+)\s*=\s*.+", line)
        if m and not m.group(1).startswith("_") and m.group(1) not in ("self", "cls"):
            assigns[m.group(1)] = i
    full = "\n".join(lines)
    out = []
    for name, ln in assigns.items():
        if len(re.findall(rf"\b{re.escape(name)}\b", full)) == 1:
            out.append(Finding("best-practice", "Low", f"Variável `{name}` nunca usada.",
                               "Remover ou prefixar com `_`.", line=ln, code_snippet=lines[ln - 1].strip(),
                               fix_snippet=f"# removido: {lines[ln - 1].strip()}"))
            if len(out) >= 2:
                break
    return out


def _detect_infinite_loop(code: str, **_) -> List[Finding]:
    lines = code.splitlines()
    for i, line in enumerate(lines, 1):
        if re.search(r"while\s+True\s*:", line):
            indent = len(line) - len(line.lstrip())
            block = []
            for j in range(i, len(lines)):
                l = lines[j]
                if l.strip() and not l.startswith(" " * (indent + 1)) and j > i:
                    if l.strip().startswith(("def ", "class ")):
                        break
                block.append(l)
            text = "\n".join(block)
            if "break" not in text and "return" not in text and "sys.exit" not in text:
                return [Finding("bug-risk", "High", "`while True` sem saída — possível loop infinito.",
                                "Adicionar `break` ou `return`.", line=i, code_snippet=_ctx(lines, i, 2),
                                fix_snippet="while True:\n    ...\n    if condicao:\n        break")]
    return []


def _detect_none_return_usage(code: str, **_) -> List[Finding]:
    lines = code.splitlines()
    none_fns: set[str] = set()
    cur = None
    for line in lines:
        s = line.strip()
        if s.startswith("def "):
            m = re.match(r"def\s+(\w+)\s*\(", s)
            if m:
                cur = m.group(1)
        if s in ("return", "return None") and cur:
            none_fns.add(cur)
    for i, line in enumerate(lines, 1):
        for fn in none_fns:
            if re.search(rf"\w+\s*=\s*{re.escape(fn)}\s*\(", line):
                if any(re.search(r"\.(\w+)", lines[j]) for j in range(i, min(i + 3, len(lines)))):
                    return [Finding("bug-risk", "Medium", f"`{fn}` retorna None mas resultado é usado.",
                                    "Tratar caso None.", line=i, code_snippet=line.strip(),
                                    fix_snippet=f"res = {fn}(...)\nif res is not None:\n    res.metodo()")]
    return []


def _detect_string_format_bugs(code: str, **_) -> List[Finding]:
    for i, line in enumerate(code.splitlines(), 1):
        if re.search(r"f['\"].*\{.*\}.*['\"]", line):
            continue
        if re.search(r"['\"].*\{\}.*['\"]\.format\(", line):
            ph = line.count("{}")
            args = line.count(",") + 1 if ".format(" in line else 0
            if ph != args and args > 0:
                return [Finding("bug-risk", "Medium", "Placeholders `{}` não batem com `.format()` args.",
                                "Ajustar quantidade.", line=i, code_snippet=line.strip())]
    return []


def _detect_missing_imports(code: str, **_) -> List[Finding]:
    lines = code.splitlines()
    full = "\n".join(lines)
    checks = {
        "logging": (r"\blogging\.", r"import logging"),
        "re": (r"\bre\.(search|match|sub|compile|findall)\b", r"import re"),
        "sys": (r"\bsys\.(exit|argv|path|stdout)\b", r"import sys"),
        "math": (r"\bmath\.(sqrt|ceil|floor|log)\b", r"import math"),
        "typing": (r"\b(List|Dict|Optional|Tuple)\[", r"(import typing|from typing)"),
    }
    for mod, (usage, imp) in checks.items():
        if re.search(usage, full) and not re.search(imp, full):
            for i, line in enumerate(lines, 1):
                if re.search(usage, line):
                    return [Finding("bug-risk", "High", f"`{mod}` usado sem import — NameError.",
                                    f"Adicionar `import {mod}`.", line=i, code_snippet=line.strip(),
                                    fix_snippet=f"import {mod}\n\n{line.strip()}")]
    return []


def _detect_sql_injection(code: str, **_) -> List[Finding]:
    for i, line in enumerate(code.splitlines(), 1):
        if re.search(r"(execute|cursor\.execute)\s*\(\s*f['\"]", line) or \
           re.search(r"(execute|cursor\.execute)\s*\(\s*['\"].*%s.*['\"].*%", line) or \
           re.search(r"(execute|cursor\.execute)\s*\(\s*['\"].*\+", line):
            return [Finding("security", "Critical", "Possível SQL injection — query construída com interpolação.",
                            "Usar queries parametrizadas: `cursor.execute('SELECT ... WHERE id = ?', (id,))`.",
                            line=i, code_snippet=line.strip(),
                            fix_snippet='cursor.execute("SELECT * FROM t WHERE id = ?", (user_id,))')]
    return []


def _detect_file_not_closed(code: str, **_) -> List[Finding]:
    for i, line in enumerate(code.splitlines(), 1):
        if re.search(r"=\s*open\(", line) and "with " not in line:
            var = re.match(r"\s*(\w+)\s*=\s*open\(", line)
            vn = var.group(1) if var else "f"
            return [Finding("bug-risk", "Medium", "Arquivo aberto sem `with` — possível resource leak.",
                            "Usar context manager `with open(...) as f:`.", line=i, code_snippet=line.strip(),
                            fix_snippet=f'with open(...) as {vn}:\n    dados = {vn}.read()')]
    return []


def _detect_none_comparison(code: str, **_) -> List[Finding]:
    for i, line in enumerate(code.splitlines(), 1):
        if re.search(r"==\s*None\b", line) or re.search(r"!=\s*None\b", line):
            fix = line.replace("== None", "is None").replace("!= None", "is not None")
            return [Finding("best-practice", "Low", "Use `is None` em vez de `== None`.",
                            "PEP 8 recomenda `is None` para comparação com singletons.", line=i,
                            code_snippet=line.strip(), fix_snippet=fix.strip())]
    return []


# ---------------------------------------------------------------------------
# JavaScript/TypeScript heuristics
# ---------------------------------------------------------------------------

def _detect_js_var(code: str, language: str = "", **_) -> List[Finding]:
    if language.lower() not in ("javascript", "typescript"):
        return []
    for i, line in enumerate(code.splitlines(), 1):
        if re.search(r"\bvar\s+\w+", line):
            fix = re.sub(r"\bvar\b", "let", line)
            return [Finding("best-practice", "Medium", "`var` tem escopo de função — prefira `let`/`const`.",
                            "Substituir `var` por `let` ou `const`.", line=i, code_snippet=line.strip(),
                            fix_snippet=fix.strip())]
    return []


def _detect_js_triple_eq(code: str, language: str = "", **_) -> List[Finding]:
    if language.lower() not in ("javascript", "typescript"):
        return []
    for i, line in enumerate(code.splitlines(), 1):
        if re.search(r"[^=!]==[^=]", line) and "===" not in line:
            fix = line.replace("==", "===")
            return [Finding("bug-risk", "Medium", "`==` faz coerção de tipo — use `===`.",
                            "Substituir `==` por `===`.", line=i, code_snippet=line.strip(),
                            fix_snippet=fix.strip())]
    return []


def _detect_js_console_log(code: str, language: str = "", **_) -> List[Finding]:
    if language.lower() not in ("javascript", "typescript"):
        return []
    for i, line in enumerate(code.splitlines(), 1):
        if "console.log(" in line:
            return [Finding("best-practice", "Info", "`console.log` de debug encontrado.",
                            "Remover ou usar logger estruturado.", line=i, code_snippet=line.strip(),
                            fix_snippet="// " + line.strip())]
    return []


# ---------------------------------------------------------------------------
# Go heuristics
# ---------------------------------------------------------------------------

def _detect_go_ignored_error(code: str, language: str = "", **_) -> List[Finding]:
    if language.lower() != "go":
        return []
    for i, line in enumerate(code.splitlines(), 1):
        if re.search(r"_\s*,?\s*:?=.*\(", line) and "err" not in line.lower():
            continue
        if re.search(r"_\s*=\s*\w+\.\w+\(", line):
            return [Finding("bug-risk", "High", "Erro ignorado com `_` — pode esconder falhas.",
                            "Tratar o erro: `if err != nil { ... }`.", line=i, code_snippet=line.strip(),
                            fix_snippet="result, err := funcao()\nif err != nil {\n    log.Fatal(err)\n}")]
    return []


_HEURISTICS = [
    _detect_todo,
    _detect_hardcoded_secret,
    _detect_eval_or_exec,
    _detect_sql_injection,
    _detect_bare_except,
    _detect_large_function,
    _detect_print_statements,
    _detect_division_by_zero,
    _detect_index_errors,
    _detect_mutable_default,
    _detect_comparison_bugs,
    _detect_none_comparison,
    _detect_unused_variable,
    _detect_infinite_loop,
    _detect_none_return_usage,
    _detect_string_format_bugs,
    _detect_missing_imports,
    _detect_file_not_closed,
    # JS/TS
    _detect_js_var,
    _detect_js_triple_eq,
    _detect_js_console_log,
    # Go
    _detect_go_ignored_error,
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_code_snippet(
    code: str, *, language: str = "python", file_path: Optional[str] = None,
    blueprint_path: str = "blueprint.md",
) -> AnalysisReport:
    normalized = code or ""
    rules = load_blueprint_rules(blueprint_path)

    heuristic_findings: List[Finding] = []
    for h in _HEURISTICS:
        heuristic_findings.extend(h(normalized, language=language, file_path=file_path))

    blueprint_text = _load_blueprint_text(blueprint_path)
    llm_raw = _call_llm(normalized, language, blueprint_text)
    llm_findings = _sanitize_llm_findings(llm_raw, rules)

    seen = {f.description for f in heuristic_findings}
    for lf in llm_findings:
        if lf.description not in seen:
            heuristic_findings.append(lf)
            seen.add(lf.description)

    # Sort by severity
    heuristic_findings.sort(key=lambda f: f.severity_score)
    findings = heuristic_findings[:rules.max_findings]

    for f in findings:
        if not f.reference:
            f.reference = file_path

    summary = _build_summary(findings, language)
    governance = summarize_governance([f.to_dict() for f in findings], rules)
    stats = _collect_stats(normalized, language, file_path)
    next_steps = _next_steps_for(findings)

    if not findings:
        findings.append(Finding("best-practice", "Info",
                                "Nenhum problema detectado pelas heurísticas e pelo LLM.",
                                "Considere adicionar testes e ferramentas estáticas (bandit, ruff).",
                                reference=file_path))

    return AnalysisReport(summary=summary, findings=findings, governance=governance,
                          statistics=stats, next_steps=next_steps)


def analyze_pull_request(
    snippets: Iterable[Dict[str, str]], *, blueprint_path: str = "blueprint.md"
) -> Dict[str, object]:
    reports: List[Dict[str, object]] = []
    all_findings: List[Finding] = []
    for s in snippets:
        r = analyze_code_snippet(
            s.get("code", ""), language=s.get("language", "python"),
            file_path=s.get("file_path"), blueprint_path=blueprint_path)
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
    return {"language": language, "file_path": file_path,
            "loc": len(lines), "blank_lines": sum(1 for l in lines if not l.strip())}


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
