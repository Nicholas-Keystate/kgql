"""
Tests for KGQL Wrappers.

Tests the thin wrappers over keripy infrastructure.
These tests use mocks since we don't have actual keripy instances.
"""

import pytest
from unittest.mock import Mock, MagicMock
from dataclasses import dataclass

from kgql.wrappers import RegerWrapper, VerifierWrapper
from kgql.wrappers.reger_wrapper import CredentialResult
from kgql.wrappers.verifier_wrapper import VerificationStatus, VerificationResult


class TestRegerWrapper:
    """Tests for RegerWrapper class."""

    @pytest.fixture
    def mock_reger(self):
        """Create a mock Reger instance."""
        reger = Mock()

        # Mock issus index
        mock_saider = Mock()
        mock_saider.qb64 = "ESAID123"
        reger.issus.getIter.return_value = [mock_saider]

        # Mock subjs index
        reger.subjs.getIter.return_value = [mock_saider]

        # Mock schms index
        reger.schms.getIter.return_value = [mock_saider]

        # Mock creds
        reger.creds.get.return_value = None

        return reger

    def test_by_issuer(self, mock_reger):
        """Test by_issuer delegates to reger.issus.getIter."""
        wrapper = RegerWrapper(mock_reger)

        results = list(wrapper.by_issuer("EAID123"))

        mock_reger.issus.getIter.assert_called_once_with(keys="EAID123")
        assert "ESAID123" in results

    def test_by_subject(self, mock_reger):
        """Test by_subject delegates to reger.subjs.getIter."""
        wrapper = RegerWrapper(mock_reger)

        results = list(wrapper.by_subject("EAID456"))

        mock_reger.subjs.getIter.assert_called_once_with(keys="EAID456")

    def test_by_schema(self, mock_reger):
        """Test by_schema delegates to reger.schms.getIter."""
        wrapper = RegerWrapper(mock_reger)

        results = list(wrapper.by_schema("ESchemaSAID"))

        mock_reger.schms.getIter.assert_called_once_with(keys="ESchemaSAID")

    def test_resolve_not_found(self, mock_reger):
        """Test resolve returns None when credential not found."""
        wrapper = RegerWrapper(mock_reger)

        result = wrapper.resolve("ESAID_NOT_FOUND")

        assert result is None

    def test_count_by_issuer(self, mock_reger):
        """Test count_by_issuer counts results."""
        wrapper = RegerWrapper(mock_reger)

        count = wrapper.count_by_issuer("EAID123")

        assert count == 1

    def test_direct_reger_access(self, mock_reger):
        """Test that underlying reger is accessible."""
        wrapper = RegerWrapper(mock_reger)

        assert wrapper.reger is mock_reger


class TestCredentialResult:
    """Tests for CredentialResult dataclass."""

    def test_from_creder(self):
        """Test creating CredentialResult from Creder."""
        mock_creder = Mock()
        mock_creder.said = "ESAID123"
        mock_creder.issuer = "EAID_ISSUER"
        mock_creder.attrib = {"i": "EAID_SUBJECT"}
        mock_creder.schema = "ESchemaSAID"

        result = CredentialResult.from_creder(mock_creder)

        assert result.said == "ESAID123"
        assert result.issuer == "EAID_ISSUER"
        assert result.subject == "EAID_SUBJECT"
        assert result.schema == "ESchemaSAID"
        assert result.raw is mock_creder


class TestVerifierWrapper:
    """Tests for VerifierWrapper class."""

    @pytest.fixture
    def mock_verifier(self):
        """Create a mock Verifier instance."""
        verifier = Mock()
        return verifier

    @pytest.fixture
    def mock_hby(self):
        """Create a mock Habery instance."""
        hby = Mock()
        hby.kevers = {}
        return hby

    def test_verify_chain_verified(self, mock_verifier, mock_hby):
        """Test verify_chain returns VERIFIED status."""
        mock_result = Mock()
        mock_result.revoked = False
        mock_result.issuer = "EAID_ISSUER"
        mock_result.sn = 5
        mock_result.ksaid = "EKeySAID"
        mock_verifier.verifyChain.return_value = mock_result

        wrapper = VerifierWrapper(mock_verifier, mock_hby)
        result = wrapper.verify_chain("ESAID123")

        assert result.status == VerificationStatus.VERIFIED
        assert result.is_valid is True
        assert result.issuer == "EAID_ISSUER"

    def test_verify_chain_not_found(self, mock_verifier, mock_hby):
        """Test verify_chain returns NOT_FOUND when credential missing."""
        mock_verifier.verifyChain.return_value = None

        wrapper = VerifierWrapper(mock_verifier, mock_hby)
        result = wrapper.verify_chain("ESAID_NOT_FOUND")

        assert result.status == VerificationStatus.NOT_FOUND
        assert result.is_valid is False

    def test_verify_chain_revoked(self, mock_verifier, mock_hby):
        """Test verify_chain returns REVOKED status."""
        mock_result = Mock()
        mock_result.revoked = True
        mock_result.issuer = "EAID_ISSUER"
        mock_verifier.verifyChain.return_value = mock_result

        wrapper = VerifierWrapper(mock_verifier, mock_hby)
        result = wrapper.verify_chain("ESAID123")

        assert result.status == VerificationStatus.REVOKED
        assert result.is_valid is False

    def test_check_delegation_in_chain(self, mock_verifier, mock_hby):
        """Test check_delegation finds delegation chain."""
        # Set up delegation: child -> parent
        child_kever = Mock()
        child_kever.delpre = "EAID_PARENT"

        mock_hby.kevers = {
            "EAID_CHILD": child_kever,
            "EAID_PARENT": Mock(delpre=None)
        }

        wrapper = VerifierWrapper(mock_verifier, mock_hby)
        result = wrapper.check_delegation("EAID_CHILD", "EAID_PARENT")

        assert result.is_delegated is True
        assert "EAID_PARENT" in result.delegation_path
        assert "EAID_CHILD" in result.delegation_path

    def test_check_delegation_not_in_chain(self, mock_verifier, mock_hby):
        """Test check_delegation returns false when not delegated."""
        mock_hby.kevers = {}

        wrapper = VerifierWrapper(mock_verifier, mock_hby)
        result = wrapper.check_delegation("EAID_CHILD", "EAID_PARENT")

        assert result.is_delegated is False
        assert result.delegation_path == []

    def test_direct_verifier_access(self, mock_verifier, mock_hby):
        """Test that underlying verifier is accessible."""
        wrapper = VerifierWrapper(mock_verifier, mock_hby)

        assert wrapper.verifier is mock_verifier


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    def test_is_valid_verified(self):
        """Test is_valid returns True for VERIFIED status."""
        result = VerificationResult(
            status=VerificationStatus.VERIFIED,
            said="ESAID123"
        )
        assert result.is_valid is True

    def test_is_valid_revoked(self):
        """Test is_valid returns False for REVOKED status."""
        result = VerificationResult(
            status=VerificationStatus.REVOKED,
            said="ESAID123"
        )
        assert result.is_valid is False

    def test_is_valid_not_found(self):
        """Test is_valid returns False for NOT_FOUND status."""
        result = VerificationResult(
            status=VerificationStatus.NOT_FOUND,
            said="ESAID123"
        )
        assert result.is_valid is False
