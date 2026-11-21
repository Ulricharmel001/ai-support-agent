# Customer Support AI Agent

A production-style customer-support assistant built with Amazon Bedrock AgentCore, Strands Agents, and MCP. It combines backend order APIs, product documents, deterministic calculations, long-term memory, and live browser access behind one conversational interface.

The deployed agent accepts a prompt, customer ID, and session ID. It chooses the right tool, calls it, and returns a clear support answer.

---

## 1. Project goal

The goal is to demonstrate a complete agent workflow, not a simple chatbot. Customer support requires several different systems:

- structured order and refund data,
- product documents and policies,
- reliable reward calculations,
- customer history and preferences,
- live web information.

This project puts all of them behind one runtime. The model does not invent backend data. It uses tools and explains the returned result.

---

## 2. What the agent can do

### Order support

Finds orders, lists customer orders, and reads customer profiles through the AgentCore Gateway and the `order-tracker` Lambda.

### Refund support

Creates refunds, checks refund status, and generates return labels through the `refund-processor` Lambda.

### Product and policy answers

Searches the Bedrock Knowledge Base for product details, return windows, warranties, and loyalty rules. The source is `product_catalog.txt`.

### Loyalty discount calculation

Uses Code Interpreter to calculate points redeemed, tier discount, final total, savings, earned points, and remaining points.

### Long-term memory

Saves customer facts and preferences with AgentCore Memory, then loads them into later prompts.

### Live browser access

Opens a live page through the remote AgentCore Browser and reads the page title using raw CDP over WebSocket.

---

## 3. How the system works

1. `agentcore invoke` sends `{"prompt", "customer_id", "session_id"}` to `invoke()` in `main.py`.
2. The memory hook loads saved facts and preferences for that customer.
3. The agent loads three local tools and six Gateway MCP tools.
4. Nova 2 Lite chooses the correct tool.
5. Strands Agents executes the tool and returns the result to the model.
6. The model writes the customer-facing answer.
7. The interaction is saved back to AgentCore Memory.

The full flow, commands, actual outputs, and screenshots are in [HOW_IT_WORKS.md](HOW_IT_WORKS.md).

---

## 4. Deployment context

| Setting | Value | Why it matters |
|---|---|---|
| AWS account | Withheld for privacy | This is the billing and security boundary that owns the deployed resources. The active AWS CLI profile must point to this account to test the agent. |
| Region | `us-east-1` | This is where the runtime, Gateway, Lambda functions, Knowledge Base, and Memory were created. Region must match because AWS service resources are regional. |
| Runtime ID | `CustomerSupportAgent-N7wgcz87hH` | This identifies the deployed agent. |
| Model | `global.amazon.nova-2-lite-v1:0` | This is the foundation model used for reasoning and answers. |

Account details are intentionally not printed in this document. Testing requires the AWS credentials configured on the machine, not account numbers inside the README.

---

## 5. System design

| Layer | Service | Why it is used |
|---|---|---|
| Runtime | Bedrock AgentCore Runtime | Hosts the deployed agent |
| Agent loop | Strands Agents | Model loop, tool dispatch, hooks |
| Model | Amazon Nova 2 Lite | Tool choice and final response |
| Tool gateway | Bedrock AgentCore Gateway | Exposes backend Lambda tools as MCP tools |
| Backend data | Lambda + API Gateway | Order, customer, and refund operations |
| Knowledge | Bedrock Knowledge Base | Retrieves product and policy chunks |
| Vector store | OpenSearch Serverless | Stores embeddings for semantic search |
| Object storage | S3 | Holds the product catalog source file |
| Calculations | Code Interpreter | Runs deterministic discount arithmetic |
| Memory | AgentCore Memory | Stores customer facts and preferences |
| Browser | AgentCore Browser + CDP | Reads live web page data |

The design separates responsibilities. Structured data stays in backend APIs, documents stay in RAG, calculations run in code, memory lives in AgentCore Memory, and the model only orchestrates.

---

## 6. Deployed resources

| Resource | Identifier |
|---|---|
| Runtime | `CustomerSupportAgent-N7wgcz87hH` |
| Gateway | `customersupportgateway-q0bnbscqkv` |
| Order target | `PGBOPONMKY` |
| Refund target | `ZUKULDYCNJ` |
| Knowledge Base | `KB9IFNPKDL` |
| Data source | `U4KSWTGQMY` |
| OpenSearch collection | `vt6d1m040prp2a1hutz8` |
| S3 KB source | Private bucket, name withheld |
| Memory | `CustomerSupportMemory-iePu3ICXR7` |
| API Gateway | `oxz6dfft9c`, stage `prod` |
| Lambda functions | `order-tracker`, `refund-processor` |

---

## 7. Repository structure

| File | Purpose |
|---|---|
| `main.py` | Agent definition, tools, memory hooks, MCP client, entrypoint |
| `HOW_IT_WORKS.md` | Detailed workflow and Test 1–6 evidence |
| `setup_permissions.py` | Applies IAM permissions for KB, Memory, and Browser |
| `product_catalog.txt` | Source document for the Knowledge Base |
| `lambda/order_tracker.py` | Order and customer lookup backend |
| `lambda/refund_processor.py` | Refund, status, and return label backend |
| `lambda/lambda_schema` | Tool schema for the refund Gateway target |
| `pyproject.toml` | Python dependencies |
| `submission_evidence/` | Screenshots and terminal outputs |
| `INSTRUCTIONS.md` | Course submission checklist |

---

## 8. Local setup and deployment

Activate the existing environment:

```bash
cd /home/ulrich/Downloads/Chat-support-agentcore/ai-support-agent
source .venv/bin/activate
export PATH="$HOME/.local/share/uvtool/bin:$PATH"
export AGENTCORE_SUPPRESS_RECOMMENDATION=1
```

If `.venv` is missing:

```bash
uv venv --python 3.13 .venv
uv sync --no-install-project
source .venv/bin/activate
```

Redeploy after code changes:

```bash
agentcore deploy
python setup_permissions.py
```

---

## 9. Verification

The deployed agent was tested with six scenarios:

1. order tracking,
2. refund initiation,
3. knowledge base retrieval,
4-1. save customer memory,
4-2. recall customer memory,
5. loyalty discount calculation,
6. live browser title lookup.

Commands, actual outputs, tool paths, and screenshots are in [HOW_IT_WORKS.md](HOW_IT_WORKS.md).

---

## 10. Key implementation decisions

- **Gateway MCP tools:** Backend APIs are exposed through AgentCore Gateway instead of being hard-coded into the agent.
- **Knowledge Base RAG:** Product and policy facts come from indexed documents, not model memory.
- **Code Interpreter:** Loyalty math is executed as code for consistency.
- **Memory hooks:** Customer context is loaded before the model runs and saved after each turn.
- **Remote browser:** Browser work runs in the cloud, avoiding ARM64 Playwright failures.
- **Error handling:** Tool and invocation errors are caught and returned as friendly answers.

---

## 11. References

- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-bases.html)
- [Amazon OpenSearch Serverless](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless.html)
- [Strands Agents Documentation](https://strandsagents.com)
- [Model Context Protocol](https://modelcontextprotocol.io)
- [uv Package Manager](https://docs.astral.sh/uv/)
