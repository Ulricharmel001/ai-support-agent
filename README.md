# Customer Support AI Agent

An AI customer support agent for a fictional Amazon store, built with Amazon Bedrock AgentCore, Strands Agents, and MCP. It runs as a Bedrock AgentCore Runtime and is invoked with a single HTTP-style JSON payload.

## 1. What it does

- **Order tracking** — status, carrier, tracking number, delivery estimate (Gateway → Lambda).
- **Returns and refunds** — initiate refunds, check status, generate return labels (Gateway → Lambda).
- **Product and policy Q&A** — product details, return policies, loyalty tiers (Bedrock Knowledge Base / RAG).
- **Loyalty discounts** — exact points + tier arithmetic in AgentCore Code Interpreter.
- **Long-term memory** — customer facts and preferences across sessions (AgentCore Memory).
- **Live web access** — reads live page titles through a remote AgentCore Browser session.

## 2. How the system works (request lifecycle)

1. `agentcore invoke` sends `{"prompt", "customer_id", "session_id"}` to the runtime entrypoint `invoke()` in `main.py`.
2. `invoke()` extracts the values, defaults `session_id` to a UUID, and creates a `MemoryHook` for that actor/session.
3. The hook is registered with `MessageAddedEvent` and `AfterInvocationEvent`.
4. On `MessageAddedEvent`, `retrieve_customer_context()` queries both memory namespaces and prepends `"Customer Context:\n..."` to the user message.
5. `invoke()` builds the tools list: three local `@tool` functions plus every MCP tool returned by `mcp_client.list_tools_sync()`.
6. `Agent` receives the enriched message, `SYSTEM_PROMPT`, model, tools, and hooks. Nova 2 Lite decides which tool to call.
7. Strands executes the selected tool, appends the result to the conversation, and the model produces the final answer.
8. On `AfterInvocationEvent`, `save_support_interaction()` stores the last user + assistant messages as `USER` and `ASSISTANT` events in AgentCore Memory.
9. `invoke()` returns the first text block of the agent response.

## 3. Architecture

| Component | Purpose |
|---|---|
| Strands Agents | Agent loop, tool dispatch, hooks, model integration |
| Amazon Nova 2 Lite (`global.amazon.nova-2-lite-v1:0`) | Reasoning and response generation |
| Bedrock AgentCore Runtime | Hosts the agent (`CustomerSupportAgent-sYElPD2X4q`) |
| AgentCore Gateway (MCP, `NONE` authorizer) | Exposes six Lambda/API tools over MCP |
| Lambda `order-tracker` / `refund-processor` | Backend order, customer, and refund logic |
| API Gateway REST API `2pkyij0gmi` | HTTP frontend for `order-tracker` |
| Bedrock Knowledge Base `O3G5Q7BGUN` | Titan Embeddings v2 + OpenSearch Serverless RAG |
| AgentCore Memory `CustomerSupportMemory-5Jds0j6vL5` | Semantic facts + user preferences |
| AgentCore Code Interpreter | Isolated Python sandbox for discount math |
| AgentCore Browser (remote CDP) | Live web navigation without local Playwright |

## 4. Tools and what each one does

### Local tools (defined in `main.py`)

| Tool | Signature | What it does | When the model uses it |
|---|---|---|---|
| `search_knowledge_base` | `(query: str) -> str` | Calls `bedrock-agent-runtime.retrieve` on KB `O3G5Q7BGUN`; joins chunks with `\n---\n` | Product specs, return policies, warranty, loyalty-tier questions |
| `calculate_loyalty_discount` | `(loyalty_points: int, tier: str, order_total: float, product_category: str = "standard") -> str` | Generates Python for point redemption (500-point steps, max 50%), tier discount (Silver 0%, Gold 10%, Platinum 15%), points earned, and remainder; executes it in `code_session`; falls back to tier-only math on failure | Any discount/points calculation request |
| `web_browser` | `(prompt: str) -> str` | Starts a remote AgentCore Browser session, attaches to the page target over CDP, overrides the user agent, navigates to the URL found in the prompt (default Amazon), polls `document.readyState`, reads `document.title`, then stops the session | Requests for live/current external web information |

### Gateway tools (discovered automatically via MCP)

| Tool name | Backend | Purpose |
|---|---|---|
| `order-tracker___get_order` | Lambda `order-tracker` | Look up one order by `order_id` |
| `order-tracker___get_customer_orders` | Lambda `order-tracker` | List all orders for a `customer_id` |
| `order-tracker___get_customer` | Lambda `order-tracker` | Look up a customer profile |
| `refund-processor___initiate_refund` | Lambda `refund-processor` | Create an approved refund |
| `refund-processor___check_refund_status` | Lambda `refund-processor` | Check a refund ID |
| `refund-processor___get_return_label` | Lambda `refund-processor` | Generate a prepaid return label |

### How a tool is called

Inside the agent, tools are registered here (`main.py`, `invoke()`):

```python
tools = [search_knowledge_base, calculate_loyalty_discount, web_browser]
with MCPClient(lambda: streamable_http_client(GATEWAY_URL)) as mcp_client:
    tools.extend(mcp_client.list_tools_sync())
agent = Agent(model=model, tools=tools, hooks=[memory_hook], system_prompt=SYSTEM_PROMPT)
```

Strands sends tool schemas to Nova 2 Lite; the model returns a tool call; Strands invokes the matching function. You do not call tools manually in normal use.

Direct MCP call for debugging (no authorizer):

```bash
curl -s -X POST \
  "https://customersupportgateway-yexbxqgy7e.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"order-tracker___get_order","arguments":{"order_id":"ORD-001"}}}'
```

## 5. Functions in `main.py`

| Function | Role |
|---|---|
| `get_namespaces(mem_client, memory_id)` | Reads memory strategies and maps `SEMANTIC` / `USER_PREFERENCE` to `cs_agent/{actorId}/facts` and `cs_agent/{actorId}/preferences` |
| `MemoryHook.__init__(actor, session, client, memory_id)` | Stores per-request identity plus the resolved namespaces |
| `MemoryHook._text_from_content(content)` | Extracts plain text from Strands content blocks |
| `MemoryHook._has_tool_block(content)` | Detects tool-result blocks so they are not saved as user text |
| `MemoryHook.retrieve_customer_context(event)` | Retrieves up to 5 memories per namespace and injects them as `"[TYPE] text"` lines |
| `MemoryHook.save_support_interaction(event)` | Walks messages backwards for the last user/assistant texts and calls `create_event` |
| `MemoryHook.register_hooks(registry)` | Registers the two callbacks listed above |
| `search_knowledge_base(query)` | RAG retrieval wrapper |
| `calculate_loyalty_discount(...)` | Code Interpreter discount calculator with fallback |
| `web_browser(prompt)` | Remote browser CDP client (see §4) |
| `invoke(payload, context=None)` | AgentCore entrypoint; full lifecycle in §2; catches exceptions and returns a friendly error string |
| `main()` | Local CLI helper for one invocation (does not modify deployed behavior) |

`setup_permissions.py` reads `.bedrock_agentcore.yaml`, finds the runtime role, and applies only the `CustomerSupportIntegrations` inline policy (KB retrieve, memory operations, browser operations).

## 6. Errors encountered and how they were fixed

| Symptom / error | Cause | Resolution |
|---|---|---|
| `Direct Code Deploy deployment unavailable (uv not found)` | `uv` not on `PATH` for the toolkit | Add `~/.local/share/uvtool/bin` to `PATH` before `agentcore deploy` |
| `uv pip install -e .` setuptools auto-discovery failure | Extra top-level dirs (`lambda/`, `terraform/`) | Install dependencies only with `uv sync --no-install-project` |
| `ImportError: browser was removed in v0.9.0` | `strands-agents-tools` 0.9 removed `AgentCoreBrowser` | Pin `>=0.2.21,<0.9.0` |
| `/var/task/playwright/driver/node: ... libatomic.so.1: cannot open` on deployed runtime | Runtime is `linux/arm64`; local Playwright driver cannot start | Replace with `web_browser`, using `BrowserClient` + raw CDP over the automation WebSocket |
| Amazon title `Sorry! Something went wrong!` | Bot detection | `Network.setUserAgentOverride` before navigation |
| Target name with `_` failed regex `([0-9a-zA-Z][-]?){1,100}` | Gateway target names reject underscores | Use `refund-processor` |
| `Credential provider configurations is not defined` | Gateway target needed IAM credentials | Add `credentialProviderType: GATEWAY_IAM_ROLE` |
| `Failed to parse OpenAPI specification: ... responses is missing` | API Gateway methods lacked responses | Add 200 `put-method-response` to each GET, redeploy API, then `synchronize-gateway-targets` |
| OpenSearch Serverless policy validation errors | Network/access policies need a top-level JSON array; key is `Principal` (singular) | Corrected policy documents |
| OpenSearch 403 on index creation | Missing signed header | Add `x-amz-content-sha256` to SigV4 request |
| KB retrieval returned `[]` | Index eventual consistency | Re-query after indexing settled |
| Memory recall failed immediately after first turn | Extraction is asynchronous | Wait 1–2 minutes before the recall turn |
| X-Ray observability `ValidationException` on deploy | Account trace destination not configured | Non-blocking; runtime deploys and runs normally |
| `ERROR:asyncio:Task was destroyed but it is pending!` | Shutdown cleanup in local tests | Harmless; does not affect responses |

Errors inside `invoke()` are caught, logged, and returned as `"I'm sorry, I ran into an error while helping you: ..."`. Tool failures are returned as strings so the model can explain them instead of crashing.

## 7. Repository layout

```text
.
├── main.py               # Agent, tools, memory hook, MCP client, entrypoint
├── setup_permissions.py  # Post-deploy IAM policy for KB, Memory, Browser
├── product_catalog.txt   # Knowledge Base source document
├── lambda/
│   ├── order_tracker.py      # Order/customer lookup (API Gateway proxy)
│   ├── refund_processor.py   # Refunds, status, return labels
│   └── lambda_schema         # Gateway tool schema
├── pyproject.toml        # Dependencies (Python >=3.13)
├── README.md             # This guide
├── INSTRUCTIONS.md       # Course instructions and submission checklist
├── SUBMISSION.md         # Captured test outputs, alarm, reflection
├── AGENTS.md             # Repo agent rules
└── .bedrock_agentcore.yaml  # Generated deploy config (git-ignored)
```

## 8. Deployed resources (us-east-1, account 561026940393)

| Resource | Identifier |
|---|---|
| Runtime ARN | `arn:aws:bedrock-agentcore:us-east-1:561026940393:runtime/CustomerSupportAgent-sYElPD2X4q` |
| Gateway ID / URL | `customersupportgateway-yexbxqgy7e` · `https://customersupportgateway-yexbxqgy7e.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp` |
| Gateway targets | `order-tracker` (`S4UZYU71CG`), `refund-processor` (`XOGQS2JBXO`) |
| Knowledge Base | `O3G5Q7BGUN` (data source `KXWZFORYUK`) |
| OpenSearch collection | `csai-kb` (`wqebi8k5jvsm41rdzh66`) |
| S3 (KB source) | `csai-kb-561026940393` |
| Memory | `CustomerSupportMemory-5Jds0j6vL5` |
| API Gateway | `2pkyij0gmi`, stage `prod` |
| Runtime role | `AmazonBedrockAgentCoreSDKRuntime-us-east-1-1687b1c02b` |
| Log group | `/aws/bedrock-agentcore/runtimes/CustomerSupportAgent-sYElPD2X4q-DEFAULT` |

## 9. Local setup

```bash
export PATH="$HOME/.local/share/uvtool/bin:$PATH"
uv venv --python 3.13 .venv
uv sync --no-install-project
source .venv/bin/activate
python -m py_compile main.py
```

Run one invocation locally without editing the entrypoint:

```bash
python - <<'PY'
import asyncio, main
print(asyncio.run(main.invoke({
    "prompt": "Can you track order ORD-001?",
    "customer_id": "CUST-123",
    "session_id": "local-1",
})))
PY
```

## 10. Deploy

`agentcore configure` has already been run with `--deployment-type direct_code_deploy --runtime PYTHON_3_13 --non-interactive`. To redeploy after code changes:

```bash
export AGENTCORE_SUPPRESS_RECOMMENDATION=1
export PATH="$HOME/.local/share/uvtool/bin:$PATH"
agentcore deploy
python setup_permissions.py
```

Use `python setup_permissions.py --dry-run` to inspect the IAM policy before applying it.

## 11. Invoke and verify

```bash
agentcore invoke '{"prompt":"<prompt>","customer_id":"CUST-123","session_id":"<id>"}'
```

| Test | Prompt | Expected |
|---|---|---|
| 1 | `Can you track order ORD-001?` | SHIPPED, UPS, `TRK987654321`, delivery estimate |
| 2 | `I want to return my Kindle Paperwhite (ORD-002). Please initiate a refund.` | Refund ID, APPROVED, 3-5 business days |
| 3 | `What are the benefits of the Platinum loyalty tier?` | Free same-day shipping, 15% discount, priority support |
| 4a | `Hi, I am Jane. I prefer concise responses.` (`session_id: s-A`) | Acknowledged |
| 4b | `Do you remember my name and communication preference?` (`session_id: s-B`) | Recalls Jane + concise responses |
| 5 | `I am a Gold member with 4250 points. Calculate my discount on a $150 standard order.` | 4000 points, 10% tier, $99 final, 349 remaining |
| 6 | `Go to https://www.amazon.com and tell me the page title.` | `Amazon.com. Spend less. Smile more.` |

Test 4 needs 1–2 minutes between turns and the same `customer_id`. Test 2 creates a real refund record.

## 12. Monitoring and submission

```bash
aws logs tail /aws/bedrock-agentcore/runtimes/CustomerSupportAgent-sYElPD2X4q-DEFAULT \
  --since 30m --follow
```

The `CSAIErrorFilter` metric filter and `CSAI-Agent-Errors` alarm track more than 5 `ERROR` entries in 5 minutes. `SUBMISSION.md` holds the captured outputs, alarm details, and the written reflection required by `INSTRUCTIONS.md`.

## 13. References

- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [Strands Agents Documentation](https://strandsagents.com)
- [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
- [uv Package Manager](https://docs.astral.sh/uv/)
