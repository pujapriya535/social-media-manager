import logging
import os
import re
import json
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel
from google.adk.workflow import Workflow
from google.adk.agents import LlmAgent, Context
from google.adk.tools import AgentTool
from google.adk.events import RequestInput
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.models import Gemini

from .config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Wire MCP Server
mcp_toolset = MCPToolset(
    name="SocialMediaMCP",
    command="uv",
    args=["run", os.path.join(os.path.dirname(__file__), "mcp_server.py")]
)

class GraphState(BaseModel):
    task: str = ""
    strategy: str = ""
    human_approved: bool = False

content_agent = LlmAgent(
    name="ContentAgent",
    model=Gemini(model=config.model),
    instruction="You are a social media manager. Given a task or trend, draft engaging social media posts. You can use tools to find trending hashtags and schedule posts.",
    tools=[mcp_toolset]
)

analytics_agent = LlmAgent(
    name="AnalyticsAgent",
    model=Gemini(model=config.model),
    instruction="You are a data analyst for social media. Given a topic, provide simulated engagement metrics and optimal posting times. You can use tools to get competitor metrics.",
    tools=[mcp_toolset]
)

orchestrator = LlmAgent(
    name="Orchestrator",
    model=Gemini(model=config.model),
    instruction="You coordinate the social media strategy. Use the ContentAgent to draft posts and the AnalyticsAgent to get metrics. Return the comprehensive final strategy.",
    tools=[
        AgentTool(agent=content_agent, description="Use this to draft social media posts."),
        AgentTool(agent=analytics_agent, description="Use this to get engagement metrics and timing.")
    ]
)

def _audit_log(action: str, details: str, severity: str = "INFO"):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "details": details,
        "severity": severity
    }
    logger.info(f"AUDIT LOG: {json.dumps(log_entry)}")

def security_checkpoint(ctx: Context[GraphState]) -> str:
    query = str(ctx.input) if ctx.input else ctx.state.task
    
    # 1. Domain-specific rule (Content Filter)
    banned_words = ["hate", "violence", "spam"]
    if any(word in query.lower() for word in banned_words):
        _audit_log("content_filter", "Blocked request containing banned words", "CRITICAL")
        return "handle_security_event"

    # 2. PII Scrubbing (Email, Phone)
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    phone_pattern = r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
    
    scrubbed_query = re.sub(email_pattern, "[REDACTED_EMAIL]", query)
    scrubbed_query = re.sub(phone_pattern, "[REDACTED_PHONE]", scrubbed_query)
    
    if scrubbed_query != query:
        _audit_log("pii_scrub", "Redacted email/phone from input", "WARNING")
    
    # 3. Prompt Injection Detection
    injection_keywords = ["ignore previous instructions", "system prompt", "bypass", "override"]
    if any(kw in scrubbed_query.lower() for kw in injection_keywords):
        _audit_log("injection_detect", "Detected potential prompt injection", "CRITICAL")
        return "handle_security_event"

    _audit_log("security_pass", "Input passed all security checks", "INFO")
    ctx.state.task = scrubbed_query
    return "orchestrator"

def handle_security_event(ctx: Context[GraphState]) -> str:
    ctx.state.strategy = "Task aborted due to security policy violation."
    ctx.state.human_approved = False
    return "final_output"

def orchestrate_task(ctx: Context[GraphState]) -> str:
    logger.info(f"Orchestrating task: {ctx.state.task}")
    response = orchestrator.run(ctx.state.task)
    ctx.state.strategy = response.text
    return "human_review"

def human_review(ctx: Context[GraphState]) -> RequestInput:
    return RequestInput(
        prompt=f"Please review the social media strategy:\n{ctx.state.strategy}\nApprove? (yes/no)"
    )

def process_review(ctx: Context[GraphState]) -> str:
    user_input = str(ctx.input).lower()
    if "yes" in user_input or "y" in user_input:
        ctx.state.human_approved = True
        _audit_log("human_review", "Strategy approved by human", "INFO")
    else:
        ctx.state.human_approved = False
        _audit_log("human_review", "Strategy denied by human", "WARNING")
    return "final_output"

def final_output(ctx: Context[GraphState]) -> str:
    if ctx.state.human_approved:
        return f"Approved Strategy:\n{ctx.state.strategy}"
    else:
        return "Strategy was denied or requires changes."

workflow = Workflow(
    name="SocialMediaWorkflow",
    state_type=GraphState
)

workflow.add_node("security_checkpoint", security_checkpoint)
workflow.add_node("handle_security_event", handle_security_event)
workflow.add_node("orchestrator", orchestrate_task)
workflow.add_node("human_review", human_review)
workflow.add_node("process_review", process_review)
workflow.add_node("final_output", final_output)

# Connect edges
workflow.add_edge("security_checkpoint", "orchestrator")
workflow.add_edge("security_checkpoint", "handle_security_event")
workflow.add_edge("handle_security_event", "final_output")
workflow.add_edge("orchestrator", "human_review")
workflow.add_edge("human_review", "process_review")
workflow.add_edge("process_review", "final_output")

workflow.set_entry_point("security_checkpoint")

app = workflow
