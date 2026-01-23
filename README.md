# KGQL - KERI Graph Query Language

A declarative query language for KERI credential graphs.

## Core Principles

1. **"Resolution IS Verification"** - If a SAID resolves, the credential exists and its cryptographic integrity is guaranteed
2. **"Don't Duplicate, Integrate"** - Thin wrappers over keripy, not reimplementation

## Installation

```bash
pip install kgql
```

Or from source:

```bash
git clone https://github.com/WebOfTrust/kgql.git
cd kgql
pip install -e .
```

## Quick Start

```python
from kgql import KGQL

# Initialize with keripy instances
kgql = KGQL(hby=hby, rgy=rgy, verifier=verifier)

# Resolve a credential
result = kgql.resolve("ESAID...")
if result:
    print(f"Found: {result.said}")
    print(f"Issuer: {result.data.get('issuer')}")

# Query by issuer
creds = kgql.by_issuer("EAID...")
print(f"Found {len(creds)} credentials")

# Execute a KGQL query
result = kgql.query(
    "MATCH (c:Credential) WHERE c.issuer = $aid",
    variables={"aid": "EAID..."}
)
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

Traverse credential relationships:

```
TRAVERSE FROM $said FOLLOW edge
TRAVERSE FROM $said FOLLOW session
TRAVERSE FROM $said FOLLOW delegator
```

## Components

### Core API (`kgql.api`)

The main `KGQL` class provides:

- `query(kgql_string, variables)` - Execute any KGQL query
- `resolve(said)` - Resolve single credential
- `by_issuer(aid)` - Get credentials by issuer
- `by_subject(aid)` - Get credentials by subject
- `verify(said)` - Verify credential chain
- `traverse(from_said, edge_type)` - Traverse relationships
- `verify_end_to_end_chain(turn_said)` - Full chain verification

### Parser (`kgql.parser`)

Parses KGQL query strings into AST:

```python
from kgql.parser import KGQLParser

parser = KGQLParser()
ast = parser.parse("RESOLVE $said", variables={"said": "ESAID..."})
```

### Translator (`kgql.translator`)

Maps KGQL operations to keripy method calls:

```python
from kgql.translator import QueryPlanner

planner = QueryPlanner()
plan = planner.plan(ast)
# plan.steps contains keripy method mappings
```

### Wrappers (`kgql.wrappers`)

Thin wrappers for consistent interface:

- `RegerWrapper` - Wraps keripy Reger for credential queries
- `VerifierWrapper` - Wraps keripy Verifier for chain verification
- `EdgeResolver` - Protocol-agnostic edge resolution (ACDC, future: S3, Git)
- `ACDCEdgeResolver` - KERI/ACDC edge resolver using correct `"e"` field structure

### Indexer (`kgql.indexer`)

Schema-driven indexing based on [Phil Feairheller's](https://github.com/pfeairheller) KERIA Seeker pattern.

```python
from kgql.indexer import (
    SchemaIndexer,
    QueryEngine,
    create_query_engine,
    Eq, Begins, Gte,
)

# Register credential schemas
engine = create_query_engine({"EPerson_Schema": person_schema})

# Query with operators
results = engine.query(
    credentials,
    {
        "personLegalName": "Alice",           # Implicit $eq
        "LEI": {"$begins": "US"},             # Prefix match
        "age": {"$gte": 30},                  # Comparison
        "-s": "EPerson_Schema",               # Schema filter
    },
)
```

**Supported Operators:**
- `$eq` - Equality (default)
- `$begins` - Prefix match (efficient for LMDB range scans)
- `$lt`, `$gt`, `$lte`, `$gte` - Comparisons
- `$contains` - Substring match

**Credit:** The schema-driven indexing approach is inspired by the Seeker class in [KERIA](https://github.com/WebOfTrust/keria) (`keria/db/basing.py`), designed by Phil Feairheller.

### MCP Server (`kgql.mcp`)

Model Context Protocol server for Claude Code integration:

```bash
# Run as MCP server
python -m kgql.mcp

# See kgql/mcp/README.md for configuration
```

## Architecture

```
┌─────────────────────────────────────────────┐
│                KGQL Query                   │
│  "MATCH (c:Credential) WHERE c.issuer=$aid" │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│              KGQLParser                     │
│  Query string → AST                         │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│             QueryPlanner                    │
│  AST → ExecutionPlan (keripy methods)       │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│               KGQL                          │
│  Execute plan using wrappers                │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│   RegerWrapper / VerifierWrapper            │
│   Thin delegation to keripy                 │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│              keripy                         │
│   Habery, Regery, Verifier                  │
└─────────────────────────────────────────────┘
```

## Testing

```bash
python -m pytest tests/ -v
```

## Integration Patterns

### With HIO Doers

KGQL uses Deck pattern for async integration:

```python
from hio.help import Deck

kgql = KGQL(hby=hby, rgy=rgy)

# Push query to input Deck
kgql.queries.push(("query-1", "RESOLVE $said", {"said": "ESAID..."}))

# In your Doer, pull results
result = kgql.results.pull()
```

### With Claude Code

Configure KGQL MCP server in `.claude/settings.local.json`:

```json
{
  "mcpServers": {
    "kgql": {
      "command": "python3",
      "args": ["-m", "kgql.mcp"],
      "env": {}
    }
  }
}
```

Then use tools like `kgql_resolve`, `kgql_verify_chain`, etc.

## Chain Verification

The critical audit function verifies: Turn → Session → Master

```python
result = kgql.verify_end_to_end_chain(turn_said)

if result.metadata.get("valid"):
    chain = result.first.data["chain"]
    for step in chain:
        print(f"{step['type']}: {step['said'][:16]}...")
else:
    print(f"Chain invalid: {result.metadata.get('error')}")
```

## License

Apache 2.0
