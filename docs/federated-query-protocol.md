# KGQL Federated Query Protocol

## Overview

Federated KGQL enables queries across organizational boundaries. Each organization runs a KGQL instance over its local credential store (Reger). A federated query routes sub-queries to the relevant instances, merges results, and returns a unified result set — all within the constraints of the applicable governance framework.

The key insight: **KERI's trust model is already federated**. Credentials are verifiable anywhere because verification depends only on the KEL, not on the issuing organization's infrastructure. Federated KGQL extends this to queries.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                 KGQL Federation Layer                 │
│                                                       │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐         │
│  │  Org A   │   │  Org B   │   │  Org C   │         │
│  │  KGQL    │   │  KGQL    │   │  KGQL    │         │
│  │  Reger   │   │  Reger   │   │  Reger   │         │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘         │
│       │              │              │                 │
│       └──────────────┼──────────────┘                 │
│                      │                                │
│              ┌───────▼───────┐                        │
│              │  Federation   │                        │
│              │  Coordinator  │                        │
│              └───────────────┘                        │
└──────────────────────────────────────────────────────┘
```

## 1. Query Routing

### Endpoint Discovery via OOBI

Organizations advertise KGQL endpoints via OOBI (Out-Of-Band Introduction):

```
{
  "eid": "EOrg_AID...",
  "scheme": "https",
  "url": "https://org.example.com/kgql",
  "role": "kgql-federation"
}
```

The federation coordinator maintains an OOBI-resolved registry of KGQL endpoints, indexed by:
- **Schema SAID**: Which credential schemas the endpoint serves
- **Issuer prefix**: Which AIDs issue credentials at this endpoint
- **Framework SAID**: Which governance frameworks apply

### Route Selection

Given a federated query:

```
WITHIN FRAMEWORK 'EFrameworkSAID...'
MATCH (qvi:QVI)-[:authorized @DI2I]->(le:LE)
WHERE qvi.issuer = 'EQVI_AID...'
```

The coordinator:
1. Resolves the framework SAID to determine participating organizations
2. Checks the `authorities` field for authorized endpoints
3. Routes sub-queries to endpoints that hold relevant credentials
4. Falls back to broadcast if routing is ambiguous

### Sub-query Decomposition

The coordinator decomposes multi-hop queries at organizational boundaries:

```
Original:  ROOT org-A → INTERMEDIATE org-B → TARGET org-C
Sub-query 1 (Org A): MATCH credentials where issuer = ROOT
Sub-query 2 (Org B): MATCH credentials where subject = INTERMEDIATE
Sub-query 3 (Org C): MATCH credentials where subject = TARGET
```

## 2. Privacy: Framework-Bounded Disclosure

### Principle

Each organization reveals only what the governance framework permits. The framework's credential matrix defines which fields are disclosable for each action and role.

### Disclosure Rules

The governance framework can include disclosure constraints:

```json
{
  "disclosure_rules": [
    {
      "action": "federated_query",
      "role": "external_org",
      "fields": ["said", "issuer", "schema", "status"],
      "exclude": ["a.personal_data", "a.internal_ref"]
    }
  ]
}
```

### Minimal Disclosure Protocol

1. Remote endpoint receives sub-query
2. Evaluates against local governance framework
3. Returns only permitted fields (SAIDs, issuer AIDs, schema refs)
4. Full credential data requires separate authorized RESOLVE

## 3. Result Merging

### Merge Strategy

Results from multiple endpoints are merged by SAID (content-addressed, so duplicates are identical):

```
Local results:   [{said: "EA...", ...}, {said: "EB...", ...}]
Remote results:  [{said: "EB...", ...}, {said: "EC...", ...}]
Merged:          [{said: "EA...", ...}, {said: "EB...", ...}, {said: "EC...", ...}]
```

### Conflict Resolution

No conflict is possible for credential data (SAID = content hash). Metadata conflicts (e.g., different revocation states) are resolved by:
1. Checking TEL for authoritative revocation status
2. Using the most recent TEL event timestamp
3. Flagging discrepancies in the query result metadata

### Provenance Tracking

Each result carries provenance metadata:

```json
{
  "said": "ECred...",
  "source": {
    "endpoint": "https://org-a.example.com/kgql",
    "endpoint_aid": "EOrg_A_AID...",
    "query_time": "2024-01-14T12:00:00Z"
  }
}
```

## 4. Trust: Verifying Remote Results

### Query Attestation

Each sub-query response is an ACDC credential issued by the responding endpoint's AID:

```json
{
  "v": "ACDC10JSON...",
  "d": "<response SAID>",
  "i": "<endpoint AID>",
  "s": "<KGQLQueryResponse schema>",
  "a": {
    "query_said": "<original query SAID>",
    "results": [...],
    "result_count": 42,
    "framework_said": "EFramework..."
  }
}
```

This means:
- **Response integrity**: SAID guarantees content hasn't changed
- **Response authenticity**: Endpoint AID signature verifiable via KEL
- **Non-repudiation**: Endpoint can't deny having returned these results

### Verification Chain

The coordinator verifies each sub-query response:
1. Verify response SAID matches content
2. Verify endpoint AID signature via KEL
3. Check endpoint AID is authorized in the governance framework
4. Optionally verify individual credential SAIDs in results

## 5. Transport: CESR-Native Messages

### Message Format

Federated queries use CESR-encoded messages for transport:

```
Query Request:  { "t": "kgql/req", "d": "<SAID>", "q": "<KGQL query>", "fw": "<framework SAID>" }
Query Response: { "t": "kgql/res", "d": "<SAID>", "r": [...results...], "p": { ...provenance... } }
Query Error:    { "t": "kgql/err", "d": "<SAID>", "e": { "code": "...", "msg": "..." } }
```

### Transport Protocol

1. **OOBI Discovery**: Resolve endpoint URLs from OOBIs
2. **SSE Stream**: Long-running queries use Server-Sent Events
3. **Batch Mode**: Multiple sub-queries in a single request
4. **Timeout**: Per-endpoint timeout with partial result return

### Error Handling

- **Endpoint Unreachable**: Skip and return partial results with warning
- **Authorization Denied**: Governance framework doesn't permit this query
- **Timeout**: Return results gathered so far with timeout metadata

## 6. Implementation Phases

### Phase 1: Local Federation (Single Process)
- FederationCoordinator class that routes to multiple local FrameworkResolvers
- Result merging logic
- Provenance tracking

### Phase 2: Network Federation
- OOBI-based endpoint discovery
- HTTP/SSE transport
- CESR message encoding

### Phase 3: Attested Federation
- Query response as ACDC credentials
- Endpoint authorization via governance framework
- Non-repudiation audit trail

## Data Structures

```python
@dataclass
class FederatedEndpoint:
    aid: str                     # Endpoint AID
    url: str                     # KGQL endpoint URL
    schemas: list[str]           # Schema SAIDs served
    frameworks: list[str]        # Framework SAIDs applicable

@dataclass
class SubQuery:
    query: str                   # KGQL query string
    target_endpoint: FederatedEndpoint
    framework_said: str
    timeout_ms: int = 5000

@dataclass
class FederatedResult:
    results: list[dict]          # Merged credential results
    provenance: list[dict]       # Per-result source tracking
    warnings: list[str]          # Partial failures, timeouts
    endpoints_queried: int
    endpoints_responded: int
```
