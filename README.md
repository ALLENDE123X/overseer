# AgentOS: Kubernetes for Multi-Agent Systems

a minimal multi-agent orchestration system with declarative graphs, parallel execution, and replay

## features

- **infra-first**: control plane + runner + events + replay
- **declarative graphs**: fan-out/fan-in with per-agent policies
- **context engineering**: manifest + budget logging
- **scaling/routing**: provider pool + simple router
- **demo workload**: git→prod pipeline with 3 parallel agents

## quickstart

```bash
# setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# start server
uvicorn app:app --reload
```

server runs on http://localhost:8000

## usage

### create a run

```bash
curl -X POST http://localhost:8000/runs \
  -H "content-type: application/json" \
  -d '{"graph":"git-to-prod-multi","inputs":{"pr_number":42}}'
```

response:
```json
{
  "ok": true,
  "run_id": "run-1-20251111120000",
  "status": "pending"
}
```

### view dashboard

open http://localhost:8000/dashboard in your browser to see:
- all runs with status
- event counts
- links to view events

### view events

```bash
curl http://localhost:8000/runs/{run_id}/events
```

### replay from a step

```bash
curl -X POST http://localhost:8000/runs/{run_id}/replay \
  -H "content-type: application/json" \
  -d '{"from_step":"tester"}'
```

## architecture

### reference workflow: git-to-prod-multi

1. **planner** → analyzes failing tests
2. **fan-out** (parallel):
   - py_fixer: fixes python bug
   - fe_fixer: handles frontend (no-op in demo)
   - test_writer: adds test cases
3. **aggregator** → picks best patch (join point)
4. **tester** → runs pytest
5. **security** → scans for issues
6. **release** → updates changelog

### components

- `app.py` - fastapi control plane + background worker
- `models.py` - pydantic models
- `engine.py` - graph executor with parallel execution
- `context.py` - context compilation + budgeting
- `routing.py` - provider pool + model selection
- `tools/` - file ops, test runner, security scanner
- `examples/sample_repo/` - demo repo with buggy code

### data persistence

- events: `./data/{run_id}/events.jsonl`
- artifacts: `./data/{run_id}/*.json`

## api reference

### endpoints

- `GET /health` - health check
- `POST /policies` - register policy
- `POST /contextprofiles` - register context profile
- `POST /providerpool` - set provider pool
- `POST /graphs` - register graph
- `GET /graphs/{name}` - get graph
- `POST /runs` - create run
- `GET /runs/{id}` - get run
- `GET /runs/{id}/events` - get events
- `POST /runs/{id}/replay` - replay from step
- `GET /dashboard` - html dashboard

## acceptance tests

the demo workflow:
1. creates a run with 8+ events
2. includes context manifest and model choice per node
3. fixes the bug (return 41 → 42)
4. passes pytest (1 test passing)
5. shows status progression: pending → running → succeeded

## design principles

- lowercase comments
- no external llm calls (deterministic demo)
- in-memory for speed, json files for persistence
- no db, no docker, no frontend framework
- small functions, direct logic

