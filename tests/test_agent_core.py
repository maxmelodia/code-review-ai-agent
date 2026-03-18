from agent_core import analyze_code_snippet


def test_detects_todo_and_respects_governance(tmp_path):
    code = """\ndef foo():
        # TODO: refatorar
        return 42
    """

    report = analyze_code_snippet(code, blueprint_path="blueprint.md")

    descriptions = [finding.description for finding in report.findings]
    assert any("TODO" in desc for desc in descriptions)
    assert report.governance["is_compliant"]


def test_info_message_when_no_issues():
    code = """\ndef foo():
        return 42
    """

    report = analyze_code_snippet(code, blueprint_path="blueprint.md")

    assert report.findings
    assert report.findings[0].severity in {"Info", "Low", "Medium", "High", "Critical"}
