# AGENTS.md

## 1. Project Overview

NodeXR is an XR collaborative design system in which user utterances are converted into graph nodes, image-generation inputs, 2D assets, and 3D assets.

The backend is built with:

* FastAPI
* SQLAlchemy
* PostgreSQL with pgvector
* WebSocket
* MinIO
* OpenAI and Gemini APIs
* Alembic

The graph domain contains nodes and edges used by both REST APIs and WebSocket events.

A graph mutation can affect:

1. nodes
2. edges
3. descendant nodes
4. graph snapshots
5. image-generation inputs
6. WebSocket events

Do not treat graph operations as isolated CRUD operations.

---

## 2. Current Application Structure

The main backend source code is under `app`.

```text
app
├── ai
│   └── prompts
│       └── keyword_prompt.py
├── alembic
│   ├── env.py
│   ├── script.py.mako
│   └── versions
├── alembic.ini
├── api
│   ├── feature.py
│   ├── generation.py
│   ├── history.py
│   ├── room.py
│   ├── utterance.py
│   └── ws_room_event.py
├── converter
│   └── graph_converter.py
├── core
│   ├── config.py
│   ├── logger.py
│   ├── minio.py
│   ├── performance.py
│   ├── response
│   │   ├── code.py
│   │   ├── exception_handler.py
│   │   ├── exceptions.py
│   │   ├── response.py
│   │   ├── ws_exception_handler.py
│   │   ├── ws_exceptions.py
│   │   └── ws_response.py
│   ├── security.py
│   ├── startup.py
│   ├── validators.py
│   └── ws_utils.py
├── db
│   ├── base.py
│   ├── init_db.py
│   └── session.py
├── main.py
├── model
│   ├── __init__.py
│   ├── agent.py
│   ├── asset.py
│   ├── enum.py
│   ├── feature.py
│   ├── graph.py
│   ├── memory.py
│   ├── reference.py
│   └── room.py
├── repository
│   ├── asset_repository.py
│   ├── feature_repository.py
│   ├── graph_repository.py
│   ├── room_repository.py
│   └── utterance_repository.py
├── schema
│   ├── feature
│   │   ├── request.py
│   │   └── response.py
│   ├── generation
│   │   ├── generation_result.py
│   │   ├── node_keyword_response.py
│   │   ├── request.py
│   │   └── ws_event_generation_payload.py
│   ├── graph
│   │   ├── response.py
│   │   ├── ws_event_edge_payload.py
│   │   └── ws_event_node_payload.py
│   ├── guide
│   ├── history
│   │   ├── request.py
│   │   └── response.py
│   ├── room
│   │   ├── request.py
│   │   └── response.py
│   ├── utterance
│   │   ├── request.py
│   │   └── ws_event_utterance_payload.py
│   └── websocket
│       └── ws_event.py
└── service
    ├── agent
    ├── feature
    │   └── feature_service.py
    ├── generation
    │   ├── feature_prompt_context_builder.py
    │   ├── feature_prompt_generation_service.py
    │   ├── gemini_image_client.py
    │   ├── image_2d_feature_generation_service.py
    │   ├── image_2d_generation_service.py
    │   ├── minio_asset_storage.py
    │   ├── model_3d_generation_service.py
    │   ├── openai_prompt_client.py
    │   ├── prompt_context_builder.py
    │   └── prompt_generation_service.py
    ├── graph
    │   ├── graph_build_service.py
    │   └── graph_interaction_service.py
    ├── history
    │   └── history_service.py
    ├── room
    │   └── room_service.py
    ├── utterance
    │   ├── auto_utterance_service.py
    │   ├── button_utterance_service.py
    │   ├── embedding_service.py
    │   ├── keyword_service.py
    │   └── text_preprocess_service.py
    └── websocket
        └── connection_manager.py
```

Preserve this structure unless a requested feature clearly requires a new file.

Do not introduce a completely new architectural layer without explaining why the existing structure cannot support the feature.

---

## 3. Required Inspection Before Editing

Before modifying code, inspect the relevant existing implementation.

For graph-related work, inspect at minimum:

* `app/model/graph.py`
* `app/model/enum.py`
* `app/repository/graph_repository.py`
* `app/service/graph/graph_build_service.py`
* `app/service/graph/graph_interaction_service.py`
* `app/api/ws_room_event.py`
* `app/schema/graph/response.py`
* `app/schema/graph/ws_event_node_payload.py`
* `app/schema/graph/ws_event_edge_payload.py`
* `app/schema/websocket/ws_event.py`
* `app/converter/graph_converter.py`

For room validation or authorization, inspect:

* `app/model/room.py`
* `app/repository/room_repository.py`
* `app/service/room/room_service.py`
* `app/api/room.py`
* `app/core/security.py`
* `app/core/validators.py`

For API response and error handling, inspect:

* `app/core/response/code.py`
* `app/core/response/response.py`
* `app/core/response/exceptions.py`
* `app/core/response/exception_handler.py`
* `app/core/response/ws_exceptions.py`
* `app/core/response/ws_exception_handler.py`
* `app/core/response/ws_response.py`

For database and transaction conventions, inspect:

* `app/db/session.py`
* `app/db/base.py`
* existing service and repository methods that call `flush`, `commit`, `refresh`, or `rollback`

Do not assume class names, method names, schemas, enum values, or database columns before inspecting the actual code.

---

## 4. Architecture Responsibilities

Follow the existing separation between API, service, repository, schema, model, and converter code.

### `app/api`

API modules are responsible for:

* declaring routes
* receiving HTTP or WebSocket requests
* parsing request schemas
* injecting dependencies
* invoking services
* returning project-standard responses

Do not place SQLAlchemy queries or graph mutation business logic directly in API modules.

REST graph APIs should be added to an existing appropriate API module or a narrowly scoped new module under `app/api`.

Do not put REST CRUD logic inside `ws_room_event.py`.

### `app/service`

Service modules are responsible for:

* business validation
* transaction orchestration
* coordinating multiple repository operations
* graph mutation workflows
* graph snapshot rebuilding
* coordinating WebSocket event publication
* coordinating external clients when required

Graph mutation logic should primarily be implemented or reused under:

```text
app/service/graph
```

Before creating a new graph service, determine whether the behavior belongs in:

* `graph_build_service.py`
* `graph_interaction_service.py`

If neither file has an appropriate responsibility, create a narrowly scoped service under `app/service/graph`.

Do not create duplicate REST-only and WebSocket-only implementations of the same graph mutation.

### `app/repository`

Repository modules are responsible for:

* SQLAlchemy queries
* entity lookup
* persistence operations
* active and deleted-state filtering
* node and edge lookup
* descendant lookup

Graph persistence belongs in:

```text
app/repository/graph_repository.py
```

Reuse existing repository methods where possible.

Do not create a separate repository for Part Nodes unless Part Nodes use a truly separate persistence model.

Do not construct HTTP responses or WebSocket messages in repository methods.

### `app/schema`

Pydantic request and response schemas belong under `app/schema`.

Graph-related REST schemas should normally be added under:

```text
app/schema/graph
```

Keep these concerns separate:

* REST request schemas
* REST response schemas
* WebSocket event payload schemas

Do not reuse a WebSocket payload schema as a REST request schema merely because the fields are similar.

### `app/model`

SQLAlchemy models and domain enums belong under:

```text
app/model
```

Graph entities belong in or should reuse:

* `app/model/graph.py`
* `app/model/enum.py`

Do not create a new `part_nodes` table when Part Nodes are represented by the existing graph node model and node type enum.

### `app/converter`

Entity-to-schema and graph conversion logic should reuse or extend:

```text
app/converter/graph_converter.py
```

Do not duplicate substantial conversion logic inside routers or services.

---

## 5. Graph Domain Rules

The graph is the source of truth for nodes and edges.

Part Nodes, Property Nodes, and root-level nodes must use the existing graph persistence model and enum definitions.

### Node rules

* Reuse the existing Node ORM model.
* Reuse the existing node type enum.
* A Part Node must use the existing `PART` type or its actual equivalent in `app/model/enum.py`.
* Do not create a separate Part Node ORM model unless one already exists.
* Validate that a node belongs to the requested room.
* Normal read APIs must not return soft-deleted nodes.
* Use UUID identifiers according to current project conventions.
* Use timezone-aware UTC timestamps if timestamps are created in application code.
* Do not allow clients to arbitrarily change immutable fields such as node ID, room ID, or node type.
* PATCH operations must modify only fields explicitly supplied by the request.

### Edge rules

* Reuse the existing Edge ORM model.
* Preserve the parent-child relationship requested by the client.
* Validate that both endpoints belong to the same room.
* Validate that both endpoints are active.
* Preserve the intended edge label semantics.
* Do not repurpose the edge label to store `used_in_generation`.
* Do not create duplicate edges unless the existing domain explicitly permits them.

### Parent rules

Before attaching a Part Node to a parent node, validate:

* the room exists and is active
* the parent node exists and is active
* the parent node belongs to the room
* the parent node type is allowed to own the requested child type
* the relationship does not violate existing graph constraints

Do not infer valid parent types without inspecting the current graph logic.

### Deletion rules

* Use soft deletion.
* Do not hard-delete graph nodes or edges unless explicitly requested.
* Reuse the existing descendant-deletion behavior.
* Reuse the existing connected-edge deletion behavior.
* A deleted parent must not leave active descendant nodes or active connected edges when current project policy requires cascade soft deletion.
* Repeated deletion requests must follow the existing idempotency or error convention.
* Normal retrieval methods must exclude deleted entities.

---

## 6. Graph Snapshot Rules

After a successful graph mutation, determine whether the current architecture requires rebuilding or persisting a graph snapshot.

Inspect and reuse:

```text
app/service/graph/graph_build_service.py
```

Do not implement another independent snapshot builder.

The graph snapshot must be built from the graph state stored in the database.

When handling Part Node and Property Node relationships:

* preserve the current `used_in_generation` calculation
* ensure that Property Node generation state is reflected in its required parent nodes
* do not modify edge labels to represent generation state
* do not rely on client-side highlighting rules as database state
* preserve the database relationships exactly as requested

Snapshot generation must not silently use stale in-memory node or edge collections after database changes.

Use `flush` before snapshot queries when required by the existing transaction pattern.

---

## 7. REST and WebSocket Integration

The project currently receives graph interaction events through:

```text
app/api/ws_room_event.py
```

WebSocket connection management is implemented in:

```text
app/service/websocket/connection_manager.py
```

WebSocket event schemas are under:

```text
app/schema/websocket
app/schema/graph
app/schema/generation
app/schema/utterance
```

REST and WebSocket entry points must not contain separate implementations of the same graph mutation.

The preferred flow is:

```text
REST API ────────────────┐
                         ├── Graph interaction service
WebSocket event handler ─┘
                                  │
                                  ├── Graph repository
                                  ├── Graph snapshot builder
                                  └── WebSocket event publication
```

When implementing REST-based graph CRUD:

* reuse graph mutation services used by WebSocket handlers when possible
* extract shared service methods when substantial logic currently exists directly inside `ws_room_event.py`
* do not copy and paste WebSocket mutation logic into a REST router
* do not make a REST service call the WebSocket router
* do not make a WebSocket handler call an HTTP endpoint
* both entry points should call a shared service layer

Do not add a new WebSocket event type unless explicitly requested.

When an existing WebSocket event type already represents a REST mutation, reuse its existing schema and publication path only where semantically appropriate.

REST request schemas and WebSocket event schemas must remain distinct.

---

## 8. Part Node CRUD Rules

When implementing Part Node CRUD APIs, follow these requirements.

### Create

The create flow should normally perform:

1. validate the room
2. validate the requesting user or existing authorization context
3. validate the parent node
4. validate room ownership of the parent node
5. validate the parent-child type relationship
6. create a Node using the existing PART node type
7. create the requested parent-child Edge
8. flush graph changes
9. rebuild or persist the graph snapshot if required
10. publish the appropriate existing WebSocket event if required
11. commit according to the existing transaction convention
12. return the project-standard API response

Node creation and required Edge creation must be atomic.

A request must not succeed with a Node created but its required Edge missing.

### Read

The read flow must:

* retrieve only active nodes
* validate the room
* validate that the node belongs to the room
* validate that the node is a Part Node
* reject or hide soft-deleted nodes according to current API conventions
* return a response schema under `app/schema/graph`

### Update

Use PATCH semantics unless the existing API conventions require another method.

The update flow must:

* validate the room
* retrieve an active Part Node
* validate room ownership
* update only explicitly supplied mutable fields
* reject node type changes
* reject room ID changes
* reject node ID changes
* rebuild the graph snapshot if graph-visible data changed
* publish the appropriate existing WebSocket event if required
* commit atomically

Do not overwrite omitted fields with `None`.

### Delete

The delete flow must:

* validate the room
* retrieve the active Part Node
* validate room ownership
* apply the existing soft-delete policy
* process descendant nodes according to the current graph policy
* soft-delete connected edges according to the current graph policy
* rebuild the graph snapshot
* publish the appropriate existing WebSocket event if required
* commit atomically

Do not implement deletion by directly calling `db.delete`.

---

## 9. Transaction Rules

Graph mutations must be atomic.

A failed operation must not leave states such as:

* Part Node created without its parent Edge
* active Edge connected to a deleted node
* parent deleted while required descendants remain active
* graph data committed while snapshot rebuilding failed
* REST mutation committed while required event preparation failed
* only part of a descendant tree deleted

Follow the transaction convention already used by the project.

Before adding transaction code, inspect whether commits are currently owned by:

* API modules
* services
* repository methods

Prefer service-level transaction orchestration for multi-step graph mutations.

Avoid adding arbitrary `commit()` calls inside repository methods.

Use these operations intentionally:

* `flush()` when following queries must observe pending changes
* `refresh()` when database-generated values are needed
* `commit()` at the established transaction boundary
* `rollback()` through the existing exception-handling convention

Do not catch broad exceptions merely to log and continue.

---

## 10. API Response and Error Rules

Reuse the project response system under:

```text
app/core/response
```

Inspect and follow:

* `code.py`
* `response.py`
* `exceptions.py`
* `exception_handler.py`

For WebSocket errors, inspect and follow:

* `ws_exceptions.py`
* `ws_exception_handler.py`
* `ws_response.py`

Requirements:

* reuse `ResponseCode` or the actual equivalent
* reuse the existing success response wrapper
* use project exception classes
* do not return arbitrary dictionaries when an existing response format is available
* do not expose raw database exceptions
* do not mix HTTP exceptions and WebSocket exceptions
* preserve the current error-code and HTTP-status mapping
* preserve existing logging conventions

Do not invent new response formats for Part Node APIs.

If a new response code is required, add it consistently to the existing response system rather than embedding strings in the router.

---

## 11. Logging and Performance Rules

Reuse:

```text
app/core/logger.py
app/core/performance.py
```

Do not replace the logging system with `print`.

Log enough context to diagnose failures, including applicable identifiers such as:

* room ID
* user ID
* node ID
* parent node ID
* event type

Do not log:

* API keys
* access tokens
* secrets
* complete sensitive request contents
* unnecessary embedding vectors

Preserve existing performance instrumentation when modifying instrumented API or service flows.

---

## 12. Database Migration Rules

Alembic files are under:

```text
app/alembic
```

Do not create an Alembic migration for a Part Node CRUD feature when the existing Node and Edge tables already support the feature.

Create a migration only when a real schema change is required.

Before generating a migration:

1. inspect the existing graph model
2. inspect existing migrations
3. verify that the requested behavior cannot be represented by current columns
4. explain the required schema change

Do not modify existing migration history unnecessarily.

---

## 13. External AI and Generation Rules

Graph CRUD must not trigger OpenAI, Gemini, MinIO, 2D generation, or 3D generation unless explicitly required by the feature.

Relevant modules include:

```text
app/service/generation
app/ai/prompts
app/core/minio.py
```

Do not introduce an external API call into basic Part Node CRUD without a clear existing requirement.

Preserve the separation between:

* graph persistence
* prompt context construction
* prompt generation
* image generation
* asset storage
* 3D model generation

---

## 14. Scope Control

For every task:

* make the smallest coherent change
* preserve current directory structure
* preserve current import paths
* preserve current naming conventions
* preserve current API contracts unless explicitly changing them
* do not reorganize unrelated files
* do not rename public classes or functions unnecessarily
* do not rewrite working modules merely for style
* do not add an unnecessary framework or dependency
* do not apply broad formatting changes
* do not modify unrelated generation, utterance, room, history, or feature flows
* do not modify Unity or XR client code during a backend-only task

A new file is acceptable when it has a clear responsibility that does not fit an existing file.

Before adding a new abstraction, explain:

* what duplication or coupling it removes
* which existing callers will use it
* why an existing service cannot reasonably own the behavior

---

## 15. Testing Rules

Before writing tests, discover the existing test structure and framework.

Do not assume a test directory or fixture name that has not been inspected.

Inspect available configuration such as:

* `pyproject.toml`
* `pytest.ini`
* `requirements.txt`
* `requirements-dev.txt`
* `Makefile`
* `README.md`
* Docker configuration
* GitHub Actions workflows
* existing test files

For Part Node CRUD, cover at minimum:

1. Part Node creation succeeds
2. required parent Edge is created
3. Node and Edge belong to the requested room
4. nonexistent room is rejected
5. nonexistent parent node is rejected
6. soft-deleted parent node is rejected
7. parent node from another room is rejected
8. invalid parent type is rejected when constrained by the domain
9. Part Node retrieval succeeds
10. a non-Part Node cannot be retrieved through a Part Node-specific API
11. soft-deleted Part Nodes are not returned
12. PATCH updates only supplied fields
13. immutable fields cannot be updated
14. Part Node deletion performs soft deletion
15. connected edges are soft-deleted
16. required descendant nodes are soft-deleted
17. graph snapshot is updated after creation
18. graph snapshot is updated after modification
19. graph snapshot is updated after deletion
20. intermediate failure rolls back the complete graph mutation

Where relevant, also verify that the expected existing WebSocket event is published exactly once.

Do not use real OpenAI, Gemini, MinIO, or external network calls in CRUD unit tests.

---

## 16. Verification Commands

Do not invent commands without checking the repository configuration.

Discover the correct commands for:

* application startup
* unit tests
* integration tests
* linting
* formatting
* type checking
* Alembic validation

Run the most relevant available checks after modification.

If a command cannot be run, report:

* the exact command attempted
* the failure reason
* whether the failure is caused by code, dependencies, infrastructure, or missing configuration

Do not report a test as passed unless it was actually executed successfully.

---

## 17. Required Workflow for Codex

For nontrivial features, use this order.

### Step 1: Inspect

Read the relevant model, enum, repository, service, schema, API, converter, and response files.

### Step 2: Report the current flow

Before changing code, identify:

* current request entry point
* service call chain
* repository methods
* transaction boundary
* snapshot update point
* WebSocket publication point
* reusable code
* likely duplicated logic

### Step 3: Propose a narrow implementation plan

List:

* files to modify
* files to create
* existing methods to reuse
* any logic to extract
* transaction strategy
* tests to add

### Step 4: Implement

Make the smallest coherent implementation that satisfies the requirements.

### Step 5: Verify

Run relevant tests and static checks.

### Step 6: Report

Provide a concise completion report.

---

## 18. Completion Report Format

After completing a task, report the following.

### Files changed

For each file:

* path
* purpose of the change

### Implementation flow

Describe the actual call flow, for example:

```text
HTTP request
→ API router
→ graph interaction service
→ room and graph validation
→ graph repository
→ snapshot builder
→ WebSocket event publication
→ transaction commit
→ HTTP response
```

Use actual class and method names from the implementation.

### API contracts

For each endpoint, provide:

* HTTP method
* path
* request body
* response body
* major error cases

### Verification

Report:

* commands executed
* tests passed
* tests failed
* checks not executed and why

### Remaining assumptions

Explicitly identify any domain rules that could not be confirmed from the repository.

---

## 19. Prohibited Changes

Unless explicitly requested, do not:

* create a `part_nodes` table
* create a Part Node ORM model separate from the graph Node model
* hard-delete nodes or edges
* place SQLAlchemy queries directly in API modules
* duplicate graph mutation logic between REST and WebSocket
* use edge labels as `used_in_generation`
* replace the existing response system
* invent new WebSocket event types
* add external AI calls to CRUD operations
* alter unrelated import paths
* move existing modules to new directories
* perform repository-wide formatting
* change public API contracts
* claim tests were run when they were not