# Customer Support AI Agent

A production-ready AI customer support agent for a fictional Amazon store, built using Amazon Bedrock AgentCore, Strands Agents, and the Model Context Protocol (MCP).

## Overview

This agent handles end-to-end customer inquiries by combining large language models with external tools, retrieval-augmented generation, persistent memory, code execution, and web browsing capabilities.

## Capabilities

- **Order Tracking** – Look up order status, shipping details, and delivery estimates via Lambda functions through AgentCore Gateway
- **Returns & Refunds** – Initiate refunds and generate return labels using Gateway-exposed tools
- **Product & Policy Q&A** – Answer questions about products, return policies, warranties, and loyalty rewards using Bedrock Knowledge Base (RAG)
- **Loyalty Discounts** – Calculate exact discounts using the AgentCore Code Interpreter with tier-based rules and points redemption
- **Persistent Memory** – Remembers customer preferences and facts across sessions using AgentCore Memory (Semantic + User Preference strategies)
- **Live Web Access** – Fetches up-to-date information from the web using the AgentCore Browser tool

## Architecture

| Component | Purpose |
|-----------|---------|
| **Strands Agents** | Agent framework with tool use, hooks, and model integration |
| **Amazon Bedrock (Nova Lite)** | Foundation model for reasoning and responses |
| **Bedrock AgentCore Runtime** | Hosts and serves the agent |
| **AgentCore Gateway (MCP)** | Exposes Lambda functions as tools |
| **Lambda (order-tracker, refund-processor)** | Backend logic for orders and refunds |
| **Bedrock Knowledge Base** | Product catalog and support documentation (RAG) |
| **AgentCore Memory** | Long-term customer context across sessions |
| **AgentCore Code Interpreter** | Secure sandbox for discount calculations |
| **AgentCore Browser** | Live web navigation and data retrieval |

## Project Structure

```text
.
├── main.py              # Agent implementation with all tools, hooks, and entrypoint
├── setup_permissions.py # Post-deployment IAM policy setup for KB, Memory, Browser
├── product_catalog.txt  # Knowledge base source document
├── lambda/
│   ├── order_tracker.py     # Order/customer lookup (API Gateway proxy)
│   ├── refund_processor.py  # Refund and return label logic (direct Lambda)
│   └── lambda_schema       # Tool schema for refund processor
├── pyproject.toml       # Dependencies
├── AGENTS.md            # Agent rules
└── INSTRUCTIONS.md      # Full project guide
```

## Tech Stack

- Python 3.14+
- [Strands Agents](https://strandsagents.com/)
- [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [AWS Lambda](https://aws.amazon.com/lambda/)
- [Amazon API Gateway](https://aws.amazon.com/api-gateway/)
- [Amazon Bedrock Knowledge Bases](https://aws.amazon.com/bedrock/knowledge-bases/)
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)

## Region

All AWS resources are deployed in **us-east-1** (N. Virginia)

## Model

- **Model ID:** `global.amazon.nova-2-lite-v1:0` (Amazon Nova Lite)

## Key Files

| File | Description |
|------|-------------|
| `main.py` | Core agent with tools, memory hook, KB search, code interpreter, browser, and AgentCore entrypoint |
| `setup_permissions.py` | Grants the deployed agent runtime access to KB, Memory, and Browser resources |
| `product_catalog.txt` | Product catalog and support policies used for the Knowledge Base |
| `lambda/order_tracker.py` | Handles order and customer lookups via API Gateway REST proxy |
| `lambda/refund_processor.py` | Handles refunds, refund status checks, and return label generation |
| `lambda/lambda_schema` | JSON schema for Gateway tool registration |

## References

- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [Strands Agents Documentation](https://strandsagents.com)
- [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
- [uv Package Manager](https://docs.astral.sh/uv/)
