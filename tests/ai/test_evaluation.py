from vnecom.ai.evaluation import evaluate


def test_offline_chat_regressions():
    result = evaluate()
    assert result["passed"], result["results"]
    assert result["total"] >= 14
    assert result["live_model_tested"] is False
