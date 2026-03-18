"""Governança e validações para o PR Review AI Agent."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List
import re


_METADATA_PATTERN = re.compile(
    r"<!--\s*blueprint:(?P<key>[a-zA-Z0-9_-]+)\s*=\s*(?P<value>[^-]+?)\s*-->"
)


@dataclass
class BlueprintRules:
    """Regras declaradas no blueprint.md."""

    severity_levels: List[str]
    required_categories: List[str]
    max_findings: int


@dataclass
class ValidationIssue:
    code: str
    message: str


@dataclass
class ValidationSummary:
    is_compliant: bool
    issues: List[ValidationIssue]

    def to_dict(self) -> Dict[str, object]:
        return {
            "is_compliant": self.is_compliant,
            "issues": [issue.__dict__ for issue in self.issues],
        }


class BlueprintNotFoundError(FileNotFoundError):
    pass


def load_blueprint_rules(path: str = "blueprint.md") -> BlueprintRules:
    """Lê metadados do blueprint e retorna as regras interpretadas."""

    blueprint_path = Path(path)
    if not blueprint_path.exists():
        raise BlueprintNotFoundError(
            f"Blueprint não encontrado em {blueprint_path.resolve()}"
        )

    content = blueprint_path.read_text(encoding="utf-8")
    metadata = {
        match.group("key"): match.group("value").strip()
        for match in _METADATA_PATTERN.finditer(content)
    }

    severity_levels = _split_list(metadata.get("severity-levels", "Critical,High,Medium,Low"))
    required_categories = _split_list(
        metadata.get("required-categories", "bug-risk,security,best-practice")
    )
    max_findings = int(metadata.get("max-findings", 5))

    return BlueprintRules(
        severity_levels=severity_levels,
        required_categories=required_categories,
        max_findings=max_findings,
    )


def _split_list(raw_value: str) -> List[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def validate_findings(
    findings: Iterable[Dict[str, str]], rules: BlueprintRules
) -> ValidationSummary:
    """Valida achados segundo as regras do blueprint."""

    issues: List[ValidationIssue] = []
    findings_list = list(findings)

    if len(findings_list) > rules.max_findings:
        issues.append(
            ValidationIssue(
                code="max_findings_exceeded",
                message=(
                    f"Foram gerados {len(findings_list)} achados, "
                    f"mas o limite configurado é {rules.max_findings}."
                ),
            )
        )

    for idx, finding in enumerate(findings_list, start=1):
        severity = (finding.get("severity") or "").strip()
        category = (finding.get("category") or "").strip()
        if severity not in rules.severity_levels:
            issues.append(
                ValidationIssue(
                    code="invalid_severity",
                    message=(
                        f"Achado #{idx} usa severidade '{severity}', "
                        f"mas o blueprint permite {rules.severity_levels}."
                    ),
                )
            )
        if category and category not in rules.required_categories:
            issues.append(
                ValidationIssue(
                    code="invalid_category",
                    message=(
                        f"Achado #{idx} usa categoria '{category}', "
                        f"mas o blueprint permite {rules.required_categories}."
                    ),
                )
            )
        if not finding.get("description"):
            issues.append(
                ValidationIssue(
                    code="missing_description",
                    message=f"Achado #{idx} precisa de descrição detalhada.",
                )
            )
        if not finding.get("recommendation"):
            issues.append(
                ValidationIssue(
                    code="missing_recommendation",
                    message=f"Achado #{idx} precisa de recomendação acionável.",
                )
            )

    return ValidationSummary(is_compliant=not issues, issues=issues)


def summarize_governance(
    findings: Iterable[Dict[str, str]], rules: BlueprintRules
) -> Dict[str, object]:
    summary = validate_findings(findings, rules)
    status = "Todas as regras foram respeitadas." if summary.is_compliant else "Existem pendências de governança."  # noqa: E501
    return {
        "status": status,
        "is_compliant": summary.is_compliant,
        "issues": [issue.__dict__ for issue in summary.issues],
        "limits": {
            "max_findings": rules.max_findings,
            "severity_levels": rules.severity_levels,
            "categories": rules.required_categories,
        },
    }
