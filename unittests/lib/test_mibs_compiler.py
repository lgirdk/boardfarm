"""Unit tests for the Boardfarm Mib Compiler module."""

from pathlib import Path

import pytest

from boardfarm3.lib.mibs_compiler import MibsCompiler

_TEST_MIBS_DIR = Path(__file__).parents[1] / "testdata" / "mibs"


@pytest.fixture(scope="module", name="mibs_compiler")
def mibs_compiler_value() -> MibsCompiler:
    """Fixture for MibsCompiler class.

    :return: MibsCompiler
    """
    return MibsCompiler([_TEST_MIBS_DIR])


def test_get_mib_oid(mibs_compiler: MibsCompiler) -> None:
    """Verify that oid can be retrieved from MIB.

    :param mibs_compiler: MibsCompiler
    :type mibs_compiler: MibsCompiler
    """
    test_oid = mibs_compiler.get_mib_oid("sysDescr")
    assert test_oid == "1.3.6.1.2.1.1.1"


def test_exception_raises(mibs_compiler: MibsCompiler) -> None:
    """Verify that ValueError raises when unable to find given OID.

    :param mibs_compiler: MibsCompiler
    :type mibs_compiler: MibsCompiler
    """
    mib_name = "dot11MACAddress"
    with pytest.raises(ValueError, match=f"Unable to find OID of '{mib_name}' MIB"):
        mibs_compiler.get_mib_oid(mib_name)
