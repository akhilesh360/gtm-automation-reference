from src.policy import render_commercial_policy_metadata


def test_commercial_policy_metadata_reflects_policy(policy):
    xml = render_commercial_policy_metadata(policy)
    assert f"<label>Current ({policy.version})</label>" in xml
    assert "<field>VP_ACV_Threshold__c</field>" in xml and f">{policy.acv.vp_threshold:g}<" in xml
    assert ", ".join(policy.payment_terms.standard) in xml
    assert xml.count("<values>") == 6
