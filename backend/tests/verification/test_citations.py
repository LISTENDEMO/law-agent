from __future__ import annotations

from app.domain.models import Evidence
from app.verification.citations import Claim, verify_claims


def _evidence() -> Evidence:
    return Evidence(
        article_id="labor-47",
        law_name="中华人民共和国劳动合同法",
        article_number="第四十七条",
        content="经济补偿按劳动者在本单位工作的年限，每满一年支付一个月工资。",
    )


def test_verifier_accepts_existing_id_matching_quote_and_supported_claim() -> None:
    result = verify_claims(
        [
            Claim(
                text="经济补偿通常按工作年限计算。",
                evidence_ids=["labor-47"],
                quotes=["每满一年支付一个月工资"],
            )
        ],
        [_evidence()],
    )

    assert result.valid is True
    assert result.issues == []


def test_verifier_rejects_unknown_evidence_id() -> None:
    result = verify_claims(
        [Claim(text="结论", evidence_ids=["invented-1"], quotes=[])],
        [_evidence()],
    )

    assert result.valid is False
    assert result.issues[0].code == "unknown_evidence"


def test_verifier_rejects_quote_not_present_in_source() -> None:
    result = verify_claims(
        [Claim(text="结论", evidence_ids=["labor-47"], quotes=["支付三个月工资"])],
        [_evidence()],
    )

    assert result.valid is False
    assert result.issues[0].code == "quote_mismatch"


def test_verifier_rejects_claim_without_evidence() -> None:
    result = verify_claims(
        [Claim(text="确定性法律结论", evidence_ids=[], quotes=[])], [_evidence()]
    )

    assert result.valid is False
    assert result.issues[0].code == "unsupported_claim"
