from typing import Dict, List, Optional, Union

import pytest

from boardfarm.devices.base_devices.acs_template import (
    AcsTemplate,
    GpvInput,
    GpvResponse,
    SpvInput,
)


def test_cannot_instantiate_abc_acs():
    with pytest.raises(TypeError) as err:
        acs = AcsTemplate()  # noqa: F841
        print(str(err.value))
    assert "Can't instantiate abstract class AcsTemplate" in str(err.value)


def test_cannot_instantiate_derived_acs_missing_model():
    with pytest.raises(TypeError) as err:
        # missing "model" property definition
        class MyAcs(AcsTemplate):
            def __init__(self, *args, **kwargs) -> None:
                pass

            def connect(self, *args, **kwargs) -> None:
                pass

            def GPV(
                self,
                param: GpvInput,
                timeout: Optional[int] = None,
                cpe_id: Optional[str] = None,
            ) -> GpvResponse:
                pass

            def SPV(
                self,
                param_value: SpvInput,
                timeout: Optional[int] = None,
                cpe_id: Optional[str] = None,
            ) -> int:
                pass

        acs = MyAcs()  # noqa: F841
    assert "Can't instantiate abstract class MyAcs" in str(err.value)


def test_cannot_instantiate_derived_acs_incorrect_signature():
    with pytest.raises(TypeError) as err:
        # missing "model" property definition
        class MyAcs(AcsTemplate):
            model = "unittest"

            def __init__(self, *args, **kwargs) -> None:
                pass

            def connect(self, *args, **kwargs) -> None:
                pass

            def GPV(self, parameter: GpvInput):
                pass

            def SPV(
                self,
                cpe_id: Optional[str],
                key_value: SpvInput,
            ) -> int:
                pass

        acs = MyAcs()  # noqa: F841
    assert (
        "Abstract method 'GPV'  not implemented with correct signature in 'MyAcs'"
        in str(err.value)
    )


def test_can_instantiate_derived_acs_with_correct_structure():
    class MyAcs(AcsTemplate):
        model = "unittest"

        def __init__(self, *args, **kwargs) -> None:
            pass

        def connect(self, *args, **kwargs) -> None:
            pass

        def GPV(
            self,
            param: GpvInput,
            timeout: Optional[int] = None,
            cpe_id: Optional[str] = None,
        ) -> GpvResponse:
            pass

        def SPV(
            self,
            param_value: SpvInput,
            timeout: Optional[int] = None,
            cpe_id: Optional[str] = None,
        ) -> int:
            pass

    acs = MyAcs()  # noqa: F841
