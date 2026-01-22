"""
KGQL Query Planner - Translates AST to keripy method calls.

This module maps KGQL query AST nodes to the appropriate keripy methods,
without duplicating any existing infrastructure.

Translation Map:
    MATCH operations → Reger index lookups (issus, subjs, schms)
    RESOLVE → Reger.cloneCred
    TRAVERSE → Reger.sources (recursive)
    VERIFY → Verifier.verifyChain
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Union

from kgql.parser.ast import (
    KGQLQuery,
    MatchOperation,
    ResolveOperation,
    TraverseOperation,
    VerifyOperation,
    EdgeOperator,
    Condition,
    Comparator,
)


class MethodType(Enum):
    """Types of keripy methods that can be called."""
    REGER_INDEX = "reger_index"      # issus, subjs, schms
    REGER_CLONE = "reger_clone"      # cloneCred
    REGER_SOURCES = "reger_sources"  # sources
    VERIFIER_CHAIN = "verifier_chain"  # verifyChain
    KEVER_STATE = "kever_state"      # get key state


@dataclass
class PlanStep:
    """
    A single step in the execution plan.

    Each step maps to exactly one keripy method call.
    """
    method_type: MethodType
    method_name: str
    args: dict[str, Any] = field(default_factory=dict)
    depends_on: list[int] = field(default_factory=list)  # indices of prior steps
    result_key: str = ""  # key to store result for later steps


@dataclass
class ExecutionPlan:
    """
    Complete execution plan for a KGQL query.

    Contains an ordered list of steps that map directly to keripy methods.
    No new logic - just orchestration of existing infrastructure.
    """
    steps: list[PlanStep] = field(default_factory=list)
    return_fields: list[str] = field(default_factory=list)
    include_proof: bool = False
    include_keystate: bool = False
    limit: Optional[int] = None
    order_by: Optional[str] = None
    order_direction: str = "ASC"

    def add_step(self, step: PlanStep) -> int:
        """Add a step and return its index."""
        step_idx = len(self.steps)
        self.steps.append(step)
        return step_idx


class QueryPlanner:
    """
    Translates KGQL AST to execution plans.

    The planner maps KGQL operations to existing keripy methods:

    | KGQL Operation | keripy Method | Notes |
    |----------------|---------------|-------|
    | MATCH by issuer | reger.issus.get() | Index lookup |
    | MATCH by subject | reger.subjs.get() | Index lookup |
    | MATCH by schema | reger.schms.get() | Index lookup |
    | RESOLVE said | reger.cloneCred() | Direct fetch |
    | TRAVERSE edge | reger.sources() | Recursive |
    | VERIFY chain | verifier.verifyChain() | Full verification |
    """

    def __init__(self):
        # Map of (node_type, field_name) -> reger index method
        self._index_map = {
            ("Credential", "issuer"): ("issus", "getIter"),
            ("Credential", "subject"): ("subjs", "getIter"),
            ("Credential", "schema"): ("schms", "getIter"),
            ("Session", "agent_aid"): ("issus", "getIter"),
            ("Turn", "session"): ("issus", "getIter"),
            ("Decision", "topic"): None,  # Requires scan, no direct index
        }

    def plan(self, query: KGQLQuery) -> ExecutionPlan:
        """
        Create an execution plan for a KGQL query.

        Args:
            query: Parsed KGQL query AST

        Returns:
            ExecutionPlan with steps mapping to keripy methods
        """
        plan = ExecutionPlan()

        # Handle modifiers
        if query.with_options:
            plan.include_proof = query.with_options.include_proof
            plan.include_keystate = query.with_options.include_keystate

        if query.limit:
            plan.limit = query.limit

        if query.order_by:
            plan.order_by = query.order_by.field
            plan.order_direction = query.order_by.direction.value

        if query.return_clause:
            plan.return_fields = [item.expression for item in query.return_clause.items]

        # Plan the operation
        if query.match:
            self._plan_match(query.match, query.where, plan)
        elif query.resolve:
            self._plan_resolve(query.resolve, plan)
        elif query.traverse:
            self._plan_traverse(query.traverse, plan)
        elif query.verify:
            # Use AGAINST clause if present, otherwise fall back to top-level context
            keystate = query.verify.against_keystate or query.keystate_context
            self._plan_verify(query.verify, keystate, plan)

        return plan

    def _plan_match(
        self,
        match: MatchOperation,
        where: Optional[Any],
        plan: ExecutionPlan
    ) -> None:
        """
        Plan a MATCH operation.

        Translates to reger index lookups (issus, subjs, schms).
        """
        for node, edge in match.patterns:
            # Determine which index to use based on WHERE conditions
            index_step = self._find_index_for_match(node, where)
            if index_step:
                plan.add_step(index_step)

            # If edge pattern specifies an operator, add verification step
            if edge and edge.operator != EdgeOperator.ANY:
                verify_step = PlanStep(
                    method_type=MethodType.VERIFIER_CHAIN,
                    method_name="verifyChain",
                    args={
                        "operator": edge.operator.value,
                    },
                    depends_on=[len(plan.steps) - 1] if plan.steps else [],
                    result_key="verified_edges"
                )
                plan.add_step(verify_step)

    def _find_index_for_match(
        self,
        node: Any,
        where: Optional[Any]
    ) -> Optional[PlanStep]:
        """
        Determine which Reger index to use for a MATCH pattern.

        Returns a PlanStep for the appropriate index lookup.
        """
        if not where or not where.conditions:
            # No WHERE clause - need full scan (expensive!)
            return PlanStep(
                method_type=MethodType.REGER_INDEX,
                method_name="getItemIter",
                args={"index": "creds"},
                result_key="all_creds"
            )

        # Find indexed conditions
        for condition in where.conditions:
            field_parts = condition.field.split(".")
            if len(field_parts) >= 2:
                field_name = field_parts[-1]
            else:
                field_name = condition.field

            # Map field to index
            node_type = node.node_type if node else "Credential"
            index_key = (node_type, field_name)

            if index_key in self._index_map:
                index_info = self._index_map[index_key]
                if index_info:
                    index_name, method = index_info
                    return PlanStep(
                        method_type=MethodType.REGER_INDEX,
                        method_name=method,
                        args={
                            "index": index_name,
                            "keys": self._extract_condition_value(condition),
                        },
                        result_key=f"{index_name}_results"
                    )

        # No indexed field found - fall back to scan with filter
        return PlanStep(
            method_type=MethodType.REGER_INDEX,
            method_name="getItemIter",
            args={
                "index": "creds",
                "filter": self._conditions_to_filter(where.conditions),
            },
            result_key="filtered_creds"
        )

    def _plan_resolve(self, resolve: ResolveOperation, plan: ExecutionPlan) -> None:
        """
        Plan a RESOLVE operation.

        Translates to reger.cloneCred(said).
        """
        plan.add_step(PlanStep(
            method_type=MethodType.REGER_CLONE,
            method_name="cloneCred",
            args={
                "said": resolve.said,
                "is_variable": resolve.is_variable,
            },
            result_key="credential"
        ))

    def _plan_traverse(self, traverse: TraverseOperation, plan: ExecutionPlan) -> None:
        """
        Plan a TRAVERSE operation.

        Translates to reger.sources() for recursive chain traversal.
        """
        # Step 1: Resolve the starting credential
        start_said = traverse.from_said
        if start_said:
            plan.add_step(PlanStep(
                method_type=MethodType.REGER_CLONE,
                method_name="cloneCred",
                args={"said": start_said},
                result_key="start_cred"
            ))

        # Step 2: Traverse using sources()
        plan.add_step(PlanStep(
            method_type=MethodType.REGER_SOURCES,
            method_name="sources",
            args={
                "follow_type": traverse.follow_type,
                "via_operator": traverse.via_edge.operator.value if traverse.via_edge else None,
            },
            depends_on=[len(plan.steps) - 1] if plan.steps else [],
            result_key="source_chain"
        ))

        # Step 3: If target specified, filter to matching
        if traverse.to_said or traverse.to_pattern:
            plan.steps[-1].args["target_said"] = traverse.to_said
            plan.steps[-1].args["target_pattern"] = traverse.to_pattern

    def _plan_verify(
        self,
        verify: VerifyOperation,
        keystate_ctx: Optional[Any],
        plan: ExecutionPlan
    ) -> None:
        """
        Plan a VERIFY operation.

        Translates to verifier.verifyChain().
        """
        plan.add_step(PlanStep(
            method_type=MethodType.VERIFIER_CHAIN,
            method_name="verifyChain",
            args={
                "said": verify.said,
                "is_variable": verify.is_variable,
                "keystate_aid": keystate_ctx.aid if keystate_ctx else None,
                "keystate_seq": keystate_ctx.seq if keystate_ctx else None,
            },
            result_key="verification_result"
        ))

    def _extract_condition_value(self, condition: Condition) -> Any:
        """Extract the value from a condition for index lookup."""
        return condition.value

    def _conditions_to_filter(self, conditions: list[Condition]) -> dict:
        """Convert conditions to a filter dict for non-indexed queries."""
        filters = {}
        for cond in conditions:
            filters[cond.field] = {
                "op": cond.comparator.value,
                "value": cond.value,
                "negated": cond.negated,
            }
        return filters


def plan_query(query: KGQLQuery) -> ExecutionPlan:
    """
    Convenience function to create an execution plan.

    Args:
        query: Parsed KGQL query AST

    Returns:
        ExecutionPlan with steps mapping to keripy methods
    """
    planner = QueryPlanner()
    return planner.plan(query)
