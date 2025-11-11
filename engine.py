import asyncio
import json
from pathlib import Path
from datetime import datetime
from tools import files, tests, security
from context import compile_context
from routing import choose_model


# in-memory stores passed from app
_runs = {}
_graphs = {}
_events = {}
_context_profiles = {}
_policies = {}


def init_stores(runs, graphs, events, context_profiles, policies):
    """initialize references to app stores"""
    global _runs, _graphs, _events, _context_profiles, _policies
    _runs = runs
    _graphs = graphs
    _events = events
    _context_profiles = context_profiles
    _policies = policies


def emit_event(run_id: str, step: str, event_type: str, data: dict):
    """emit event to memory and persist to disk"""
    event = {
        "run_id": run_id,
        "step": step,
        "type": event_type,
        "ts": datetime.utcnow().isoformat(),
        "data": data
    }
    
    if run_id not in _events:
        _events[run_id] = []
    _events[run_id].append(event)
    
    # persist to disk
    data_dir = Path("./data") / run_id
    data_dir.mkdir(parents=True, exist_ok=True)
    
    with open(data_dir / "events.jsonl", "a") as f:
        f.write(json.dumps(event) + "\n")
    
    return event


def save_artifact(run_id: str, name: str, content: str):
    """save artifact to disk"""
    data_dir = Path("./data") / run_id
    data_dir.mkdir(parents=True, exist_ok=True)
    
    with open(data_dir / name, "w") as f:
        f.write(content)


async def run_node(run_id: str, node: str, run_events: list) -> dict:
    """execute a single node handler"""
    
    # compile context
    ctx = compile_context(
        _runs[run_id],
        node,
        "reviewer-default",
        run_events,
        _context_profiles
    )
    
    # choose model
    tokens = ctx["manifest"]["total_tokens"]
    model_choice = choose_model(tokens, node)
    
    # emit context event
    emit_event(run_id, node, "context_compiled", {
        "manifest": ctx["manifest"],
        "model": model_choice
    })
    
    # node-specific handlers (deterministic, no real llm calls)
    result = {}
    
    if node == "planner":
        result = {
            "target_files": ["app.py", "tests/test_app.py"],
            "hint": "test expects 42, app returns 41"
        }
        emit_event(run_id, node, "plan_ready", result)
    
    elif node == "py_fixer":
        # read app.py, fix the bug
        app_file = files.read("app.py")
        if "content" in app_file:
            fixed = app_file["content"].replace("return 41", "return 42")
            files.write("app.py", fixed)
            patch = {"file": "app.py", "change": "return 41 -> return 42"}
            save_artifact(run_id, "py_fixer_patch.json", json.dumps(patch, indent=2))
            result = {"patch": patch, "success": True}
        else:
            result = {"error": "app.py not found"}
        emit_event(run_id, node, "patch_created", result)
    
    elif node == "fe_fixer":
        # no-op for demo
        result = {"patch": None, "message": "no frontend changes needed"}
        emit_event(run_id, node, "patch_created", result)
    
    elif node == "test_writer":
        # append a simple assertion to tests if missing
        test_file = files.read("tests/test_app.py")
        if "content" in test_file:
            content = test_file["content"]
            if "assert answer == 42" not in content:
                # add another assertion
                content += "\n\ndef test_answer_type():\n    from app import compute\n    assert isinstance(compute(), int)\n"
                files.write("tests/test_app.py", content)
                result = {"added": "test_answer_type", "success": True}
            else:
                result = {"message": "tests already complete"}
        else:
            result = {"error": "test file not found"}
        emit_event(run_id, node, "test_updated", result)
    
    elif node == "aggregator":
        # pick py_fixer patch if present
        patches = []
        for e in run_events:
            if e.get("step") == "py_fixer" and e.get("type") == "patch_created":
                if e.get("data", {}).get("success"):
                    patches.append(e["data"]["patch"])
        
        result = {"selected_patch": patches[0] if patches else None}
        emit_event(run_id, node, "patch_selected", result)
    
    elif node == "tester":
        # run tests
        test_result = tests.run()
        result = test_result
        if test_result.get("passed"):
            emit_event(run_id, node, "tests_passed", result)
        else:
            emit_event(run_id, node, "tests_failed", result)
    
    elif node == "security":
        # scan repo
        scan_result = security.scan_repo()
        result = scan_result
        if scan_result.get("ok"):
            emit_event(run_id, node, "security_ok", result)
        else:
            emit_event(run_id, node, "security_failed", result)
    
    elif node == "release":
        # append to changelog
        changelog = files.read("CHANGELOG.md")
        content = changelog.get("content", "# Changelog\n\n")
        content += f"\n- {datetime.utcnow().isoformat()}: auto-release from run {run_id}\n"
        files.write("CHANGELOG.md", content)
        result = {"released": True}
        emit_event(run_id, node, "release_complete", result)
    
    else:
        result = {"error": f"unknown node: {node}"}
        emit_event(run_id, node, "error", result)
    
    # emit completion
    emit_event(run_id, node, "node_done", {"result": result})
    
    return result


async def execute_graph(run_id: str):
    """execute graph for a run with parallel fan-out and join support"""
    
    try:
        run = _runs[run_id]
        graph = _graphs[run["graph"]]
        
        run["status"] = "running"
        emit_event(run_id, "system", "run_started", {"graph": graph["name"]})
        
        # build adjacency map
        adj = {}  # node -> list of outgoing edges
        in_degree = {}  # node -> count of incoming edges
        join_groups = {}  # join node -> list of source nodes
        
        for edge in graph["dag"]:
            from_node = edge["from_node"]
            to_node = edge["to_node"]
            
            if from_node not in adj:
                adj[from_node] = []
            adj[from_node].append(edge)
            
            in_degree[to_node] = in_degree.get(to_node, 0) + 1
            in_degree.setdefault(from_node, 0)
            
            # track join nodes
            if edge.get("join"):
                if to_node not in join_groups:
                    join_groups[to_node] = []
                join_groups[to_node].append(from_node)
        
        # find start nodes (in_degree == 0)
        ready = [n for n in in_degree if in_degree[n] == 0]
        completed = set()
        completed_nodes = {}  # node -> result
        
        # execution loop
        while ready:
            # check for parallel edges from ready nodes
            parallel_tasks = []
            parallel_nodes = []
            sequential_node = None
            
            for node in ready:
                edges = adj.get(node, [])
                if edges and edges[0].get("parallel"):
                    # fan-out: run this node, then its children in parallel
                    if node not in completed:
                        result = await run_node(run_id, node, _events.get(run_id, []))
                        completed.add(node)
                        completed_nodes[node] = result
                    
                    # schedule parallel children
                    for edge in edges:
                        child = edge["to_node"]
                        parallel_tasks.append(run_node(run_id, child, _events.get(run_id, [])))
                        parallel_nodes.append(child)
                else:
                    sequential_node = node
                    break
            
            # execute parallel tasks if any
            if parallel_tasks:
                results = await asyncio.gather(*parallel_tasks)
                for node, result in zip(parallel_nodes, results):
                    completed.add(node)
                    completed_nodes[node] = result
                
                # remove parallel nodes from ready
                ready = [n for n in ready if n not in parallel_nodes and n not in completed]
                
                # check join nodes
                for join_node, sources in join_groups.items():
                    if all(s in completed for s in sources):
                        if join_node not in completed:
                            ready.append(join_node)
            
            elif sequential_node:
                # run sequential node
                if sequential_node not in completed:
                    result = await run_node(run_id, sequential_node, _events.get(run_id, []))
                    completed.add(sequential_node)
                    completed_nodes[sequential_node] = result
                
                ready.remove(sequential_node)
                
                # add children to ready based on edge conditions
                for edge in adj.get(sequential_node, []):
                    child = edge["to_node"]
                    
                    # check edge conditions
                    if edge.get("on"):
                        # check if any of the required event types were emitted
                        events = _events.get(run_id, [])
                        matches = any(
                            e.get("step") == sequential_node and e.get("type") in edge["on"]
                            for e in events
                        )
                        if not matches:
                            continue
                    
                    # check if all incoming edges are complete
                    if child in join_groups:
                        if all(s in completed for s in join_groups[child]):
                            if child not in ready and child not in completed:
                                ready.append(child)
                    else:
                        if child not in ready and child not in completed:
                            ready.append(child)
            else:
                break
        
        run["status"] = "succeeded"
        emit_event(run_id, "system", "run_completed", {"completed_nodes": list(completed)})
    
    except Exception as e:
        run["status"] = "failed"
        emit_event(run_id, "system", "run_failed", {"error": str(e)})
        raise


async def replay_from(run_id: str, from_step: str) -> str:
    """replay from a specific step (creates new run)"""
    
    original_run = _runs[run_id]
    
    # create new run
    new_run_id = f"{run_id}-replay-{from_step}"
    new_run = {
        "id": new_run_id,
        "graph": original_run["graph"],
        "inputs": original_run["inputs"],
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "parent_run": run_id
    }
    _runs[new_run_id] = new_run
    
    # copy events up to from_step
    original_events = _events.get(run_id, [])
    new_events = []
    
    found_step = False
    for event in original_events:
        if event["step"] == from_step:
            found_step = True
            break
        new_events.append(event)
    
    _events[new_run_id] = new_events
    
    # execute from from_step
    await execute_graph(new_run_id)
    
    return new_run_id

