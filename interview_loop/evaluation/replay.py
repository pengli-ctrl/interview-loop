from dataclasses import dataclass, field


class ReplayError(ValueError):
    pass


@dataclass(frozen=True)
class ReplayReport:
    run_id: str
    trace_id: str
    final_stage: int
    stage_sequence: list[int] = field(default_factory=list)
    question_count: int = 0
    evaluation_completed: bool = False
    record_exported: bool = False
    completed: bool = False


def replay_agent_run(run: dict) -> ReplayReport:
    events = run.get("events", [])
    current_stage = 0
    stage_sequence = [current_stage]
    question_count = 0
    evaluation_completed = False
    record_exported = False
    completed_event = False

    for index, event in enumerate(events):
        event_type = event.get("event_type")
        payload = event.get("payload", {})
        if event_type == "stage.transition":
            from_index = int(payload.get("from_index", -1))
            to_index = int(payload.get("to_index", -1))
            if from_index != current_stage:
                raise ReplayError(
                    f"Event {index}: transition starts at {from_index}, "
                    f"expected {current_stage}"
                )
            if to_index <= current_stage:
                raise ReplayError(
                    f"Event {index}: non-forward stage transition "
                    f"{current_stage} -> {to_index}"
                )
            current_stage = to_index
            stage_sequence.append(to_index)
        elif event_type == "question.generated":
            question_count += 1
            if "stage_index" in payload:
                event_stage = int(payload["stage_index"])
                if event_stage != current_stage:
                    raise ReplayError(
                        f"Event {index}: question stage {event_stage}, "
                        f"replay stage {current_stage}"
                    )
        elif event_type == "evaluation.completed":
            evaluation_completed = True
        elif event_type == "record.exported":
            record_exported = True
        elif event_type == "run.completed":
            completed_event = True

    status = run.get("status")
    if status == "completed" and not completed_event:
        raise ReplayError("Completed run is missing run.completed event")
    return ReplayReport(
        run_id=str(run.get("run_id", "")),
        trace_id=str(run.get("trace_id", "")),
        final_stage=current_stage,
        stage_sequence=stage_sequence,
        question_count=question_count,
        evaluation_completed=evaluation_completed,
        record_exported=record_exported,
        completed=status == "completed" and completed_event,
    )
