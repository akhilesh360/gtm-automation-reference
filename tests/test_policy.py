import pytest
import yaml

from src.policy import Policy, load_policy, render_approval_matrix


def test_policy_loads_and_has_expected_thresholds(policy):
    assert policy.discount.standard_limit == 10
    assert policy.discount.manager_limit == 20
    assert policy.acv.vp_threshold == 100000
    assert policy.payment_terms.standard == ["Net 30", "Annual Prepaid"]
    assert abs(sum(policy.scoring.weights.model_dump().values()) - 1.0) < 1e-9


def test_policy_rejects_bad_weights(tmp_path, policy):
    raw = policy.model_dump()
    raw["scoring"]["weights"]["intent"] = 0.9
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError):
        load_policy(p)


def test_policy_rejects_inverted_discount_limits(policy):
    raw = policy.model_dump()
    raw["discount"]["standard_limit"] = 25
    with pytest.raises(ValueError):
        Policy.model_validate(raw)


def test_approval_matrix_renders_from_policy(policy):
    md = render_approval_matrix(policy)
    assert "Discount > 20%" in md and "VP Sales" in md and policy.version in md
