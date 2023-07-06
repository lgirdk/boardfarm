# How to write device classes?

- All device classes are located under the devices folder. Eg. LAN, WLAN
- All base devices are located under devices\base_devices. Eg. LinuxDevice
- A device class could be inherited from the base device and a preferred device template.
- A template consists of abstract methods, which have to be used.
- In addition, functions other than the template could be added to the device class.
- A device class could implement the required hooks. To know more about the hooks go to #link to hooks

## Sample device class

```python
"""Demo WAN device module."""

import logging
from typing import Any, Optional, Union
from boardfarm3.templates.wan import WAN


from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import LinuxDevice


_LOGGER = logging.getLogger(__name__)


class DemoWAN(LinuxDevice,WAN):
    """Boardfarm WAN device."""

    @hookimpl
    def boardfarm_server_boot(self) -> None:
        """Boardfarm hook implementation to boot WAN device.

        :raises DeviceBootFailure: if WAN fails to connect
        """
        _LOGGER.info(
            "Booting %s(%s) device", self.device_name, self.device_type
        )
        self._connect()

    @hookimpl
    def boardfarm_shutdown_device(self) -> None:
        """Boardfarm hook implementation to shutdown WAN device."""
        _LOGGER.info(
            "Shutdown %s(%s) device", self.device_name, self.device_type
        )
        self._disconnect()

    @property
    def iface_dut(self) -> str:
        """Name of the interface that is connected to DUT."""
        return "eth1"

    def ping(  # noqa: PLR0913
        self,
        ping_ip: str,
        ping_count: int = 4,
        ping_interface: Optional[str] = None,
        options: str = "",
        timeout: int = 50,
        json_output: bool = False,
    ) -> Union[bool, dict[str, Any]]:
        """Ping remote host.

        Return True if ping has 0% loss
        or parsed output in JSON if json_output=True flag is provided.

        :param ping_ip: ping ip
        :param ping_count: number of ping, defaults to 4
        :param ping_interface: ping via interface, defaults to None
        :param options: extra ping options, defaults to ""
        :param timeout: timeout, defaults to 50
        :param json_output: return ping output in dictionary format, defaults to False
        :return: ping output
        """
        return super().ping(
            ping_ip,
            ping_count,
            ping_interface,
            options,
            timeout,
            json_output,
        )
```
