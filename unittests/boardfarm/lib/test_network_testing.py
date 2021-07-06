import pytest

from boardfarm.lib import network_testing


@pytest.mark.parametrize("mac", ["68:02:B8:47:FC:5D", "68:02:B8:47:FC:5e"])
def test_mac_to_eui64_with_valid_mac(mac):
    assert network_testing.mac_to_eui64(mac)


@pytest.mark.parametrize("mac", ["68:02:B8:47:FC", "68:02:B8:47:Fd"])
def test_mac_to_eui64_with_invalid_mac(mac):
    with pytest.raises(TypeError):
        assert network_testing.mac_to_eui64(mac)
