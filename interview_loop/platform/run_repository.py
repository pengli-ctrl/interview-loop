from interview_loop.platform.agent_run import AgentRun


class AgentRunNotFoundError(LookupError):
    pass


class InMemoryAgentRunRepository:
    def __init__(self) -> None:
        self._runs: dict[str, AgentRun] = {}

    def create(self, run: AgentRun) -> AgentRun:
        self._runs[run.run_id] = run
        return run

    def get(self, run_id: str) -> AgentRun:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise AgentRunNotFoundError(run_id) from exc

    def save(self, run: AgentRun) -> AgentRun:
        self._runs[run.run_id] = run
        return run

    def list(self, tenant_id: str | None = None) -> list[AgentRun]:
        runs = list(self._runs.values())
        if tenant_id is not None:
            runs = [run for run in runs if run.tenant_id == tenant_id]
        return runs
