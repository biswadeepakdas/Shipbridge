# ShipBridge Transition Timeline: Mocked to Production-Ready

## 1. Introduction

This document outlines a proposed 4-week timeline for transitioning the currently simulated or partially implemented data layer and event-driven components of ShipBridge to a production-ready state, aligning with the original build plan and architectural diagram. The goal is to replace mocked functionalities with robust, scalable, and durable implementations.

## 2. Transition Milestones

The transition will focus on the following key areas, addressing the discrepancies identified in the gap analysis report:

*   **Real-time Context Assembly**: Replacing simulated `pgvector` and `tsvector` with actual PostgreSQL extensions for dense and sparse retrieval, respectively. This includes setting up embedding generation and ingestion pipelines.
*   **Asynchronous Event Ingestion**: Implementing a robust, asynchronous webhook processing pipeline using Redis Streams to ensure high throughput and reliability, adhering to the 200ms ACK guarantee.
*   **Production-Grade Staged Deployment**: Integrating real-time metric collection for canary stages to enable accurate auto-rollback decisions, moving beyond simulated metrics.
*   **Full Temporal Workflow Integration**: Migrating the in-memory deployment engine to a fully durable and scalable Temporal workflow, leveraging its checkpointing and fault-tolerance capabilities.
*   **Distributed Context Caching**: Implementing a Redis-backed distributed cache for context assembly to improve performance and ensure consistency across multiple instances.
*   **Expanded Connector Ecosystem**: Developing and integrating the remaining planned connector adapters to broaden ShipBridge's integration capabilities.
*   **Automated LLM Rule Generation**: Fully implementing the LLM-based rule generation for Composio triggers, including schema fetching, prompt engineering, and administrative review workflows.
*   **Accurate Cost Modeling**: Implementing the detailed cost modeling and token estimation logic, including dynamic pricing and routing optimization.

## 3. 4-Week Transition Roadmap

This roadmap provides a high-level overview of tasks distributed across four weeks. Each week builds upon the previous one, ensuring a systematic progression towards production readiness.

### Week 1: Core Data Layer & Caching Foundation

| Day | Focus Area | Key Tasks | Deliverables |
|---|---|---|---|
| **Day 1-2** | **PostgreSQL `pgvector` Setup** | - Provision PostgreSQL with `pgvector` extension. <br> - Update `app.db` to support `pgvector` types. <br> - Implement `EmbeddingIngester` to chunk documents, generate embeddings, and store in `pgvector`. <br> - Replace simulated `dense_retrieval` in `context.py` with actual `pgvector` queries. | - `pgvector` enabled in dev environment. <br> - Initial document embeddings ingested. <br> - Functional `dense_retrieval` using `pgvector`. |
| **Day 3-4** | **PostgreSQL `tsvector` Setup** | - Configure PostgreSQL for `tsvector` and GIN indexes. <br> - Implement `tsvector` indexing for relevant content. <br> - Replace simulated `sparse_retrieval` in `context.py` with actual `tsvector` queries. | - `tsvector` indexing configured. <br> - Functional `sparse_retrieval` using `tsvector`. |
| **Day 5** | **Redis Context Cache** | - Integrate `redis.asyncio` for context caching. <br> - Replace in-memory `ContextCache` with Redis-backed implementation. <br> - Configure cache TTL and eviction policies. | - Distributed context cache operational with Redis. <br> - Measurable cache hit rate in development. |

### Week 2: Event-Driven Architecture & LLM Rule Generation

| Day | Focus Area | Key Tasks | Deliverables |
|---|---|---|---|
| **Day 6-7** | **Asynchronous Webhook Ingestion (Redis Streams)** | - Implement Redis Streams for webhook ingestion. <br> - Modify `webhooks.py` to write to Redis Streams immediately (200ms ACK). <br> - Develop a dedicated Redis Streams consumer service (e.g., Celery worker) to process events asynchronously. <br> - Implement deduplication logic using Redis SETNX. | - Webhooks ingested asynchronously via Redis Streams. <br> - Deduplication functional. <br> - DLQ for failed events. |
| **Day 8-9** | **LLM Rule Generator Implementation** | - Implement `RuleGeneratorJob` (Celery beat) to drain `UnknownEventQueue`. <br> - Integrate Composio SDK to fetch trigger schemas. <br> - Develop LLM prompt for rule generation (Haiku, structured output). <br> - Implement snapshot testing for generated rules. | - Automated LLM rule generation for unknown triggers. <br> - Draft rules available for admin review. |
| **Day 10** | **Admin Rule Review UI & Promotion** | - Build admin UI for reviewing draft rules. <br> - Implement rule promotion flow (draft → active) with cache invalidation. | - Admin UI for rule review. <br> - Rules can be promoted to active status. |

### Week 3: Production-Ready Staged Deployer & Metrics

| Day | Focus Area | Key Tasks | Deliverables |
|---|---|---|---|
| **Day 11-12** | **Real-time Metric Collection** | - Identify and integrate with actual metric sources (e.g., Prometheus, Grafana, internal logging). <br> - Replace `simulate_stage_metrics` with functions that query real metrics. <br> - Define metrics for task success rate, latency, token cost, error rate. | - Live metric collection for deployment stages. <br> - Metrics dashboard updated with real data. |
| **Day 13-14** | **Full Temporal Workflow Integration** | - Configure Temporal server for production deployment. <br> - Ensure `StagedDeploymentTemporalWorkflow` uses durable Temporal activities for all stages. <br> - Remove reliance on in-memory `DeploymentEngine` for production paths. <br> - Implement robust error handling and retry logic within Temporal workflows. | - Staged deployment fully managed by Temporal. <br> - Durable and fault-tolerant deployment workflows. |
| **Day 15** | **Auto-Rollback Refinement** | - Validate auto-rollback triggers against real metrics. <br> - Implement notification mechanisms (Slack, email) for rollback events. <br> - Ensure rollback activities are robust and revert changes effectively. | - Reliable auto-rollback based on live metrics. <br> - Rollback notifications configured. |

### Week 4: Connector Expansion & Cost Modeling

| Day | Focus Area | Key Tasks | Deliverables |
|---|---|---|---|
| **Day 16-18** | **Connector Adapter Development** | - Prioritize and implement remaining high-value connector adapters (e.g., Google Workspace, Linear, Airtable). <br> - Ensure each adapter includes OAuth/API key authentication, `normalize()` function, and health checks. <br> - Write comprehensive integration tests for new adapters. | - Additional production-ready connector adapters. <br> - Expanded integration capabilities. |
| **Day 19-20** | **Advanced Cost Modeling** | - Implement `CostModeler` service with dynamic pricing tables (Haiku/Sonnet/Opus). <br> - Develop 3-tier routing optimizer based on task classification. <br> - Implement `SemanticCacheEstimator` for hit rate projection. <br> - Integrate cost breakdown charts into the dashboard. | - Accurate cost projections and optimization. <br> - Cost metrics wired into assessment Cost pillar. |

## 4. Conclusion

This 4-week roadmap provides a structured approach to transition ShipBridge's core data layer and event-driven components from their current simulated state to a robust, production-ready architecture. By systematically addressing each identified discrepancy, ShipBridge can achieve the scalability, reliability, and full feature set envisioned in its original build plan and architectural design. Regular testing, monitoring, and iterative deployment will be crucial throughout this transition. 

## 5. References

[1] ShipBridge Build Plan · Pilot-to-Production Platform · 30-Day Roadmap (Provided Document)
[2] ShipBridge Pilot-to-Production Platform — Full System Architecture (Provided Diagram)
[3] Shipbridge GitHub Repository: [https://github.com/biswadeepakdas/Shipbridge/tree/claude/general-session-HAzLT](https://github.com/biswadeepakdas/Shipbridge/tree/claude/general-session-HAzLT)
