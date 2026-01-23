# -*- encoding: utf-8 -*-
"""
Tests for KGQL Edge Resolver functionality.

These tests verify the EdgeResolver abstraction, ACDCEdgeResolver implementation,
and EdgeResolverRegistry using real ACDC credential structures from keripy.
"""

import pytest

from kgql.wrappers import (
    EdgeRef,
    EdgeResolver,
    ACDCEdgeResolver,
    EdgeResolverRegistry,
    create_default_registry,
)


# Test fixtures - Real ACDC structures from keripy/tests/vc/test_protocoling.py


@pytest.fixture
def simple_credential():
    """Simple ACDC credential with issuance edge."""
    return {
        "v": "ACDC10JSON000197_",
        "d": "EElymNmgs1u0mSaoCeOtSsNOROLuqOz103V3-4E-ClXH",
        "i": "EMl4RhuR_JxpiMd1N8DEJEhTxM3Ovvn9Xya8AN-tiUbl",
        "ri": "EB-u4VAF7A7_GR8PXJoAVHv5X9vjtXew8Yo6Z3w9mQUQ",
        "s": "EMQWEcCnVRk1hatTNyK3sIykYSrrFvafX3bHQ9Gkk1kC",
        "a": {
            "d": "EO9_6NattzsFiO8Fw1cxjYmDjOsKKSbootn-wXn9S3iB",
            "dt": "2021-06-27T21:26:21.233257+00:00",
            "i": "EMl4RhuR_JxpiMd1N8DEJEhTxM3Ovvn9Xya8AN-tiUbl",
            "LEI": "254900OPPU84GM83MG36",
        },
        "e": {
            "iss": {
                "v": "KERI10JSON0000ed_",
                "t": "iss",
                "d": "ECUw7AdWEE3fvr7dgbFDXj0CEZuJTTa_H8-iLLAmIUPO",
                "i": "EElymNmgs1u0mSaoCeOtSsNOROLuqOz103V3-4E-ClXH",
                "s": "0",
                "ri": "EB-u4VAF7A7_GR8PXJoAVHv5X9vjtXew8Yo6Z3w9mQUQ",
            }
        },
    }


@pytest.fixture
def credential_with_chained_acdc():
    """ACDC credential with nested ACDC edge."""
    return {
        "v": "ACDC10JSON000250_",
        "d": "EParentCredentialSAID12345678901234567890",
        "i": "EIssuerAID12345678901234567890123456789012",
        "s": "ESchemaSAID123456789012345678901234567890",
        "a": {"d": "EAttrSAID1234567890123456789012345678901"},
        "e": {
            "acdc": {
                "v": "ACDC10JSON000197_",
                "d": "EChildCredentialSAID1234567890123456789",
                "i": "EChildIssuerAID123456789012345678901234",
                "s": "EChildSchemaSAID12345678901234567890123",
                "a": {"d": "EChildAttrSAID12345678901234567890123"},
            },
            "iss": {
                "v": "KERI10JSON0000ed_",
                "t": "iss",
                "d": "EIssuanceEventSAID123456789012345678901",
                "i": "EParentCredentialSAID12345678901234567890",
                "s": "0",
            },
        },
    }


@pytest.fixture
def credential_with_registry_edge():
    """Credential with VCP (registry inception) edge."""
    return {
        "v": "ACDC10JSON000197_",
        "d": "ECredentialSAID12345678901234567890123456",
        "i": "EIssuerAID12345678901234567890123456789012",
        "s": "ESchemaSAID123456789012345678901234567890",
        "a": {"d": "EAttrSAID1234567890123456789012345678901"},
        "e": {
            "vcp": {
                "v": "KERI10JSON00010f_",
                "t": "vcp",
                "d": "EI6hBlgkWoJgkZyfLW35_UyM4nIK44OgsSwFR_WOfvVB",
                "i": "EI6hBlgkWoJgkZyfLW35_UyM4nIK44OgsSwFR_WOfvVB",
                "ii": "EIaGMMWJFPmtXznY1IIiKDIrg-vIyge6mBl2QV8dDjI3",
                "s": "0",
                "c": [],
                "bt": "0",
                "b": [],
            },
            "ixn": {
                "v": "KERI10JSON000138_",
                "t": "ixn",
                "d": "EFuFnevyDFfpWG6il-6Qcv0ne0ZIItLwanCwI-SU8A9j",
                "i": "EIaGMMWJFPmtXznY1IIiKDIrg-vIyge6mBl2QV8dDjI3",
                "s": "1",
                "p": "EIaGMMWJFPmtXznY1IIiKDIrg-vIyge6mBl2QV8dDjI3",
            },
        },
    }


@pytest.fixture
def credential_no_edges():
    """Credential with empty edges."""
    return {
        "v": "ACDC10JSON000100_",
        "d": "ENoEdgesCredSAID123456789012345678901234",
        "i": "EIssuerAID12345678901234567890123456789012",
        "s": "ESchemaSAID123456789012345678901234567890",
        "a": {"d": "EAttrSAID1234567890123456789012345678901"},
        "e": {},
    }


# EdgeRef Tests


class TestEdgeRef:
    """Tests for EdgeRef dataclass."""

    def test_edge_ref_creation(self):
        """Test basic EdgeRef creation."""
        ref = EdgeRef(
            target_said="ESAID12345678901234567890123456789012345",
            edge_type="iss",
            payload_type="iss",
            source_protocol="keri",
        )
        assert ref.target_said == "ESAID12345678901234567890123456789012345"
        assert ref.edge_type == "iss"
        assert ref.payload_type == "iss"
        assert ref.source_protocol == "keri"
        assert ref.metadata == {}
        assert ref.raw_message is None

    def test_edge_ref_with_metadata(self):
        """Test EdgeRef with metadata."""
        ref = EdgeRef(
            target_said="ESAID12345",
            edge_type="acdc",
            metadata={"issuer": "EISSUER123", "schema": "ESCHEMA456"},
        )
        assert ref.metadata["issuer"] == "EISSUER123"
        assert ref.metadata["schema"] == "ESCHEMA456"

    def test_edge_ref_repr(self):
        """Test EdgeRef string representation."""
        ref = EdgeRef(
            target_said="ESAID12345678901234567890123456789012345",
            edge_type="iss",
            payload_type="iss",
        )
        repr_str = repr(ref)
        assert "EdgeRef" in repr_str
        assert "iss" in repr_str


# ACDCEdgeResolver Tests


class TestACDCEdgeResolver:
    """Tests for ACDCEdgeResolver."""

    def test_protocol_identifier(self):
        """Test protocol property."""
        resolver = ACDCEdgeResolver()
        assert resolver.protocol == "keri"

    def test_get_iss_edge(self, simple_credential):
        """Test extracting issuance edge."""
        resolver = ACDCEdgeResolver()
        edge = resolver.get_edge(simple_credential, "iss")

        assert edge is not None
        assert edge.target_said == "ECUw7AdWEE3fvr7dgbFDXj0CEZuJTTa_H8-iLLAmIUPO"
        assert edge.edge_type == "iss"
        assert edge.payload_type == "iss"
        assert edge.source_protocol == "keri"

    def test_get_acdc_edge(self, credential_with_chained_acdc):
        """Test extracting chained ACDC edge."""
        resolver = ACDCEdgeResolver()
        edge = resolver.get_edge(credential_with_chained_acdc, "acdc")

        assert edge is not None
        assert edge.target_said == "EChildCredentialSAID1234567890123456789"
        assert edge.edge_type == "acdc"
        assert edge.payload_type == "acdc"  # Detected from version string

    def test_get_vcp_edge(self, credential_with_registry_edge):
        """Test extracting VCP (registry inception) edge."""
        resolver = ACDCEdgeResolver()
        edge = resolver.get_edge(credential_with_registry_edge, "vcp")

        assert edge is not None
        assert edge.target_said == "EI6hBlgkWoJgkZyfLW35_UyM4nIK44OgsSwFR_WOfvVB"
        assert edge.edge_type == "vcp"
        assert edge.payload_type == "vcp"

    def test_get_ixn_edge(self, credential_with_registry_edge):
        """Test extracting IXN (interaction) edge."""
        resolver = ACDCEdgeResolver()
        edge = resolver.get_edge(credential_with_registry_edge, "ixn")

        assert edge is not None
        assert edge.target_said == "EFuFnevyDFfpWG6il-6Qcv0ne0ZIItLwanCwI-SU8A9j"
        assert edge.payload_type == "ixn"

    def test_get_nonexistent_edge(self, simple_credential):
        """Test requesting edge that doesn't exist."""
        resolver = ACDCEdgeResolver()
        edge = resolver.get_edge(simple_credential, "nonexistent")
        assert edge is None

    def test_get_edge_empty_edges(self, credential_no_edges):
        """Test credential with empty edges dict."""
        resolver = ACDCEdgeResolver()
        edge = resolver.get_edge(credential_no_edges, "iss")
        assert edge is None

    def test_get_edge_non_dict_content(self):
        """Test with non-dict content."""
        resolver = ACDCEdgeResolver()
        assert resolver.get_edge("not a dict", "iss") is None
        assert resolver.get_edge(None, "iss") is None
        assert resolver.get_edge([], "iss") is None

    def test_list_edges(self, simple_credential):
        """Test listing edges."""
        resolver = ACDCEdgeResolver()
        edges = resolver.list_edges(simple_credential)
        assert edges == ["iss"]

    def test_list_edges_multiple(self, credential_with_chained_acdc):
        """Test listing multiple edges."""
        resolver = ACDCEdgeResolver()
        edges = resolver.list_edges(credential_with_chained_acdc)
        assert set(edges) == {"acdc", "iss"}

    def test_list_edges_empty(self, credential_no_edges):
        """Test listing edges on empty edges dict."""
        resolver = ACDCEdgeResolver()
        edges = resolver.list_edges(credential_no_edges)
        assert edges == []

    def test_can_resolve_acdc(self, simple_credential):
        """Test can_resolve for ACDC credential."""
        resolver = ACDCEdgeResolver()
        assert resolver.can_resolve(simple_credential) is True

    def test_can_resolve_non_acdc(self):
        """Test can_resolve for non-ACDC content."""
        resolver = ACDCEdgeResolver()
        assert resolver.can_resolve({"random": "dict"}) is False
        assert resolver.can_resolve("string") is False

    def test_edge_metadata(self, simple_credential):
        """Test that edge metadata is populated."""
        resolver = ACDCEdgeResolver()
        edge = resolver.get_edge(simple_credential, "iss")

        assert edge is not None
        assert "version" in edge.metadata
        assert edge.metadata["version"] == "KERI10JSON0000ed_"
        assert edge.raw_message is not None
        assert edge.raw_message["t"] == "iss"


# EdgeResolverRegistry Tests


class TestEdgeResolverRegistry:
    """Tests for EdgeResolverRegistry."""

    def test_register_resolver(self):
        """Test registering a resolver."""
        registry = EdgeResolverRegistry()
        resolver = ACDCEdgeResolver()

        registry.register(resolver)

        assert "keri" in registry
        assert registry.get("keri") is resolver
        assert len(registry) == 1

    def test_protocols_list(self):
        """Test listing protocols."""
        registry = EdgeResolverRegistry()
        registry.register(ACDCEdgeResolver())

        protocols = registry.protocols()
        assert protocols == ["keri"]

    def test_unregister_resolver(self):
        """Test unregistering a resolver."""
        registry = EdgeResolverRegistry()
        resolver = ACDCEdgeResolver()
        registry.register(resolver)

        removed = registry.unregister("keri")

        assert removed is resolver
        assert "keri" not in registry
        assert len(registry) == 0

    def test_resolve_edge(self, simple_credential):
        """Test resolving edge through registry."""
        registry = EdgeResolverRegistry()
        registry.register(ACDCEdgeResolver())

        edge = registry.resolve_edge(simple_credential, "iss")

        assert edge is not None
        assert edge.target_said == "ECUw7AdWEE3fvr7dgbFDXj0CEZuJTTa_H8-iLLAmIUPO"

    def test_resolve_edge_with_hint(self, simple_credential):
        """Test resolving edge with protocol hint."""
        registry = EdgeResolverRegistry()
        registry.register(ACDCEdgeResolver())

        edge = registry.resolve_edge(simple_credential, "iss", protocol_hint="keri")
        assert edge is not None

        # Wrong hint should return None
        edge = registry.resolve_edge(simple_credential, "iss", protocol_hint="s3")
        assert edge is None

    def test_list_edges_through_registry(self, credential_with_chained_acdc):
        """Test listing edges through registry."""
        registry = EdgeResolverRegistry()
        registry.register(ACDCEdgeResolver())

        edges = registry.list_edges(credential_with_chained_acdc)
        assert set(edges) == {"acdc", "iss"}

    def test_list_all_edges(self, credential_with_chained_acdc):
        """Test listing edges from all resolvers."""
        registry = EdgeResolverRegistry()
        registry.register(ACDCEdgeResolver())

        all_edges = registry.list_all_edges(credential_with_chained_acdc)

        assert "keri" in all_edges
        assert set(all_edges["keri"]) == {"acdc", "iss"}

    def test_resolve_all_edges(self, credential_with_chained_acdc):
        """Test resolving all edges at once."""
        registry = EdgeResolverRegistry()
        registry.register(ACDCEdgeResolver())

        all_refs = registry.resolve_all_edges(credential_with_chained_acdc)

        assert "acdc" in all_refs
        assert "iss" in all_refs
        assert all_refs["acdc"].edge_type == "acdc"
        assert all_refs["iss"].edge_type == "iss"

    def test_create_default_registry(self):
        """Test default registry factory."""
        registry = create_default_registry()

        assert "keri" in registry
        assert isinstance(registry.get("keri"), ACDCEdgeResolver)


# Integration Tests


class TestEdgeResolverIntegration:
    """Integration tests for edge resolution workflow."""

    def test_full_edge_traversal_workflow(self, credential_with_chained_acdc):
        """Test complete edge resolution workflow."""
        registry = create_default_registry()

        # List available edges
        edges = registry.list_edges(credential_with_chained_acdc)
        assert len(edges) == 2

        # Resolve each edge
        for edge_name in edges:
            edge_ref = registry.resolve_edge(credential_with_chained_acdc, edge_name)
            assert edge_ref is not None
            assert edge_ref.target_said  # Has a target
            assert edge_ref.edge_type == edge_name

    def test_edge_chain_navigation(self):
        """Test navigating a chain of edges."""
        # Simulate a credential chain
        root_cred = {
            "v": "ACDC10JSON000100_",
            "d": "ERootCredSAID1234567890123456789012345",
            "i": "EIssuerAID12345678901234567890123456789012",
            "s": "ESchemaSAID123456789012345678901234567890",
            "a": {"d": "EAttrSAID1"},
            "e": {
                "acdc": {
                    "v": "ACDC10JSON000100_",
                    "d": "EChildCredSAID123456789012345678901234",
                    "i": "EChildIssuer1234567890123456789012345",
                    "s": "EChildSchema1234567890123456789012345",
                    "a": {"d": "EChildAttr1"},
                }
            },
        }

        registry = create_default_registry()

        # Navigate to child
        child_edge = registry.resolve_edge(root_cred, "acdc")
        assert child_edge is not None
        assert child_edge.target_said == "EChildCredSAID123456789012345678901234"

        # In real usage, we would fetch the child credential by SAID
        # and continue navigation
