"""
KGQL - KERI Graph Query Language main API.

This module provides the high-level interface for executing KGQL queries
against keripy infrastructure. It uses existing keripy methods without
duplicating any functionality.

Core Principle: "Resolution IS Verification" + "Don't Duplicate, Integrate"

Usage:
    from kgql import KGQL

    # Initialize with keripy instances
    kgql = KGQL(hby=hby, rgy=rgy, verifier=verifier)

    # Execute a query
    result = kgql.query("MATCH (c:Credential) WHERE c.issuer = $aid RETURN c",
                        variables={"aid": "EAID..."})

    # Access results
    for cred in result.items:
        print(cred.said, cred.issuer)
"""

from dataclasses import dataclass, field
from typing import Any, Iterator, Optional, TYPE_CHECKING

from hio.help import Deck

from kgql.parser import KGQLParser, KGQLQuery
from kgql.translator import QueryPlanner, ExecutionPlan, MethodType
from kgql.wrappers import RegerWrapper, VerifierWrapper

if TYPE_CHECKING:
    from keri.app.habbing import Habery
    from keri.vdr.verifying import Verifier, Regery


@dataclass
class QueryResultItem:
    """A single item in a query result."""
    said: str
    data: dict = field(default_factory=dict)
    proof: Optional[Any] = None
    keystate: Optional[Any] = None


@dataclass
class QueryResult:
    """
    Result of a KGQL query execution.

    Provides a unified result format for all query types.
    """
    items: list[QueryResultItem] = field(default_factory=list)
    count: int = 0
    has_more: bool = False
    metadata: dict = field(default_factory=dict)

    def __iter__(self) -> Iterator[QueryResultItem]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __bool__(self) -> bool:
        return len(self.items) > 0

    @property
    def first(self) -> Optional[QueryResultItem]:
        """Get the first result item, or None if empty."""
        return self.items[0] if self.items else None

    def collect_saids(self) -> list[str]:
        """Collect all SAIDs from the result items."""
        return [item.said for item in self.items]


class KGQL:
    """
    KGQL query interface using existing keripy infrastructure.

    NOT a Doer - uses Deck pattern for integration with existing Doers.
    All query execution delegates to existing keripy methods.

    Usage:
        # Initialize
        kgql = KGQL(hby=hby, rgy=rgy, verifier=verifier)

        # Synchronous query
        result = kgql.query("RESOLVE $said", variables={"said": "ESAID..."})

        # For async queries, use Deck integration
        kgql.queries.push(("query_id", query_string, variables))
        # ... later ...
        result = kgql.results.pull()
    """

    def __init__(
        self,
        hby: "Habery",
        rgy: "Regery",
        verifier: Optional["Verifier"] = None
    ):
        """
        Initialize KGQL with keripy instances.

        Args:
            hby: Habery instance for key state access
            rgy: Regery instance for credential access
            verifier: Optional Verifier instance for chain verification
        """
        self._hby = hby
        self._rgy = rgy
        self._reger = rgy.reger

        # Create wrappers for consistent interface
        self._reger_wrapper = RegerWrapper(self._reger)
        self._verifier_wrapper = VerifierWrapper(verifier, hby) if verifier else None

        # Parser and planner
        self._parser = KGQLParser()
        self._planner = QueryPlanner()

        # Deck for async query integration with existing Doist
        self.queries = Deck()  # Input: (query_id, query_string, variables)
        self.results = Deck()  # Output: (query_id, QueryResult)

    @property
    def reger(self):
        """Direct access to Reger for advanced queries."""
        return self._reger

    @property
    def hby(self):
        """Direct access to Habery for advanced operations."""
        return self._hby

    def query(
        self,
        kgql_string: str,
        variables: Optional[dict] = None
    ) -> QueryResult:
        """
        Execute a KGQL query synchronously.

        This is the main entry point for KGQL queries.

        Args:
            kgql_string: The KGQL query string
            variables: Optional dict of variable bindings ($name -> value)

        Returns:
            QueryResult with matched items

        Example:
            result = kgql.query(
                "MATCH (c:Credential) WHERE c.issuer = $aid",
                variables={"aid": "EAID..."}
            )
        """
        # Parse the query
        ast = self._parser.parse(kgql_string, variables)

        # Create execution plan
        plan = self._planner.plan(ast)

        # Execute the plan
        return self._execute(plan, variables or {})

    def parse(self, kgql_string: str) -> KGQLQuery:
        """
        Parse a KGQL query without executing.

        Useful for validation or inspection.

        Args:
            kgql_string: The KGQL query string

        Returns:
            Parsed KGQLQuery AST
        """
        return self._parser.parse(kgql_string)

    def plan(self, ast: KGQLQuery) -> ExecutionPlan:
        """
        Create an execution plan from a parsed AST.

        Useful for optimization or debugging.

        Args:
            ast: Parsed KGQLQuery AST

        Returns:
            ExecutionPlan with keripy method mapping
        """
        return self._planner.plan(ast)

    def _execute(self, plan: ExecutionPlan, variables: dict) -> QueryResult:
        """
        Execute a query plan using existing keripy methods.

        Each step in the plan maps directly to a keripy method call.
        """
        result = QueryResult()
        step_results = {}

        for idx, step in enumerate(plan.steps):
            # Resolve variables in step args
            resolved_args = self._resolve_variables(step.args, variables)

            # Execute step based on method type
            if step.method_type == MethodType.REGER_INDEX:
                step_result = self._execute_index_query(step, resolved_args)
            elif step.method_type == MethodType.REGER_CLONE:
                step_result = self._execute_clone(step, resolved_args)
            elif step.method_type == MethodType.REGER_SOURCES:
                step_result = self._execute_sources(step, resolved_args, step_results)
            elif step.method_type == MethodType.VERIFIER_CHAIN:
                step_result = self._execute_verify(step, resolved_args)
            else:
                step_result = None

            # Store result for dependent steps
            if step.result_key:
                step_results[step.result_key] = step_result

        # Build final result from step results
        result = self._build_result(step_results, plan)

        return result

    def _resolve_variables(self, args: dict, variables: dict) -> dict:
        """Resolve $variable references in arguments."""
        resolved = {}
        for key, value in args.items():
            if isinstance(value, str) and value.startswith("$"):
                var_name = value[1:]
                resolved[key] = variables.get(var_name, value)
            else:
                resolved[key] = value
        return resolved

    def _execute_index_query(self, step, args: dict) -> list:
        """Execute a Reger index query."""
        index_name = args.get("index", "creds")
        keys = args.get("keys")

        if index_name == "issus" and keys:
            return list(self._reger_wrapper.by_issuer(keys))
        elif index_name == "subjs" and keys:
            return list(self._reger_wrapper.by_subject(keys))
        elif index_name == "schms" and keys:
            return list(self._reger_wrapper.by_schema(keys))
        elif index_name == "creds":
            # Full scan - expensive but sometimes necessary
            results = []
            filter_dict = args.get("filter", {})
            for said, _ in self._reger.creds.getItemIter():
                if self._matches_filter(said, filter_dict):
                    results.append(said)
            return results

        return []

    def _execute_clone(self, step, args: dict) -> Optional[Any]:
        """Execute a credential clone/resolve."""
        said = args.get("said")
        if not said:
            return None

        return self._reger_wrapper.resolve(said)

    def _execute_sources(self, step, args: dict, prior_results: dict) -> list:
        """Execute a sources traversal."""
        # Get starting credential from prior step
        start_cred = prior_results.get("start_cred")
        if not start_cred:
            return []

        results = []
        for creder, proof in self._reger_wrapper.traverse_sources(
            self._hby.db, start_cred.said
        ):
            results.append((creder, proof))

        return results

    def _execute_verify(self, step, args: dict) -> Optional[Any]:
        """Execute chain verification."""
        if not self._verifier_wrapper:
            return None

        said = args.get("said")
        if not said:
            return None

        return self._verifier_wrapper.verify_chain(
            said=said,
            issuer=args.get("issuer"),
            operator=args.get("operator")
        )

    def _matches_filter(self, said: str, filter_dict: dict) -> bool:
        """Check if a credential matches filter conditions."""
        if not filter_dict:
            return True

        cred = self._reger_wrapper.resolve(said)
        if not cred:
            return False

        for field, condition in filter_dict.items():
            actual_value = getattr(cred, field, cred.data.get(field))
            expected_value = condition.get("value")
            op = condition.get("op", "=")
            negated = condition.get("negated", False)

            matches = self._compare(actual_value, op, expected_value)
            if negated:
                matches = not matches
            if not matches:
                return False

        return True

    def _compare(self, actual: Any, op: str, expected: Any) -> bool:
        """Compare values based on operator."""
        if op == "=":
            return actual == expected
        elif op == "!=":
            return actual != expected
        elif op == "<":
            return actual < expected
        elif op == ">":
            return actual > expected
        elif op == "<=":
            return actual <= expected
        elif op == ">=":
            return actual >= expected
        elif op == "LIKE":
            return expected in str(actual)
        elif op == "CONTAINS":
            return expected in actual if hasattr(actual, '__contains__') else False
        elif op == "IN":
            return actual in expected if hasattr(expected, '__contains__') else False
        return False

    def _build_result(self, step_results: dict, plan: ExecutionPlan) -> QueryResult:
        """Build the final QueryResult from step results."""
        result = QueryResult()

        # Collect all SAIDs from index queries
        for key, value in step_results.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):  # SAID
                        result.items.append(QueryResultItem(said=item))
                    elif isinstance(item, tuple):  # (creder, proof)
                        creder, proof = item
                        result.items.append(QueryResultItem(
                            said=creder.said if hasattr(creder, 'said') else str(creder),
                            data={"creder": creder},
                            proof=proof if plan.include_proof else None
                        ))
            elif hasattr(value, 'said'):  # CredentialResult or similar
                result.items.append(QueryResultItem(
                    said=value.said,
                    data={"raw": value.raw} if hasattr(value, 'raw') else {}
                ))

        # Apply limit
        if plan.limit and len(result.items) > plan.limit:
            result.has_more = True
            result.items = result.items[:plan.limit]

        result.count = len(result.items)
        return result

    # Convenience methods that map to common KGQL patterns

    def by_issuer(self, aid: str) -> QueryResult:
        """
        Get credentials by issuer AID.

        Equivalent to: MATCH (c:Credential) WHERE c.issuer = $aid
        """
        return self.query(
            "MATCH (c:Credential) WHERE c.issuer = $aid",
            variables={"aid": aid}
        )

    def by_subject(self, aid: str) -> QueryResult:
        """
        Get credentials by subject AID.

        Equivalent to: MATCH (c:Credential) WHERE c.subject = $aid
        """
        return self.query(
            "MATCH (c:Credential) WHERE c.subject = $aid",
            variables={"aid": aid}
        )

    def resolve(self, said: str) -> Optional[QueryResultItem]:
        """
        Resolve a single credential by SAID.

        Equivalent to: RESOLVE $said
        """
        result = self.query("RESOLVE $said", variables={"said": said})
        return result.first

    def verify(self, said: str) -> QueryResult:
        """
        Verify a credential chain.

        Equivalent to: VERIFY $said
        """
        return self.query("VERIFY $said", variables={"said": said})

    def traverse(self, from_said: str, edge_type: str = "edge") -> QueryResult:
        """
        Traverse credential chain from a starting SAID.

        Equivalent to: TRAVERSE FROM $said FOLLOW edge
        """
        return self.query(
            f"TRAVERSE FROM $said FOLLOW {edge_type}",
            variables={"said": from_said}
        )

    def traverse_delegator(self, session_cred_said: str) -> QueryResult:
        """
        Traverse session credential's delegator edge to master KEL event.

        This completes the chain: Turn → Session → Master KEL

        The delegator edge in a session credential contains:
        - n: Master AID prefix
        - s: KEL event SAID (preferred) or delegation seal SAID
        - o: Optional metadata with both SAIDs

        Args:
            session_cred_said: SAID of the session credential

        Returns:
            QueryResult with delegation chain information
        """
        result = QueryResult()

        # Resolve session credential
        session_item = self.resolve(session_cred_said)
        if not session_item:
            result.metadata = {"error": "Session credential not found"}
            return result

        # Get delegator edge using EdgeResolver pattern
        # ACDC edges are in "e" field with nested messages; target SAID is in "d" field
        cred_data = session_item.data
        edges = cred_data.get("e", {}) if isinstance(cred_data, dict) else {}
        delegator = edges.get("delegator", {})

        # In ACDC edge structure:
        # - "d" contains the SAID of the target (e.g., delegation event SAID)
        # - "i" contains the issuer/delegator AID
        # For delegation chains, master_pre is the delegator's AID from "i" field
        reference_said = delegator.get("d")  # Target/event SAID
        master_pre = delegator.get("i")  # Master AID prefix from issuer field
        # Additional metadata from the nested message
        metadata = {k: v for k, v in delegator.items() if k not in ("v", "d", "i", "t", "s")}

        if not master_pre:
            result.metadata = {"error": "No delegator edge found in session credential"}
            return result

        # Check if we have a KEL event SAID
        kel_event_said = metadata.get("kel_event_said") if metadata else None

        # Try to verify master KEL event exists
        try:
            master_kever = self._hby.kevers.get(master_pre)
            if not master_kever:
                result.metadata = {
                    "error": f"Master AID {master_pre[:16]}... not found in KEL",
                    "master_pre": master_pre,
                    "reference_said": reference_said,
                }
                return result

            # If we have a KEL event SAID, try to find it in master's events
            found_event = None
            if kel_event_said:
                # Search master's KEL for the anchoring event
                # In keripy, we iterate through interaction events
                try:
                    for pre, dig in self._hby.db.getKelIter(master_pre):
                        # Load event
                        evt = self._hby.db.getEvt(pre, dig)
                        if evt and hasattr(evt, 'said') and evt.said == kel_event_said:
                            found_event = evt
                            break
                except Exception as e:
                    # KEL iteration may not be supported in all keripy versions
                    pass

            # Build result
            result.items.append(QueryResultItem(
                said=kel_event_said or reference_said,
                data={
                    "master_pre": master_pre,
                    "kel_event_said": kel_event_said,
                    "seal_said": metadata.get("seal_said") if metadata else reference_said,
                    "kel_verified": found_event is not None,
                    "master_sn": master_kever.sner.num if master_kever else None,
                },
            ))
            result.metadata = {
                "chain": "session → master",
                "kel_anchored": kel_event_said is not None,
            }

        except Exception as e:
            result.metadata = {
                "error": f"Delegator traversal failed: {e}",
                "master_pre": master_pre,
            }

        return result

    def verify_end_to_end_chain(self, turn_said: str) -> QueryResult:
        """
        Verify complete chain: Turn → Session → Master KEL

        This is the critical production verification that ensures
        a turn credential chains all the way back to the master AID.

        Args:
            turn_said: SAID of the turn credential

        Returns:
            QueryResult with full chain verification info
        """
        result = QueryResult()
        chain = []

        # Step 1: Resolve turn credential
        turn_item = self.resolve(turn_said)
        if not turn_item:
            result.metadata = {"valid": False, "error": "Turn credential not found"}
            return result

        chain.append({
            "type": "turn",
            "said": turn_said,
            "issuer": turn_item.data.get("issuer") if isinstance(turn_item.data, dict) else None,
        })

        # Step 2: Traverse to session
        # ACDC edges are in "e" field; target SAID is in "d" field of nested message
        turn_data = turn_item.data if isinstance(turn_item.data, dict) else {}
        turn_edges = turn_data.get("e", {})
        session_edge = turn_edges.get("session", {})
        session_said = session_edge.get("d")  # Target SAID in "d" field

        if not session_said:
            result.metadata = {
                "valid": False,
                "error": "Turn has no session edge",
                "chain": chain,
            }
            return result

        session_item = self.resolve(session_said)
        if not session_item:
            result.metadata = {
                "valid": False,
                "error": f"Session credential {session_said[:16]}... not found",
                "chain": chain,
            }
            return result

        chain.append({
            "type": "session",
            "said": session_said,
        })

        # Step 3: Traverse delegator edge to master KEL
        delegator_result = self.traverse_delegator(session_said)

        if not delegator_result.first:
            result.metadata = {
                "valid": False,
                "error": delegator_result.metadata.get("error", "Delegator not found"),
                "chain": chain,
            }
            return result

        delegator_data = delegator_result.first.data
        chain.append({
            "type": "master_delegation",
            "said": delegator_result.first.said,
            "master_pre": delegator_data.get("master_pre"),
            "kel_verified": delegator_data.get("kel_verified", False),
        })

        # Build final result
        result.items.append(QueryResultItem(
            said=turn_said,
            data={
                "chain": chain,
                "chain_length": len(chain),
                "kel_anchored": delegator_data.get("kel_event_said") is not None,
            },
        ))
        result.metadata = {
            "valid": True,
            "chain_length": len(chain),
        }

        return result
