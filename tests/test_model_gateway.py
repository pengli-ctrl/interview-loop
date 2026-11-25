from interview_loop.platform.model_gateway import ModelGateway, estimate_tokens


def test_model_gateway_routes_tasks():
    gateway = ModelGateway(completer=lambda system_prompt, user_msg: f"{system_prompt}|{user_msg}")
    result = gateway.complete("review", "system", "user")
    assert result.content == "system|user"
    assert result.task == "review"
    assert result.model
    assert result.estimated_input_tokens > 0


def test_unknown_task_uses_default_profile():
    gateway = ModelGateway(completer=lambda system_prompt, user_msg: "ok")
    result = gateway.complete("custom", "system", "user")
    assert result.prompt_version == "custom-v1"


def test_estimate_tokens():
    assert estimate_tokens("12345678") == 2
    assert estimate_tokens("") == 1
