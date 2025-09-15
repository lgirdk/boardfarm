"""MIBs to JSON compiler module."""

import json
import logging
from pathlib import Path
from typing import Any

from pysmi.codegen import JsonCodeGen
from pysmi.compiler import MibCompiler
from pysmi.parser import SmiStarParser
from pysmi.reader import FileReader
from pysmi.searcher import StubSearcher
from pysmi.writer import CallbackWriter

_LOGGER = logging.getLogger(__name__)


class MibsCompiler:
    """MIBs to JSON compiler class."""

    # pylint: disable=too-few-public-methods

    def __init__(self, mibs_dirs: list[str]):
        """Initialize MIBs to JSON compiler.

        :param mibs_dirs: mibs directories
        """
        self._mibs_dict: dict[str, dict] = {}
        self._compile_mibs(mibs_dirs)

    @staticmethod
    def _get_mib_names(mibs_dirs: list[str]) -> list[str]:
        """Get mib names from given directories.

        :param mibs_dirs: mibs directories
        :returns: list of mib name
        """
        mib_names = []
        for path in mibs_dirs:
            mib_names.extend(
                [file.stem for file in Path(path).glob("**/*") if file.is_file()],
            )
        return mib_names

    def _callback(
        self,
        mib_name: str,
        json_data: str,
        _: Any,  # noqa: ANN401
    ) -> None:
        _LOGGER.debug("Processing %s MIB", mib_name)
        for item, value in json.loads(json_data).items():
            # skip item that has no use
            if "oid" in value and "objects" not in value:
                self._mibs_dict[item] = value

    def _compile_mibs(self, mibs_dirs: list[str]) -> None:
        """Compile mibs in the given directories.

        :param mibs_dirs: mibs directories
        """
        mibs_compiler = MibCompiler(
            SmiStarParser(),
            JsonCodeGen(),
            CallbackWriter(self._callback),
        )
        # search for source MIBs here
        mibs_compiler.addSources(*(FileReader(x) for x in mibs_dirs))
        # never recompile MIBs with MACROs
        mibs_compiler.addSearchers(StubSearcher(*JsonCodeGen.baseMibs))
        mibs_compiler.compile(*self._get_mib_names(mibs_dirs))

    def get_mib_oid(self, mib_name: str) -> str:
        """Get OID of given MIB.

        :param mib_name: MIB name
        :returns: OID of the given MIB
        :raises ValueError: when unable to find given mib
        """
        if (
            mib_name in self._mibs_dict
            and self._mibs_dict.get(mib_name, None)
            and "oid" in self._mibs_dict[mib_name]
        ):
            return self._mibs_dict[mib_name]["oid"]
        msg = f"Unable to find OID of {mib_name!r} MIB"
        raise ValueError(msg)
