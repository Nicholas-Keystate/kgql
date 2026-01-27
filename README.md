# KGQL - KERI Graph Query Language

Declarative query language for KERI credential graphs. Thin wrappers over keripy — no reimplementation.

## Principles

1. **Resolution IS Verification** — If a SAID resolves, cryptographic integrity is guaranteed
2. **Don't Duplicate, Integrate** — Thin wrappers over keripy, not a parallel stack

## Install

```bash
pip install kgql
```

## Usage

```python
from kgql import KGQL

# Initialize with any keripy Habery/Regery/Verifier
kgql = KGQL(hby=hby, rgy=rgy, verifier=verifier)

# Resolve a credential by SAID
result = kgql.resolve("ESAID...")

# Query by issuer
creds = kgql.by_issuer("EAID...")

# Execute a KGQL query string
result = kgql.query(
    "MATCH (c:Credential) WHERE c.issuer = $aid",
    variables={"aid": "EAID..."}
)

# Verify a credential chain
result = kgql.verify("ESAID...")

# Traverse edges
result = kgql.traverse("ESAID...", "delegator")
```

## Query Language

### RESOLVE

Resolve a single credential by SAID:

```
RESOLVE $said
```

### MATCH

Query credentials by attributes:

```
MATCH (c:Credential) WHERE c.issuer = $aid
MATCH (c:Credential) WHERE c.schema = $schema_said
MATCH (c:Credential) WHERE c.subject = $aid
```

### VERIFY

Verify a credential chain:

```
VERIFY $said
```

### TRAVERSE

Follow credential edges:

```
TRAVERSE FROM $said FOLLOW edge
TRAVERSE FROM $said FOLLOW delegator
```

## Components

### Core API (`kgql.api`)

- `query(kgql_string, variables)` — Execute any KGQL query
- `resolve(said)` — Resolve single credential
- `by_issuer(aid)` / `by_subject(aid)` — Query by participant
- `verify(said)` — Verify credential chain
- `traverse(from_said, edge_type)` — Follow edges
- `verify_end_to_end_chain(said)` — Full delegation chain verification

### Parser (`kgql.parser`)

Parses KGQL query strings into AST:

```python
from kgql.parser import KGQLParser

parser = KGQLParser()
ast = parser.parse("RESOLVE $said", variables={"said": "ESAID..."})
```

### Translator (`kgql.translator`)

Maps AST operations to keripy method calls:

```python
from kgql.translator import QueryPlanner

planner = QueryPlanner()
plan = planner.plan(ast)
```

### Wrappers (`kgql.wrappers`)

Protocol-agnostic edge resolution:

- `EdgeResolver` — Abstract interface for any protocol
- `ACDCEdgeResolver` — KERI/ACDC credential edges (reads the `"e"` field)
- `PatternSpaceEdgeResolver` — Concept/pattern ontology graph edges
- `EdgeResolverRegistry` — Multi-protocol resolver registry
- `RegerWrapper` — Thin wrapper over keripy Reger
- `VerifierWrapper` — Thin wrapper over keripy Verifier

```python
from kgql.wrappers import create_default_registry

# Registry with ACDC + PatternSpace resolvers
registry = create_default_registry()

# Resolve an edge from a credential
edge = registry.resolve_edge(credential, "iss")
print(edge.target_said)

# Or from a concept/pattern node
edge = registry.resolve_edge(
    {"slug": "keri-runtime-singleton"},
    "references",
    protocol_hint="pattern-space",
)
```

Implementing a custom resolver:

```python
from kgql.wrappers import EdgeResolver, EdgeRef

class MyProtocolResolver(EdgeResolver):
    @property
    def protocol(self) -> str:
        return "my-protocol"

    def get_edge(self, content, edge_name):
        # Extract edge from your protocol's format
        ...

    def list_edges(self, content):
        # List available edges
        ...

registry.register(MyProtocolResolver())
```

### Indexer (`kgql.indexer`)

Schema-driven credential indexing (inspired by Phil Feairheller's KERIA Seeker pattern):

```python
from kgql.indexer import create_query_engine

engine = create_query_engine({"ESchema...": person_schema})

results = engine.query(
    credentials,
    {
        "personLegalName": "Alice",       # Implicit $eq
        "LEI": {"$begins": "US"},         # Prefix match
        "age": {"$gte": 30},              # Comparison
        "-s": "ESchema...",               # Schema filter
    },
)
```

Operators: `$eq`, `$begins`, `$lt`, `$gt`, `$lte`, `$gte`, `$contains`

### MCP Server (`kgql.mcp`)

Model Context Protocol server for LLM tool integration:

```bash
python -m kgql.mcp
```

Configure in any MCP-compatible client:

```json
{
  "mcpServers": {
    "kgql": {
      "command": "python3",
      "args": ["-m", "kgql.mcp"]
    }
  }
}
```

Tools: `kgql_resolve`, `kgql_query`, `kgql_verify_chain`, `kgql_by_schema`, `kgql_traverse`

## Architecture

```
 KGQL Query String
       │
       ▼
   KGQLParser ──→ AST
       │
       ▼
  QueryPlanner ──→ ExecutionPlan
       │
       ▼
     KGQL ──→ Execute via wrappers
       │
       ▼
  EdgeResolverRegistry
   ├── ACDCEdgeResolver (KERI/ACDC)
   ├── PatternSpaceEdgeResolver (ontology)
   └── [your resolver]
       │
       ▼
    keripy
  Habery / Regery / Verifier
```

## Dependencies

- `keri>=1.2.0` — Core KERI implementation
- `hio>=0.6.14` — HIO async framework (Deck integration)
- `lark>=1.1.0` — Parser generator for KGQL grammar

## License

Apache 2.0
