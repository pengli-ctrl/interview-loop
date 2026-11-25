from pathlib import Path

from streamlit.testing.v1 import AppTest

import interview_loop.config as config


def test_demo_interview_starts_and_advances(monkeypatch):
    monkeypatch.setattr(config, "DEMO_MODE", True)

    import interview_loop.services.llm as llm
    import interview_loop.services.tts as tts

    monkeypatch.setattr(llm, "DEMO_MODE", True)
    monkeypatch.setattr(tts, "DEMO_MODE", True)

    app_path = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30).run()
    assert not at.exception

    at.button(key="start_interview").click().run(timeout=30)
    assert not at.exception
    assert at.session_state["current_question"]
    assert at.session_state["model_budget"].used_tokens > 0

    events = at.session_state["agent_run"].events
    assert any(event.event_type == "model.call" for event in events)
    assert any(event.event_type == "question.generated" for event in events)

    answer_mode = at.radio(key="answer_input_mode")
    answer_mode.set_value(answer_mode.options[1]).run()
    assert not at.exception

    at.text_area(key="text_answer").set_value("short answer")
    at.button(key="submit_text_answer").click().run(timeout=30)
    assert not at.exception
    assert not at.error, [item.value for item in at.error]
    assert at.session_state["current_stage_idx"] == 1

    for _ in range(12):
        if at.session_state["current_stage_idx"] >= 6:
            break
        at.text_area(key="text_answer").set_value("short answer")
        at.button(key="submit_text_answer").click().run(timeout=30)
        assert not at.exception
        assert not at.error, [item.value for item in at.error]

    assert at.session_state["current_stage_idx"] == 6
