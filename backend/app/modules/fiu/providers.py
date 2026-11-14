"""Chain-analytics PROVIDER ADAPTERS - SIMULATED.

Each adapter exposes the same interface a real integration would (attribute an address, score exposure) but is backed by the demo ledger and
its simulated attribution table. There are no real API calls, endpoints or credentials here: the vendor names and category vocabularies are used
only to show where a production integration plugs in. To integrate for real, implement `Provider.attribute / exposure` against the vendor's
published API under your own licence and map its categories onto CATEGORY_MAP below."""
from __future__ import annotations

from ..chain import CATEGORY_WEIGHT, ChainGraph, screen_address

CATEGORY_MAP = {"SANCTIONED": "sanctions", "RANSOMWARE": "ransomware", "TERRORISM_FINANCING": "terrorist financing", "DARKNET": "darknet market", "MIXER": "mixer",
                "SCAM": "scam", "UNREGULATED_EXCHANGE": "high-risk exchange", "GAMBLING": "gambling", "P2P": "p2p exchange", "DEFI": "defi", "BRIDGE": "bridge",
                "REGULATED_EXCHANGE": "exchange", "UNLABELED": "unknown"}


class Provider:
    code = "SIM"
    name = "Simulated provider"
    vocabulary = "generic"
    coverage = ["ETH", "BTC"]
    # Deliberately different 'opinions' so the UI shows how multi-provider triangulation works. Adjustments are fixed constants, not data.
    score_bias = 0

    def attribute(self, g: ChainGraph, address: str) -> dict:
        lab = g.labels.get(address)
        return dict(provider=self.code, address=address, category=lab.category if lab else "UNLABELED", entity=lab.entity_name if lab else None,
                    label=CATEGORY_MAP.get(lab.category if lab else "UNLABELED"), confidence=0.9 if lab else 0.0, simulated=True)

    def exposure(self, g: ChainGraph, address: str) -> dict:
        r = screen_address(g, address)
        score = max(0, min(100, r["risk_score"] + self.score_bias))
        return dict(provider=self.code, name=self.name, address=address, risk_score=score, direct_pct=r["exposure"]["sources_direct_pct"],
                    indirect_pct=r["exposure"]["sources_indirect_pct"], destination_pct=r["exposure"]["destinations_total_pct"],
                    coverage=self.coverage, simulated=True, note="Simulated output from the demo ledger - not vendor data.")


class Chainalysis(Provider):
    code, name, vocabulary, score_bias = "CHAINALYSIS_SIM", "Chainalysis (simulated adapter)", "category + exposure", 0


class TRM(Provider):
    code, name, vocabulary, score_bias = "TRM_SIM", "TRM Labs (simulated adapter)", "risk indicators", 3


class Elliptic(Provider):
    code, name, vocabulary, score_bias = "ELLIPTIC_SIM", "Elliptic (simulated adapter)", "holistic screening", -2


class Crystal(Provider):
    code, name, vocabulary, score_bias = "CRYSTAL_SIM", "Crystal Intelligence (simulated adapter)", "transaction risk", 1


PROVIDERS: dict[str, Provider] = {p.code: p for p in (Chainalysis(), TRM(), Elliptic(), Crystal())}


def triangulate(g: ChainGraph, address: str) -> dict:
    rows = [p.exposure(g, address) for p in PROVIDERS.values()]
    scores = [r["risk_score"] for r in rows]
    spread = max(scores) - min(scores)
    return dict(providers=rows, attribution=[p.attribute(g, address) for p in PROVIDERS.values()][0], consensus_score=round(sum(scores) / len(scores)), spread=spread,
                disagreement=spread >= 10, simulated=True,
                disclaimer="All provider outputs are SIMULATED from the demo ledger. No vendor API is called. A production deployment would replace these adapters with licensed integrations.")
