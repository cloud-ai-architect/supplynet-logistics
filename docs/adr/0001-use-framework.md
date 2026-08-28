# ADR-0001: Use CrewAI + LangGraph as the primary agent framework

## Status: Accepted

## Context

SupplyNet is a multi-agent system. We need:
- Easy multi-agent orchestration
- Tool-calling
- AWS-native integration
- Cost-effective

## Decision

Use **CrewAI + LangGraph** as the primary orchestration framework, with Strands Agents / Bedrock AgentCore for AWS-native integration.

## Consequences

- Best multi-agent patterns in the industry
- AWS-native via Bedrock
- Easy to swap models
- Tool-calling built-in

## References

- [CrewAI + LangGraph docs](https://docs.CrewAI + LangGraph.com/)
- [Strands Agents](https://strandsagents.com/)
