"""Boardfarm API plugin: hookspec registration and native config resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pluggy import HookimplMarker

from boardfarm3 import hookimpl
from boardfarm3.api import hookspecs
from boardfarm3.lib.boardfarm_config import select_inventory

# Create hookimpl marker for the boardfarm_api entrypoint group
hookimpl_api = HookimplMarker("boardfarm_api")

if TYPE_CHECKING:
    from argparse import Namespace

    from pluggy import PluginManager

    from boardfarm3.api.routers import RouterBundle
    from boardfarm3.lib.boardfarm_config import BoardfarmConfig


@hookimpl
def boardfarm_add_hookspecs(plugin_manager: PluginManager) -> None:
    """Add the API hookspecs to the plugin manager.

    :param plugin_manager: plugin manager
    :type plugin_manager: PluginManager
    """
    plugin_manager.add_hookspecs(hookspecs)


@hookimpl(trylast=True)
def boardfarm_api_resolve_config(
    payload: dict[str, Any],
    cmdline_args: Namespace,
    plugin_manager: PluginManager,
) -> BoardfarmConfig:
    """Resolve a native payload of the form ``{"inventory": ..., "env": ...}``.

    Registered ``trylast`` so any plugin handling a front-end specific format
    takes precedence.

    :param payload: opaque session payload
    :type payload: dict[str, Any]
    :param cmdline_args: synthesised boardfarm command line arguments
    :type cmdline_args: Namespace
    :param plugin_manager: plugin manager instance
    :type plugin_manager: PluginManager
    :return: parsed boardfarm config
    :rtype: BoardfarmConfig
    """
    inventory_config = select_inventory(payload["inventory"], cmdline_args.board_name)
    return plugin_manager.hook.boardfarm_parse_config(  # type: ignore[no-any-return]
        cmdline_args=cmdline_args,
        inventory_config=inventory_config,
        env_config=payload["env"],
    )


@hookimpl_api
def boardfarm_add_api_routers() -> list[RouterBundle]:  # pylint: disable=too-many-locals
    """Return the core boardfarm API routers, generated from template ABCs.

    :return: one RouterBundle for the ``core`` namespace
    :rtype: list[RouterBundle]
    """
    from boardfarm3.api.routers import (  # pylint: disable=import-outside-toplevel
        RouterBundle,
    )
    from boardfarm3.api.routers._generator import (  # pylint: disable=import-outside-toplevel
        TemplateMount,
        generate_template_routers,
    )
    from boardfarm3.api.routers._usecase_generator import (  # pylint: disable=import-outside-toplevel
        generate_usecase_routers,
    )
    from boardfarm3.templates.acs import ACS  # pylint: disable=import-outside-toplevel
    from boardfarm3.templates.core_router import (  # pylint: disable=import-outside-toplevel
        CoreRouter,
    )
    from boardfarm3.templates.cpe import (  # pylint: disable=import-outside-toplevel
        CPE,
        CPEHW,
        CPESW,
    )
    from boardfarm3.templates.lan import LAN  # pylint: disable=import-outside-toplevel
    from boardfarm3.templates.ntu.ntu import (  # pylint: disable=import-outside-toplevel
        NTU,
    )
    from boardfarm3.templates.provisioner import (  # pylint: disable=import-outside-toplevel
        Provisioner,
    )
    from boardfarm3.templates.sip_phone import (  # pylint: disable=import-outside-toplevel
        SIPPhone,
    )
    from boardfarm3.templates.sip_server import (  # pylint: disable=import-outside-toplevel
        SIPServer,
    )
    from boardfarm3.templates.wan import WAN  # pylint: disable=import-outside-toplevel
    from boardfarm3.templates.wlan import (  # pylint: disable=import-outside-toplevel
        WLAN,
    )
    from boardfarm3.use_cases import (  # pylint: disable=import-outside-toplevel
        cpe as uc_cpe,
    )
    from boardfarm3.use_cases import (  # pylint: disable=import-outside-toplevel
        dhcp as uc_dhcp,
    )
    from boardfarm3.use_cases import (  # pylint: disable=import-outside-toplevel
        iperf as uc_iperf,
    )
    from boardfarm3.use_cases import (  # pylint: disable=import-outside-toplevel
        networking as uc_networking,
    )
    from boardfarm3.use_cases import (  # pylint: disable=import-outside-toplevel
        voice as uc_voice,
    )
    from boardfarm3.use_cases import (  # pylint: disable=import-outside-toplevel
        wifi as uc_wifi,
    )

    templates: list[type | TemplateMount] = [
        LAN,
        WAN,
        WLAN,
        ACS,
        Provisioner,
        SIPServer,
        SIPPhone,
        CoreRouter,
        TemplateMount("cpe", CPE, CPESW, "sw"),
        TemplateMount("cpe", CPE, CPEHW, "hw"),
        TemplateMount("ntu", NTU, CPESW, "sw"),
        TemplateMount("ntu", NTU, CPEHW, "hw"),
    ]
    routers, skipped = generate_template_routers(templates)
    uc_routers, uc_skipped = generate_usecase_routers(
        [uc_cpe, uc_dhcp, uc_networking, uc_wifi, uc_iperf, uc_voice]
    )
    return [
        RouterBundle(
            namespace="core",
            routers=[*routers, *uc_routers],
            skipped=[*skipped, *uc_skipped],
        )
    ]
