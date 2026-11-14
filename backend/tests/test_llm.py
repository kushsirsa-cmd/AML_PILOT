"""Exercises the Claude code path with a fake client (no network)."""
from types import SimpleNamespace

from app import llm
from app.config import settings

PAYLOAD = {
    "full_name": "Claude Path", "date_of_birth": "1985-02-02", "nationality": "Poland", "country_of_residence": "Poland",
    "occupation": "Teacher", "industry": "Education", "annual_income": 30000,
    "source_of_funds": "Monthly teaching salary of EUR 2,000 from a public school, employed since 2010.",
    "source_of_wealth": "Savings from employment as a teacher since 2010 totalling about EUR 20,000.",
    "expected_activity": "Salary of EUR 2,000 per month",
}


class FakeClient:
    def __init__(self, fail=False):
        self.fail, self.prompts = fail, []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.prompts.append(kw["messages"][0]["content"])
        if self.fail:
            raise RuntimeError("boom")
        prompt = kw["messages"][0]["content"]
        if "SOURCE OF FUNDS" in prompt:
            text = '{"plausibility": "IMPLAUSIBLE", "assessment": "Claude says be careful.", "risk_observations": ["Claude observation"], "suggested_evidence": ["Claude evidence"]}'
        elif "SOURCE OF WEALTH" in prompt:
            text = '```json\n{"sow_assessment": "PARTIAL", "assessment": "Claude SoW view.", "observations": [], "missing_evidence": []}\n```'
        elif "four numbered sections" in prompt:
            text = "1. CUSTOMER PROFILE\n- x\n2. RISKS IDENTIFIED\n- y\n3. SCREENING RESULTS\n- z\n4. FINAL RECOMMENDATION\n- APPROVE"
        else:
            text = "Claude narrative."
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def _enable(monkeypatch, client):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(llm, "_client", client)


def test_claude_layer_is_used_and_takes_the_more_cautious_view(client, monkeypatch):
    fake = FakeClient()
    _enable(monkeypatch, fake)
    d = client.post("/api/customers", json=PAYLOAD).json()
    a = d["assessments"]
    assert a["kyc"]["engine"] == "rules+claude" and a["kyc"]["output"]["kyc_summary"] == "Claude narrative."
    assert a["sof"]["output"]["plausibility"] == "IMPLAUSIBLE"  # rules said PLAUSIBLE; Claude was more cautious
    assert "Claude observation" in a["sof"]["output"]["risk_observations"]
    assert a["sow"]["output"]["sow_assessment"] in ("PARTIAL", "INSUFFICIENT")  # fenced JSON parsed
    assert a["summary"]["engine"] == "rules+claude" and "FINAL RECOMMENDATION" in a["summary"]["output"]["case_note"]
    # customer free text is passed inside delimited data tags, never as instructions
    assert any("<customer_data>" in p for p in fake.prompts)


def test_claude_failure_falls_back_to_rules(client, monkeypatch):
    _enable(monkeypatch, FakeClient(fail=True))
    d = client.post("/api/customers", json={**PAYLOAD, "full_name": "Fallback Path"}).json()
    assert all(v["engine"] == "rules" for k, v in d["assessments"].items())
    assert d["customer"]["risk_rating"] is not None
