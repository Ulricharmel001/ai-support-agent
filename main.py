"""
Customer Support AI Agent — Starter Code
==========================================
Your task is to complete this file by implementing all sections marked
with # TODO comments.

Reference the project instructions and rubric for guidance.
Work through each section yourself.

Run locally (after filling in config values):
  uv run main.py '{"prompt": "Hello", "customer_id": "CUST-123", "session_id": "s1"}'

Deploy to AgentCore:
  agentcore deploy

Invoke deployed agent:
  agentcore invoke '{"prompt": "Hello", "customer_id": "CUST-123", "session_id": "s1"}'
"""

# ── Imports ───────────────────────────────────────────────────────────────────
# These imports are provided. Do not remove them.
from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory import MemoryClient
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamable_http_client
import argparse, json
import os, asyncio, boto3
from strands.hooks import (
    HookProvider, AfterInvocationEvent, HookRegistry, MessageAddedEvent,
)
import logging
import uuid
import nest_asyncio
from typing import Dict
from bedrock_agentcore.tools.code_interpreter_client import code_session
from strands_tools.browser import AgentCoreBrowser


logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("CSAI_Agent")

# Allow the sync MCP client helpers to run inside the async AgentCore entrypoint.
nest_asyncio.apply()

# ── TODO 1 — App Initialisation ───────────────────────────────────────────────
# Create a BedrockAgentCoreApp instance.
# This registers the ASGI server for AgentCore deployment.
# There must be exactly one instance per deployment.
#

# Hint: app = BedrockAgentCoreApp()

# TODO: Create the BedrockAgentCoreApp instance
app = BedrockAgentCoreApp()


# Suppress interactive tool-consent prompts (required in headless deployments).
os.environ["BYPASS_TOOL_CONSENT"] = "true"


# ── TODO 2 — Configuration ────────────────────────────────────────────────────
# Replace the placeholder strings with your actual AWS resource values.
# You collected these in the infrastructure setup section of the project instructions.
#
# GATEWAY_URL format: https://<alias>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp
# This starter uses an unsigned MCP connection and therefore assumes the
# project Gateway is configured with the NONE authorizer.
# KB_ID       format: 10-character alphanumeric string from the KB console
# REGION:     your AWS region, e.g. "us-east-1"
# MEMORY_ID   format: shown in the AgentCore Memory console

GATEWAY_URL = "https://customersupportgateway-yexbxqgy7e.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"   # TODO: Replace with your Gateway URL
KB_ID       = "O3G5Q7BGUN"          # TODO: Replace with your Knowledge Base ID
REGION      = "us-east-1"        # TODO: Replace with your AWS region
MEMORY_ID   = "CustomerSupportMemory-5Jds0j6vL5"        # TODO: Replace with your Memory ID


# ── TODO 3 — Model and Clients ────────────────────────────────────────────────
# Create:
#   1. A BedrockModel using model_id "global.amazon.nova-2-lite-v1:0"
#   2. A MemoryClient with region_name=REGION
#   3. A boto3 client for the "bedrock-agent-runtime" service in REGION
#
# Hint: model = BedrockModel(model_id=model_id)

model_id = "global.amazon.nova-2-lite-v1:0"

# TODO: Create the BedrockModel instance
model = BedrockModel(model_id=model_id)

# TODO: Create the MemoryClient instance
memory_client = MemoryClient(region_name=REGION)

# TODO: Create the boto3 bedrock-agent-runtime client
_bedrock_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)


# ── TODO 4 — Namespace Helper ─────────────────────────────────────────────────
# Implement get_namespaces() to return a dict mapping strategy type to
# namespace template string.
#
# Steps:
#   1. Call mem_client.get_memory_strategies(memory_id) to get strategy list
#   2. Read the namespace from strategy["namespaceTemplates"][0].
#      For compatibility with older AgentCore responses, fall back to
#      strategy["namespaces"][0] when namespaceTemplates is absent.
#
# Example output:
#   { "SEMANTIC": "cs_agent/{actorId}/facts",
#     "USER_PREFERENCE": "cs_agent/{actorId}/preferences" }

def get_namespaces(mem_client: MemoryClient, memory_id: str) -> Dict:
    """Return a dict mapping strategy type → namespace template string."""
    namespaces: Dict[str, str] = {}
    try:
        strategies = mem_client.get_memory_strategies(memory_id)
    except Exception as e:
        logger.warning("Unable to load memory strategies: %s", e)
        return namespaces

    for strategy in strategies or []:
        templates = strategy.get("namespaceTemplates") or strategy.get("namespaces") or []
        strategy_type = strategy.get("type") or strategy.get("memoryStrategyType")
        if templates and strategy_type:
            namespaces[strategy_type] = templates[0]
    return namespaces


# ── TODO 5 — Memory Hook ──────────────────────────────────────────────────────
# Implement MemoryHook, a HookProvider subclass that adds long-term memory.
#
# The class needs:
#   __init__(self, actor_id, session_id, memory_client, memory_id)
#     — store all four as instance attributes
#     — call get_namespaces() and store the result as self.namespaces
#
#   retrieve_customer_context(self, event: MessageAddedEvent)
#     — only runs for plain-text user messages (not tool results)
#     — for each strategy namespace, call memory_client.retrieve_memories(
#          memory_id, namespace (formatted with actorId), query, top_k=5)
#     — collect non-empty memory texts tagged with their strategy type
#     — if any memories found, prepend them to the user message as:
#          "Customer Context:\n<memories>\n\n<original_message>"
#
#   save_support_interaction(self, event: AfterInvocationEvent)
#     — walk the message list backwards to find the last plain-text user
#       query and the last assistant response
#     — call memory_client.create_event(memory_id, actor_id, session_id,
#          messages=[(customer_query, "USER"), (agent_response, "ASSISTANT")])
#
#   register_hooks(self, registry: HookRegistry)
#     — register retrieve_customer_context on MessageAddedEvent
#     — register save_support_interaction on AfterInvocationEvent

class MemoryHook(HookProvider):
    """Long-term memory hook for the customer support agent."""

    def __init__(
        self,
        actor_id: str,
        session_id: str,
        memory_client: MemoryClient,
        memory_id: str,
    ):
        self.actor_id = actor_id
        self.session_id = session_id
        self.memory_client = memory_client
        self.memory_id = memory_id
        self.namespaces = get_namespaces(memory_client, memory_id)

    @staticmethod
    def _text_from_content(content) -> str:
        """Flatten a Strands message content block into plain text."""
        if isinstance(content, str):
            return content.strip()
        if not isinstance(content, list):
            return ""
        parts = [
            block["text"]
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ]
        return " ".join(parts).strip()

    @staticmethod
    def _has_tool_block(content) -> bool:
        """Return True when a message carries tool use/result blocks."""
        if not isinstance(content, list):
            return False
        return any(
            isinstance(block, dict) and ("toolResult" in block or "toolUse" in block)
            for block in content
        )

    def retrieve_customer_context(self, event: MessageAddedEvent):
        """Retrieve relevant memories and prepend them to the user message."""
        messages = getattr(event.agent, "messages", None) or []
        if not messages:
            return

        message = messages[-1]
        if message.get("role") != "user":
            return

        content = message.get("content")
        if self._has_tool_block(content):
            return

        query = self._text_from_content(content)
        if not query:
            return

        memories = []
        for strategy_type, namespace in self.namespaces.items():
            formatted_namespace = namespace.format(actorId=self.actor_id)
            try:
                records = self.memory_client.retrieve_memories(
                    self.memory_id,
                    namespace=formatted_namespace,
                    query=query,
                    top_k=5,
                )
            except Exception as e:
                logger.warning(
                    "Memory retrieval failed for %s: %s", strategy_type, e
                )
                continue

            for record in records or []:
                record_content = record.get("content") or {}
                text = (
                    record_content.get("text")
                    if isinstance(record_content, dict)
                    else None
                )
                if text:
                    memories.append(f"[{strategy_type}] {text}")

        if memories:
            context = "Customer Context:\n" + "\n".join(memories)
            message["content"] = [{"text": f"{context}\n\n{query}"}]

    def save_support_interaction(self, event: AfterInvocationEvent):
        """Save the completed turn to memory after the agent responds."""
        messages = getattr(event.agent, "messages", None) or []
        customer_query = None
        agent_response = None

        for message in reversed(messages):
            content = message.get("content")
            text = self._text_from_content(content)
            if not text:
                continue

            if message.get("role") == "assistant" and agent_response is None:
                agent_response = text
            elif (
                message.get("role") == "user"
                and customer_query is None
                and not self._has_tool_block(content)
            ):
                customer_query = text

            if customer_query and agent_response:
                break

        if not customer_query or not agent_response:
            return

        try:
            self.memory_client.create_event(
                self.memory_id,
                self.actor_id,
                self.session_id,
                messages=[
                    (customer_query, "USER"),
                    (agent_response, "ASSISTANT"),
                ],
            )
        except Exception as e:
            logger.warning("Failed to save support interaction: %s", e)

    def register_hooks(self, registry: HookRegistry) -> None:  # type: ignore
        """Register both memory callbacks."""
        registry.add_callback(MessageAddedEvent, self.retrieve_customer_context)
        registry.add_callback(AfterInvocationEvent, self.save_support_interaction)


# ── TODO 6 — Knowledge Base Tool ─────────────────────────────────────────────
# Implement search_knowledge_base(query) using the @tool decorator.
#
# Steps:
#   1. Guard: if KB_ID is empty return "Knowledge base not configured."
#   2. Call _bedrock_runtime.retrieve(
#          knowledgeBaseId=KB_ID,
#          retrievalQuery={"text": query}
#      )
#   3. Extract resp["retrievalResults"]; return a message if empty
#   4. Join the text chunks with "\n---\n" and return the result
#
# The docstring is the tool description — the model uses it to decide when
# to call this tool, so keep it clear and accurate.

@tool
def search_knowledge_base(query: str) -> str:
    """
    Search the Amazon product catalog and support knowledge base.
    Use this for product specifications, return policies, warranty
    information, loyalty program details, and order status definitions.

    Args:
        query: The question or topic to search for

    Returns:
        Relevant information retrieved from the knowledge base
    """
    if not KB_ID:
        return "Knowledge base not configured."

    try:
        response = _bedrock_runtime.retrieve(
            knowledgeBaseId=KB_ID,
            retrievalQuery={"text": query},
        )
    except Exception as e:
        logger.warning("Knowledge base retrieval failed: %s", e)
        return f"Knowledge base search failed: {e}"

    results = response.get("retrievalResults", [])
    if not results:
        return "No relevant information found in the knowledge base."

    chunks = []
    for result in results:
        content = result.get("content") or {}
        text = content.get("text") if isinstance(content, dict) else None
        if text:
            chunks.append(text)

    if not chunks:
        return "No relevant information found in the knowledge base."
    return "\n---\n".join(chunks)


# ── TODO 7 — Loyalty Discount Tool (Code Interpreter) ────────────────────────
# Implement calculate_loyalty_discount() using the @tool decorator.
#
# The tool must:
#   1. Build a self-contained Python code string that:
#        • Defines earn_rates: {"standard": 1, "device": 2, "fresh": 5}
#        • Defines tier_rates: {"Silver": 0.00, "Gold": 0.10, "Platinum": 0.15}
#        • Calculates points_redeemed (floor to nearest 500, cap at 50% of order)
#        • Calculates tier_discount (applied to subtotal after points)
#        • Calculates final_total, total_savings, points_earned, remaining_points
#        • Prints a JSON result dict
#   2. Execute the code with code_session(REGION).invoke("executeCode", {...})
#      using language="python" and clearContext=True
#   3. Return the first result event as a JSON string
#   4. Include a fallback that computes only the tier discount if the
#      Code Interpreter is unavailable

@tool
def calculate_loyalty_discount(
    loyalty_points: int,
    tier: str,
    order_total: float,
    product_category: str = "standard",
) -> str:
    """
    Calculate the loyalty discount for a customer order using the
    AgentCore Code Interpreter. Runs exact arithmetic in a secure sandbox.

    Args:
        loyalty_points:   Customer's current points balance
        tier:             Customer tier — Silver, Gold, or Platinum
        order_total:      Order total in USD
        product_category: standard, device, or fresh

    Returns:
        Full discount breakdown and final price
    """
    code = f'''
import json

earn_rates = {{"standard": 1, "device": 2, "fresh": 5}}
tier_rates = {{"Silver": 0.00, "Gold": 0.10, "Platinum": 0.15}}

loyalty_points = {int(loyalty_points)}
tier = {tier!r}
order_total = {float(order_total)}
product_category = {product_category!r}

tier_rate = tier_rates.get(tier, 0.00)
earn_rate = earn_rates.get(product_category, 1)

available_points = (loyalty_points // 500) * 500
max_points = (int((order_total * 0.5) * 100) // 500) * 500
points_redeemed = min(available_points, max_points)

points_value = points_redeemed / 100.0
subtotal_after_points = order_total - points_value
tier_discount = subtotal_after_points * tier_rate
final_total = subtotal_after_points - tier_discount
total_savings = points_value + tier_discount
points_earned = int(final_total * earn_rate)
remaining_points = loyalty_points - points_redeemed + points_earned

result = {{
    "loyalty_points": loyalty_points,
    "tier": tier,
    "order_total": round(order_total, 2),
    "product_category": product_category,
    "points_redeemed": points_redeemed,
    "points_value": round(points_value, 2),
    "subtotal_after_points": round(subtotal_after_points, 2),
    "tier_discount_rate": tier_rate,
    "tier_discount": round(tier_discount, 2),
    "final_total": round(final_total, 2),
    "total_savings": round(total_savings, 2),
    "points_earned": points_earned,
    "remaining_points": remaining_points,
}}
print(json.dumps(result))
'''

    try:
        with code_session(REGION) as code_client:
            response = code_client.invoke(
                "executeCode",
                {"language": "python", "code": code, "clearContext": True},
            )
            for event in response.get("stream", []):
                result = event.get("result") or {}
                for content in result.get("content", []) or []:
                    if content.get("type") == "text" and content.get("text"):
                        return content["text"].strip()
        raise RuntimeError("Code Interpreter returned no output")

    except Exception as e:
        logger.warning("Code Interpreter unavailable, using fallback: %s", e)
        tier_rate = {"Silver": 0.0, "Gold": 0.10, "Platinum": 0.15}.get(tier, 0.0)
        tier_discount = order_total * tier_rate
        final_total = order_total - tier_discount
        return json.dumps(
            {
                "error": str(e),
                "tier": tier,
                "order_total": round(order_total, 2),
                "tier_discount_rate": tier_rate,
                "tier_discount": round(tier_discount, 2),
                "final_total": round(final_total, 2),
                "note": (
                    "Code Interpreter unavailable; fallback applied the tier "
                    "discount only."
                ),
            }
        )


# ── TODO 8 — Agent Entrypoint ─────────────────────────────────────────────────
# Implement the invoke() function decorated with @app.entrypoint.
#
# Steps:
#   1. Extract user_input, actor_id, and session_id from the payload
#      (generate a UUID if session_id is missing)
#   2. Instantiate MemoryHook for this actor/session
#   3. Instantiate AgentCoreBrowser(region=REGION)
#   4. Build the tools list: [search_knowledge_base, calculate_loyalty_discount,
#                              agent_core_browser.browser]
#   5. Connect to the Gateway via MCPClient, load gateway_tools, extend tools list
#   6. Create and invoke the Agent with all tools, hooks, and system_prompt
#   7. Return the text from the first content block of the response
#   8. Handle exceptions gracefully

SYSTEM_PROMPT = """You are a friendly, efficient customer support agent for the Amazon store.

You help customers with:
- Order tracking and status (use the order lookup tools)
- Refunds, returns, and prepaid return labels (use the refund tools)
- Product details, return policies, warranties, and loyalty program questions
  (use the knowledge base tool)
- Loyalty discount calculations (use the loyalty discount tool)
- General web research when a customer needs current external information
  (use the browser tool)

Guidelines:
- Always use the available tools to look up real data instead of guessing.
- Be concise, clear, and empathetic.
- Confirm order and customer IDs before irreversible actions such as refunds.
- Never invent order numbers, refund IDs, tracking numbers, or policy details.
- If a tool returns an error or no results, say so honestly and suggest the
  next step (for example, verifying the order ID or contacting a human agent).
"""


@app.entrypoint
async def invoke(payload, context=None):
    """
    Main handler called by AgentCore for every incoming request.

    Expected payload keys:
      prompt      (str, required) — the customer's message
      customer_id (str, optional) — unique customer identifier
      session_id  (str, optional) — session identifier; generated if absent
    """
    try:
        user_input = (payload or {}).get("prompt", "")
        actor_id = (payload or {}).get("customer_id") or "anonymous"
        session_id = (payload or {}).get("session_id") or str(uuid.uuid4())

        if not user_input:
            return "Please include a 'prompt' describing how I can help."

        memory_hook = MemoryHook(actor_id, session_id, memory_client, MEMORY_ID)
        agent_core_browser = AgentCoreBrowser(region=REGION)

        tools = [
            search_knowledge_base,
            calculate_loyalty_discount,
            agent_core_browser.browser,
        ]

        with MCPClient(lambda: streamable_http_client(GATEWAY_URL)) as mcp_client:
            tools.extend(mcp_client.list_tools_sync())

            agent = Agent(
                model=model,
                tools=tools,
                hooks=[memory_hook],
                system_prompt=SYSTEM_PROMPT,
            )
            response = agent(user_input)

        for block in response.message.get("content", []):
            if block.get("text"):
                return block["text"]
        return str(response)

    except Exception as e:
        logger.exception("Agent invocation failed")
        return f"I'm sorry, I ran into an error while helping you: {e}"


# ── CLI entry point (do not modify) ──────────────────────────────────────────
def main():
    """Run one invocation from the command line for local testing."""
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=str)
    args = parser.parse_args()
    response = asyncio.run(invoke(json.loads(args.payload)))
    print(response)


if __name__ == "__main__":
    app.run()
    # Uncomment the line below and comment app.run() for local CLI testing:
    # main()
