from typing import Dict, List

import pytest

from boardfarm.devices.base_devices.acs_template import AcsTemplate, SpvStructure


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

            def GPV(self, cpe_id: str, parameter: str) -> None:
                pass

            def SPV(self, cpe_id: str, key_value: SpvStructure) -> int:
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

            # cpe_id: str param should be present
            def GPV(self, parameter: str):
                pass

            def SPV(self, cpe_id: str, key_value: SpvStructure) -> int:
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

        def GPV(self, cpe_id: str, parameter: str) -> None:
            pass

        def SPV(self, cpe_id: str, key_value: SpvStructure) -> int:
            pass

    acs = MyAcs()  # noqa: F841
