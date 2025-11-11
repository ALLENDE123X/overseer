from pydantic import BaseModel, Field
from typing import Optional


class AgentClass(BaseModel):
    name: str
    description: str
    tools: list[str] = []
    policy_name: Optional[str] = None
    context_profile: Optional[str] = None


class Policy(BaseModel):
    name: str
    max_cost_usd: float = 5.0
    block_patterns: list[str] = []


class ContextProfile(BaseModel):
    name: str
    budget_tokens: int = 120000
    mounts: list[str] = []
    selectors: list[dict] = []
    transforms: list[dict] = []


class ProviderPool(BaseModel):
    name: str
    models: list[dict] = []
    routing: list[dict] = []


class Edge(BaseModel):
    from_node: str
    to_node: str
    on: list[str] = []
    parallel: bool = False
    join: Optional[str] = None


class Graph(BaseModel):
    name: str
    agents: list[str] = []
    dag: list[Edge] = []
    policy_name: Optional[str] = None


class Run(BaseModel):
    id: str
    graph: str
    inputs: dict = {}
    status: str = "pending"
    created_at: str
    parent_run: Optional[str] = None


class Event(BaseModel):
    run_id: str
    step: str
    type: str
    ts: str
    data: dict = {}

