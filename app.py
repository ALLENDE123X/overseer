import asyncio
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
from models import Policy, ContextProfile, ProviderPool, Graph, Run, Edge
import engine


# in-memory stores
policies = {}
context_profiles = {}
provider_pool = None
graphs = {}
runs = {}
events = {}
run_queue = []


# request models
class CreateRunRequest(BaseModel):
    graph: str
    inputs: dict = {}


class ReplayRequest(BaseModel):
    from_step: str


# fastapi app
app = FastAPI(title="runos-mini")


@app.on_event("startup")
async def startup():
    """seed data and start background worker"""
    
    # initialize engine stores
    engine.init_stores(runs, graphs, events, context_profiles, policies)
    
    # ensure sample repo exists
    sample_dir = Path("examples/sample_repo")
    sample_dir.mkdir(parents=True, exist_ok=True)
    
    # seed default policy
    policies["default"] = {
        "name": "default",
        "max_cost_usd": 5.0,
        "block_patterns": ["eval("]
    }
    
    # seed default context profile
    context_profiles["reviewer-default"] = {
        "name": "reviewer-default",
        "budget_tokens": 120000,
        "mounts": [],
        "selectors": [],
        "transforms": []
    }
    
    # seed default graph
    graphs["git-to-prod-multi"] = {
        "name": "git-to-prod-multi",
        "agents": ["planner", "py_fixer", "fe_fixer", "test_writer", "aggregator", "tester", "security", "release"],
        "dag": [
            # planner fans out to 3 parallel agents
            {"from_node": "planner", "to_node": "py_fixer", "on": [], "parallel": True, "join": None},
            {"from_node": "planner", "to_node": "fe_fixer", "on": [], "parallel": True, "join": None},
            {"from_node": "planner", "to_node": "test_writer", "on": [], "parallel": True, "join": None},
            
            # all 3 join into aggregator
            {"from_node": "py_fixer", "to_node": "aggregator", "on": [], "parallel": False, "join": "all"},
            {"from_node": "fe_fixer", "to_node": "aggregator", "on": [], "parallel": False, "join": "all"},
            {"from_node": "test_writer", "to_node": "aggregator", "on": [], "parallel": False, "join": "all"},
            
            # sequential pipeline
            {"from_node": "aggregator", "to_node": "tester", "on": ["patch_selected"], "parallel": False, "join": None},
            {"from_node": "tester", "to_node": "security", "on": ["tests_passed"], "parallel": False, "join": None},
            {"from_node": "security", "to_node": "release", "on": ["security_ok"], "parallel": False, "join": None}
        ],
        "policy_name": "default"
    }
    
    # start background worker
    asyncio.create_task(background_worker())


async def background_worker():
    """poll run queue and execute pending runs"""
    while True:
        await asyncio.sleep(0.5)
        
        # find pending runs
        pending = [r for r in runs.values() if r["status"] == "pending"]
        
        for run in pending:
            run["status"] = "running"
            try:
                await engine.execute_graph(run["id"])
            except Exception as e:
                print(f"error executing run {run['id']}: {e}")
                run["status"] = "failed"


@app.get("/health")
def health():
    """health check"""
    return {"status": "ok", "runs": len(runs), "graphs": len(graphs)}


@app.post("/policies")
def create_policy(policy: Policy):
    """register a policy"""
    policies[policy.name] = policy.dict()
    return {"ok": True, "name": policy.name}


@app.post("/contextprofiles")
def create_context_profile(profile: ContextProfile):
    """register a context profile"""
    context_profiles[profile.name] = profile.dict()
    return {"ok": True, "name": profile.name}


@app.post("/providerpool")
def create_provider_pool(pool: ProviderPool):
    """set provider pool"""
    global provider_pool
    provider_pool = pool.dict()
    return {"ok": True, "name": pool.name}


@app.post("/graphs")
def create_graph(graph: Graph):
    """register a graph"""
    graphs[graph.name] = graph.dict()
    return {"ok": True, "name": graph.name}


@app.get("/graphs/{name}")
def get_graph(name: str):
    """get graph by name"""
    if name not in graphs:
        raise HTTPException(status_code=404, detail="graph not found")
    return graphs[name]


@app.post("/runs")
def create_run(req: CreateRunRequest):
    """create a new run"""
    if req.graph not in graphs:
        raise HTTPException(status_code=404, detail="graph not found")
    
    run_id = f"run-{len(runs)+1}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    run = {
        "id": run_id,
        "graph": req.graph,
        "inputs": req.inputs,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "parent_run": None
    }
    
    runs[run_id] = run
    events[run_id] = []
    
    return {"ok": True, "run_id": run_id, "status": "pending"}


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    """get run by id"""
    if run_id not in runs:
        raise HTTPException(status_code=404, detail="run not found")
    return runs[run_id]


@app.get("/runs/{run_id}/events")
def get_run_events(run_id: str):
    """get events for a run"""
    if run_id not in runs:
        raise HTTPException(status_code=404, detail="run not found")
    return {"run_id": run_id, "events": events.get(run_id, [])}


@app.post("/runs/{run_id}/replay")
async def replay_run(run_id: str, req: ReplayRequest):
    """replay run from a specific step"""
    if run_id not in runs:
        raise HTTPException(status_code=404, detail="run not found")
    
    new_run_id = await engine.replay_from(run_id, req.from_step)
    
    return {"ok": True, "new_run_id": new_run_id, "parent_run": run_id}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """simple html dashboard"""
    
    rows = ""
    for run_id, run in runs.items():
        event_count = len(events.get(run_id, []))
        rows += f"""
        <tr>
            <td>{run_id}</td>
            <td>{run['graph']}</td>
            <td><span class="status-{run['status']}">{run['status']}</span></td>
            <td>{event_count}</td>
            <td><a href="/runs/{run_id}/events">view events</a></td>
        </tr>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>runos-mini dashboard</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                max-width: 1200px;
                margin: 40px auto;
                padding: 0 20px;
                background: #f5f5f5;
            }}
            h1 {{
                color: #333;
                border-bottom: 3px solid #4CAF50;
                padding-bottom: 10px;
            }}
            table {{
                width: 100%;
                background: white;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                border-collapse: collapse;
            }}
            th {{
                background: #4CAF50;
                color: white;
                text-align: left;
                padding: 15px;
                font-weight: 600;
            }}
            td {{
                padding: 12px 15px;
                border-bottom: 1px solid #eee;
            }}
            tr:last-child td {{
                border-bottom: none;
            }}
            tr:hover {{
                background: #f9f9f9;
            }}
            a {{
                color: #4CAF50;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            .status-pending {{
                color: #FF9800;
                font-weight: 600;
            }}
            .status-running {{
                color: #2196F3;
                font-weight: 600;
            }}
            .status-succeeded {{
                color: #4CAF50;
                font-weight: 600;
            }}
            .status-failed {{
                color: #F44336;
                font-weight: 600;
            }}
            .info {{
                background: white;
                padding: 20px;
                border-radius: 8px;
                margin: 20px 0;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            code {{
                background: #f4f4f4;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Monaco', 'Courier New', monospace;
            }}
        </style>
    </head>
    <body>
        <h1>runos-mini dashboard</h1>
        
        <div class="info">
            <p><strong>Total Runs:</strong> {len(runs)} | <strong>Graphs:</strong> {len(graphs)} | <strong>Policies:</strong> {len(policies)}</p>
            <p>Create a run: <code>curl -X POST http://localhost:8000/runs -H "content-type: application/json" -d '{{"graph":"git-to-prod-multi","inputs":{{"pr_number":42}}}}'</code></p>
        </div>
        
        <table>
            <thead>
                <tr>
                    <th>Run ID</th>
                    <th>Graph</th>
                    <th>Status</th>
                    <th>Events</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {rows if rows else '<tr><td colspan="5" style="text-align: center; color: #999;">no runs yet</td></tr>'}
            </tbody>
        </table>
    </body>
    </html>
    """
    
    return html


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

