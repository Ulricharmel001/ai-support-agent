# AI Support Agent

Customer support agent built with Strands Agents and Amazon Bedrock AgentCore (Runtime, Gateway, Memory, Knowledge Base).

## Structure
- `main.py` - Agent logic (TODOs to complete)
- `setup_permissions.py` - Configure agent execution role permissions
- `product_catalog.txt` - Upload to S3 for Knowledge Base
- `lambda/` - `order_tracker.py`, `refund_processor.py`, `lambda_schema`

## Setup
```bash
uv sync --python 3.13
aws configure
```

## AWS Resources
Create in `us-east-1`:
1. Lambda functions (`order-tracker`, `refund-processor`)
2. API Gateway REST API with routes wired to `order-tracker`
3. AgentCore Gateway (NONE authorizer) with API Gateway + Lambda targets
4. Bedrock Knowledge Base from `product_catalog.txt`
5. AgentCore Memory with SEMANTIC + USER_PREFERENCE strategies
6. AgentCore Runtime via `agentcore deploy`

Update `main.py` with `GATEWAY_URL`, `KB_ID`, `REGION`, `MEMORY_ID`.

## Run
```bash
# local
uv run main.py '{"prompt": "Hello", "customer_id": "CUST-123", "session_id": "s1"}'

# deploy
agentcore deploy

# invoke
agentcore invoke '{"prompt": "Hello", "customer_id": "CUST-123", "session_id": "s1"}'
```
