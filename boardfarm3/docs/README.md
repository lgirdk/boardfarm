<div id="top_nav">

[|||](# "Toggle sidebar")

# [Boardfarm documentation](# "Go to homepage")

[](search.html "Search")

<div class="searchbox_wrapper">

</div>

</div>

<div class="sphinxsidebar" role="navigation" aria-label="main navigation">

<div class="sphinxsidebarwrapper">

<span class="caption-text">Use Cases</span>

  - [CPE Use Cases](#document-cpe)
  - [Device getters Use Cases](#document-device_getters)
  - [DHCP Use Cases](#document-dhcp)
  - [Networking Use Cases](#document-networking)

</div>

</div>

<div class="document">

<div class="documentwrapper">

<div class="bodywrapper">

<div class="body" role="main">

<div id="boardfarm3-suite-use-cases-documentation" class="section">

# Boardfarm3 suite Use Cases documentation[¶](#boardfarm3-suite-use-cases-documentation "Link to this heading")

<div class="toctree-wrapper compound">

<span id="document-cpe"></span>

<div id="cpe-use-cases" class="section">

## CPE Use Cases[¶](#cpe-use-cases "Link to this heading")

<div id="module-boardfarm3.use_cases.cpe" class="section">

<span id="from-boardfarm3"></span>

### from boardfarm3[¶](#module-boardfarm3.use_cases.cpe "Link to this heading")

Use Cases to check the performance of CPE.

  - <span class="sig-name descname"><span class="pre">board\_reset\_via\_console</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">board</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">CPE</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">None</span></span></span>[¶](#boardfarm3.use_cases.cpe.board_reset_via_console "Link to this definition")
    Reset board via console.

    <div class="admonition hint">

    Hint

    This Use Case implements statements from the test suite such as:

      - Reboot from console.

    </div>

      - Parameters<span class="colon">:</span>
        **board** (*CPE*) – The board instance

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">create\_upnp\_rule</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">device</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">LAN</span></span>*, *<span class="n"><span class="pre">int\_port</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span></span>*, *<span class="n"><span class="pre">ext\_port</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span></span>*, *<span class="n"><span class="pre">protocol</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span></span>*, *<span class="n"><span class="pre">url</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">None</span></span><span class="w"> </span><span class="o"><span class="pre">=</span></span><span class="w"> </span><span class="default_value"><span class="pre">None</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">str</span></span></span>[¶](#boardfarm3.use_cases.cpe.create_upnp_rule "Link to this definition")
    Create UPnP rule on the device.

    <div class="admonition hint">

    Hint

    This Use Case implements statements from the test suite such as:

      - Create UPnP rule through cli.

    </div>

      - Parameters<span class="colon">:</span>

          - **device** (*LAN*) – LAN device instance

          - **int\_port** (*str*) – internal port for UPnP

          - **ext\_port** (*str*) – external port for UPnP

          - **protocol** (*str*) – protocol to be used

          - **url** (*str* *|* *None*) – url to be used

      - Returns<span class="colon">:</span>
        output of UPnP add port command

      - Return type<span class="colon">:</span>
        str

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">delete\_upnp\_rule</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">device</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">LAN</span></span>*, *<span class="n"><span class="pre">ext\_port</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span></span>*, *<span class="n"><span class="pre">protocol</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span></span>*, *<span class="n"><span class="pre">url</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">None</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">str</span></span></span>[¶](#boardfarm3.use_cases.cpe.delete_upnp_rule "Link to this definition")
    Delete UPnP rule on the device.

    <div class="admonition hint">

    Hint

    This Use Case implements statements from the test suite such as:

      - Delete UPnP rule through cli.

    </div>

      - Parameters<span class="colon">:</span>

          - **device** (*LAN*) – LAN device instance

          - **ext\_port** (*str*) – external port for UPnP

          - **protocol** (*str*) – protocol to be used

          - **url** (*str* *|* *None*) – url to be used

      - Returns<span class="colon">:</span>
        output of UPnP delete port command

      - Return type<span class="colon">:</span>
        str

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">disable\_logs</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">board</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">CPE</span></span>*, *<span class="n"><span class="pre">component</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">None</span></span></span>[¶](#boardfarm3.use_cases.cpe.disable_logs "Link to this definition")
    Disable logs for the specified component on the CPE.

    <div class="admonition note">

    Note

      - The component can be one of “voice” and “pacm” for mv2p

      -   - The component can be one of “voice”, “docsis”, “common\_components”,
            “gw”, “vfe”, “vendor\_cbn”, “pacm” for mv1

    </div>

      - Parameters<span class="colon">:</span>

          - **board** (*CPE*) – The board instance

          - **component** (*str*) – The component for which logs have to disabled.

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">enable\_logs</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">board</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">CPE</span></span>*, *<span class="n"><span class="pre">component</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">None</span></span></span>[¶](#boardfarm3.use_cases.cpe.enable_logs "Link to this definition")
    Enable logs for the specified component on the CPE.

    <div class="admonition note">

    Note

      - The component can be one of “voice” and “pacm” for mv2p

      -   - The component can be one of “voice”, “docsis”, “common\_components”,
            “gw”, “vfe”, “vendor\_cbn”, “pacm” for mv1

    </div>

      - Parameters<span class="colon">:</span>

          - **board** (*CPE*) – The board instance

          - **component** (*str*) – The component for which logs have to be enabled.

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">factory\_reset</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">board</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">CPE</span></span>*, *<span class="n"><span class="pre">method</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">None</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">str</span></span><span class="w"> </span><span class="o"><span class="pre">=</span></span><span class="w"> </span><span class="default_value"><span class="pre">None</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">bool</span></span></span>[¶](#boardfarm3.use_cases.cpe.factory_reset "Link to this definition")
    Perform factory reset CPE via given method.

      - Parameters<span class="colon">:</span>

          - **board** (*CPE*) – The board instance.

          - **method** (*None* *|* *str*) – Factory reset method

      - Returns<span class="colon">:</span>
        True on successful factory reset

      - Return type<span class="colon">:</span>
        bool

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">get\_cpe\_provisioning\_mode</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">board</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">CPE</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">str</span></span></span>[¶](#boardfarm3.use_cases.cpe.get_cpe_provisioning_mode "Link to this definition")
    Get the provisioning mode of the board.

      - Parameters<span class="colon">:</span>
        **board** (*CPE*) – The board object, from which the provisioning mode is fetched.

      - Returns<span class="colon">:</span>
        The provisioning mode of the board.

      - Return type<span class="colon">:</span>
        str

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">get\_cpu\_usage</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">board</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">CPE</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">float</span></span></span>[¶](#boardfarm3.use_cases.cpe.get_cpu_usage "Link to this definition")
    Return the current CPU usage of CPE.

    <div class="admonition hint">

    Hint

    This Use Case implements statements from the test suite such as:

      - Return the current CPU usage of CPE.

    </div>

      - Parameters<span class="colon">:</span>
        **board** (*CPE*) – CPE device instance

      - Returns<span class="colon">:</span>
        current CPU usage of the CPE

      - Return type<span class="colon">:</span>
        float

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">get\_memory\_usage</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">board</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">CPE</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">dict</span><span class="p"><span class="pre">\[</span></span><span class="pre">str</span><span class="p"><span class="pre">,</span></span><span class="w"> </span><span class="pre">int</span><span class="p"><span class="pre">\]</span></span></span></span>[¶](#boardfarm3.use_cases.cpe.get_memory_usage "Link to this definition")
    Return the memory usage of CPE.

    <div class="admonition hint">

    Hint

    This Use Case implements statements from the test suite such as:

      - Return the memory usage of CPE.

    </div>

      - Parameters<span class="colon">:</span>
        **board** (*CPE*) – CPE device instance

      - Returns<span class="colon">:</span>
        current memory utilization of the CPE

      - Return type<span class="colon">:</span>
        dict\[str, int\]

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">get\_seconds\_uptime</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">board</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">CPE</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">float</span></span></span>[¶](#boardfarm3.use_cases.cpe.get_seconds_uptime "Link to this definition")
    Return board uptime in seconds.

      - Parameters<span class="colon">:</span>
        **board** (*CPE*) – The board instance

      - Returns<span class="colon">:</span>
        board uptime in seconds

      - Return type<span class="colon">:</span>
        float

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">is\_ntp\_synchronized</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">board</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">CPE</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">bool</span></span></span>[¶](#boardfarm3.use_cases.cpe.is_ntp_synchronized "Link to this definition")
    Get the NTP synchronization status.

    Sample block of the output

    <div class="highlight-python notranslate">

    <div class="highlight">

        [
            {
                "remote": "2001:dead:beef:",
                "refid": ".XFAC.",
                "st": 16,
                "t": "u",
                "when": 65,
                "poll": 18,
                "reach": 0,
                "delay": 0.0,
                "offset": 0.0,
                "jitter": 0.0,
                "state": "*",
            }
        ]

    </div>

    </div>

    This Use Case validates the ‘state’ from the parsed output and returns bool based on the value present in it. The meaning of the indicators are given below,

    ‘\*’ - synchronized candidate ‘\#’ - selected but not synchronized ‘+’ - candidate to be selected \[x/-/ /./None\] - discarded candidate

      - Parameters<span class="colon">:</span>
        **board** (*CPE*) – CPE device instance

      - Raises<span class="colon">:</span>
        **ValueError** – when the output has more than one list item

      - Returns<span class="colon">:</span>
        True if NTP is synchronized, false otherwise

      - Return type<span class="colon">:</span>
        bool

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">is\_tr069\_agent\_running</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">board</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">CPE</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">bool</span></span></span>[¶](#boardfarm3.use_cases.cpe.is_tr069_agent_running "Link to this definition")
    Check if TR069 agent is running or not.

      - Parameters<span class="colon">:</span>
        **board** (*CPE*) – The board instance

      - Returns<span class="colon">:</span>
        True if agent is running, false otherwise

      - Return type<span class="colon">:</span>
        bool

</div>

</div>

<span id="document-device_getters"></span>

<div id="device-getters-use-cases" class="section">

## Device getters Use Cases[¶](#device-getters-use-cases "Link to this heading")

<div id="module-boardfarm3.use_cases.device_getters" class="section">

<span id="from-boardfarm3"></span>

### from boardfarm3[¶](#module-boardfarm3.use_cases.device_getters "Link to this heading")

Device getters use cases.

  - <span class="sig-name descname"><span class="pre">device\_getter</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">device\_type</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">type</span><span class="p"><span class="pre">\[</span></span><span class="pre">T</span><span class="p"><span class="pre">\]</span></span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">T</span></span></span>[¶](#boardfarm3.use_cases.device_getters.device_getter "Link to this definition")
    Provide device of type ‘device\_type’.

      - Parameters<span class="colon">:</span>
        **device\_type** – Type of device to get

      - Returns<span class="colon">:</span>
        Instance of device

      - Raises<span class="colon">:</span>
        **ValueError** – if no device of given type is available or if more than 1 device of given type is available

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">get\_lan\_clients</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">count</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">int</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">list</span><span class="p"><span class="pre">\[</span></span><span class="pre">LAN</span><span class="p"><span class="pre">\]</span></span></span></span>[¶](#boardfarm3.use_cases.device_getters.get_lan_clients "Link to this definition")
    Return a list of LAN clients based on given count.

      - Parameters<span class="colon">:</span>
        **count** (*int*) – number of LAN clients

      - Returns<span class="colon">:</span>
        list of LAN clients

      - Return type<span class="colon">:</span>
        List\[LAN\]

      - Raises<span class="colon">:</span>
        **DeviceNotFound** – if count of LAN devices is invalid

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">get\_wan\_clients</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">count</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">int</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">list</span><span class="p"><span class="pre">\[</span></span><span class="pre">WAN</span><span class="p"><span class="pre">\]</span></span></span></span>[¶](#boardfarm3.use_cases.device_getters.get_wan_clients "Link to this definition")
    Return a list of WAN clients based on given count.

      - Parameters<span class="colon">:</span>
        **count** (*int*) – number of WAN clients

      - Returns<span class="colon">:</span>
        list of WAN clients

      - Return type<span class="colon">:</span>
        List\[WAN\]

      - Raises<span class="colon">:</span>
        **DeviceNotFound** – if count of WAN devices is invalid

</div>

</div>

<span id="document-dhcp"></span>

<div id="dhcp-use-cases" class="section">

## DHCP Use Cases[¶](#dhcp-use-cases "Link to this heading")

<div id="module-boardfarm3.use_cases.dhcp" class="section">

<span id="from-boardfarm3"></span>

### from boardfarm3[¶](#module-boardfarm3.use_cases.dhcp "Link to this heading")

Boardfarm LGI DHCP IPv4 Use Cases.

  - *<span class="pre">class</span><span class="w"> </span>*<span class="sig-name descname"><span class="pre">DHCPTraceData</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">source</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">IPAddresses</span></span>*, *<span class="n"><span class="pre">destination</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">IPAddresses</span></span>*, *<span class="n"><span class="pre">dhcp\_packet</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">dict</span><span class="p"><span class="pre">\[</span></span><span class="pre">str</span><span class="p"><span class="pre">,</span></span><span class="w"> </span><span class="pre">Any</span><span class="p"><span class="pre">\]</span></span></span>*, *<span class="n"><span class="pre">dhcp\_message\_type</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">int</span></span>*<span class="sig-paren">)</span>[¶](#boardfarm3.use_cases.dhcp.DHCPTraceData "Link to this definition")
    Provides a DHCPTraceData data class.

    Holds source, destination, dhcp\_packet and dhcp\_message\_type.

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">configure\_dhcp\_inform</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">client</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">LAN</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">WAN</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">None</span></span></span>[¶](#boardfarm3.use_cases.dhcp.configure_dhcp_inform "Link to this definition")
    Configure dhclient.conf to send DHCPINFORM messages.

      - Parameters<span class="colon">:</span>
        **client** (*LAN* *|* *WAN*) – Device where dhclient.conf needs to be configured for DHCPINFORM,=,

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">configure\_dhcp\_option125</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">client</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">LAN</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">WAN</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">None</span></span></span>[¶](#boardfarm3.use_cases.dhcp.configure_dhcp_option125 "Link to this definition")
    Configure device’s vendor-specific suboptions in DHCP option 125.

    This function modifies the device’s dhclient.conf.

      - Parameters<span class="colon">:</span>
        **client** (*LAN* *|* *WAN*) – Linux device to be configured.

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">get\_all\_dhcp\_options</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">packet</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n">[<span class="pre">DHCPTraceData</span>](index.html#boardfarm3.use_cases.dhcp.DHCPTraceData "boardfarm3.use_cases.dhcp.DHCPTraceData")</span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">dict</span><span class="p"><span class="pre">\[</span></span><span class="pre">str</span><span class="p"><span class="pre">,</span></span><span class="w"> </span><span class="pre">Any</span><span class="p"><span class="pre">\]</span></span></span></span>[¶](#boardfarm3.use_cases.dhcp.get_all_dhcp_options "Link to this definition")
    Get all the DHCP options in a DHCP packet.

      - Parameters<span class="colon">:</span>
        **packet** ([*DHCPTraceData*](index.html#boardfarm3.use_cases.dhcp.DHCPTraceData "boardfarm3.use_cases.dhcp.DHCPTraceData")) – desired packet from DHCP trace (only one packet)

      - Returns<span class="colon">:</span>
        all the DHCP options

      - Return type<span class="colon">:</span>
        RecursiveDict

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">get\_all\_dhcpv6\_options</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">packet</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">DHCPV6TraceData</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">DHCPV6Options</span></span></span>[¶](#boardfarm3.use_cases.dhcp.get_all_dhcpv6_options "Link to this definition")
    Get all the DHCPv6 options in a DHCPv6 packet.

    <div class="admonition hint">

    Hint

    This Use Case implements statements from the test suite such as:

      - DHCPv6 includes the \[\] option

    </div>

      - Parameters<span class="colon">:</span>
        **packet** (*DHCPV6TraceData*) – desired packet from DHCPv6 trace (only one packet)

      - Returns<span class="colon">:</span>
        all the DHCPv6 options

      - Return type<span class="colon">:</span>
        DHCPV6Options

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">get\_dhcp\_option\_details</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">packet</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n">[<span class="pre">DHCPTraceData</span>](index.html#boardfarm3.use_cases.dhcp.DHCPTraceData "boardfarm3.use_cases.dhcp.DHCPTraceData")</span>*, *<span class="n"><span class="pre">option</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">int</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">dict</span><span class="p"><span class="pre">\[</span></span><span class="pre">str</span><span class="p"><span class="pre">,</span></span><span class="w"> </span><span class="pre">Any</span><span class="p"><span class="pre">\]</span></span></span></span>[¶](#boardfarm3.use_cases.dhcp.get_dhcp_option_details "Link to this definition")
    Get all required option details when option is provided.

    <div class="admonition hint">

    Hint

    This Use Case implements statements from the test suite such as:

      - Verify packet capture has option

      - Verify \[\] is present in DHCP \[\] message

      - Verify all the Mandatory\_Fields are available in DHCP message

    </div>

      - Parameters<span class="colon">:</span>

          - **packet** ([*DHCPTraceData*](index.html#boardfarm3.use_cases.dhcp.DHCPTraceData "boardfarm3.use_cases.dhcp.DHCPTraceData")) – the packet data structure

          - **option** (*int*) – DHCP option

      - Raises<span class="colon">:</span>
        **UseCaseFailure** – on failing to find the option

      - Returns<span class="colon">:</span>
        option Dict along with suboptions

      - Return type<span class="colon">:</span>
        RecursiveDict

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">get\_dhcp\_packet\_by\_message</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">trace</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">list</span><span class="p"><span class="pre">\[</span></span>[<span class="pre">DHCPTraceData</span>](index.html#boardfarm3.use_cases.dhcp.DHCPTraceData "boardfarm3.use_cases.dhcp.DHCPTraceData")<span class="p"><span class="pre">\]</span></span></span>*, *<span class="n"><span class="pre">message\_type</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">list</span><span class="p"><span class="pre">\[</span></span>[<span class="pre">DHCPTraceData</span>](index.html#boardfarm3.use_cases.dhcp.DHCPTraceData "boardfarm3.use_cases.dhcp.DHCPTraceData")<span class="p"><span class="pre">\]</span></span></span></span>[¶](#boardfarm3.use_cases.dhcp.get_dhcp_packet_by_message "Link to this definition")
    Get the DHCP packets for the particular message from the pcap file.

    <div class="admonition hint">

    Hint

    This Use Case implements statements from the test suite such as:

      - Following messages are exchanged

      - Discover, Offer, Request and Ack messages

      - DHCP messages are exchanged

    </div>

      - Parameters<span class="colon">:</span>

          - **trace** (*List\[*[*DHCPTraceData*](index.html#boardfarm3.use_cases.dhcp.DHCPTraceData "boardfarm3.use_cases.dhcp.DHCPTraceData")*\]*) – sequence of DHCP packets filtered from captured pcap file and stored in DHCPTraceData

          - **message\_type** (*str*) –

            DHCP message according to RFC2132 and could be any of:

              - DHCPDISCOVER,

              - DHCPOFFER,

              - DHCPREQUEST,

              - DHCPDECLINE,

              - DHCPACK,

              - DHCPACK,

              - DHCPRELEASE,

              - DHCPINFORM

      - Returns<span class="colon">:</span>
        Sequence of DHCP packets filtered with the message type

      - Return type<span class="colon">:</span>
        List\[[DHCPTraceData](index.html#boardfarm3.use_cases.dhcp.DHCPTraceData "boardfarm3.use_cases.dhcp.DHCPTraceData")\]

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">get\_dhcp\_suboption\_details</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">packet</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n">[<span class="pre">DHCPTraceData</span>](index.html#boardfarm3.use_cases.dhcp.DHCPTraceData "boardfarm3.use_cases.dhcp.DHCPTraceData")</span>*, *<span class="n"><span class="pre">option</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">int</span></span>*, *<span class="n"><span class="pre">suboption</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">int</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">dict</span><span class="p"><span class="pre">\[</span></span><span class="pre">str</span><span class="p"><span class="pre">,</span></span><span class="w"> </span><span class="pre">Any</span><span class="p"><span class="pre">\]</span></span></span></span>[¶](#boardfarm3.use_cases.dhcp.get_dhcp_suboption_details "Link to this definition")
    Get all required sub option details when option & sub option are provided.

    <div class="admonition hint">

    Hint

    This Use Case implements statements from the test suite such as:

      - DHCP option \[\] suboptions

      - Verify \[\] suboptions are present in DHCP

    </div>

      - Parameters<span class="colon">:</span>

          - **packet** ([*DHCPTraceData*](index.html#boardfarm3.use_cases.dhcp.DHCPTraceData "boardfarm3.use_cases.dhcp.DHCPTraceData")) – the packet data structure

          - **option** (*int*) – DHCP option

          - **suboption** (*int*) – DHCP sub option

      - Raises<span class="colon">:</span>
        **UseCaseFailure** – on failing to find the suboption

      - Returns<span class="colon">:</span>
        suboption dictionary

      - Return type<span class="colon">:</span>
        RecursiveDict

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">get\_dhcpv6\_packet\_by\_message</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">trace</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">list</span><span class="p"><span class="pre">\[</span></span><span class="pre">DHCPV6TraceData</span><span class="p"><span class="pre">\]</span></span></span>*, *<span class="n"><span class="pre">message\_type</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">list</span><span class="p"><span class="pre">\[</span></span><span class="pre">DHCPV6TraceData</span><span class="p"><span class="pre">\]</span></span></span></span>[¶](#boardfarm3.use_cases.dhcp.get_dhcpv6_packet_by_message "Link to this definition")
    Get the DHCPv6 packets for the particular message from the pcap file.

    <div class="admonition hint">

    Hint

    This Use Case implements statements from the test suite such as:

      - Following messages are exchanged DHCPv6

      - Discover, Offer, Request and Ack DHCPv6 messages

      - DHCPv6 messages are exchanged

    </div>

      - Parameters<span class="colon">:</span>

          - **trace** (*List\[DHCPV6TraceData\]*) – sequence of DHCPv6 packets filtered from captured pcap file and stored in DHCPV6TraceData

          - **message\_type** (*str*) –

            DHCP message according to RFC3315 and could be any of:

              - SOLICIT,

              - ADVERTISE,

              - REQUEST,

              - CONFIRM,

              - RENEW,

              - REBIND,

              - REPLY,

              - RELEASE,

              - DECLINE,

              - RECONFIGURE,

              - INFORMATION-REQUEST,

              - RELAY-FORW,

              - RELAY-REPL

      - Returns<span class="colon">:</span>
        Sequence of DHCPv6 packets filtered with the message type

      - Return type<span class="colon">:</span>
        List\[DHCPV6TraceData\]

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">parse\_dhcp\_trace</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">on\_which\_device</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">LAN</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">WAN</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">Provisioner</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">LTS</span></span>*, *<span class="n"><span class="pre">fname</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span></span>*, *<span class="n"><span class="pre">timeout</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">int</span></span><span class="w"> </span><span class="o"><span class="pre">=</span></span><span class="w"> </span><span class="default_value"><span class="pre">30</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">list</span><span class="p"><span class="pre">\[</span></span>[<span class="pre">DHCPTraceData</span>](index.html#boardfarm3.use_cases.dhcp.DHCPTraceData "boardfarm3.use_cases.dhcp.DHCPTraceData")<span class="p"><span class="pre">\]</span></span></span></span>[¶](#boardfarm3.use_cases.dhcp.parse_dhcp_trace "Link to this definition")
    Read and filter the DHCP packets from the pcap file and returns the DHCP packets.

    <div class="admonition hint">

    Hint

    This Use Case implements statements from the test suite such as:

      - Verify from the packet capture

      - Verify that the following messages are exchanged

      - Check that \[\] messages are exchanged

    </div>

      - Parameters<span class="colon">:</span>

          - **on\_which\_device** (*LAN* *|* *WAN* *|* *Provisioner* *|* *CMTS*) – Object of the device class where tcpdump is captured

          - **fname** (*str*) – Name of the captured pcap file

          - **timeout** (*int*) – time out for `tshark read` to be executed, defaults to 30

      - Raises<span class="colon">:</span>
        **UseCaseFailure** – on DHCP parse issue

      - Returns<span class="colon">:</span>
        Sequence of DHCP packets filtered from captured pcap file

      - Return type<span class="colon">:</span>
        List\[[DHCPTraceData](index.html#boardfarm3.use_cases.dhcp.DHCPTraceData "boardfarm3.use_cases.dhcp.DHCPTraceData")\]

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">parse\_dhcpv6\_trace</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">on\_which\_device</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">LAN</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">WAN</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">Provisioner</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">LTS</span></span>*, *<span class="n"><span class="pre">fname</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span></span>*, *<span class="n"><span class="pre">timeout</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">int</span></span><span class="w"> </span><span class="o"><span class="pre">=</span></span><span class="w"> </span><span class="default_value"><span class="pre">30</span></span>*, *<span class="n"><span class="pre">additional\_args</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span></span><span class="w"> </span><span class="o"><span class="pre">=</span></span><span class="w"> </span><span class="default_value"><span class="pre">'dhcpv6'</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">list</span><span class="p"><span class="pre">\[</span></span><span class="pre">DHCPV6TraceData</span><span class="p"><span class="pre">\]</span></span></span></span>[¶](#boardfarm3.use_cases.dhcp.parse_dhcpv6_trace "Link to this definition")
    Read and filter the DHCPv6 packets from the pcap file.

    <div class="admonition hint">

    Hint

    This Use Case implements statements from the test suite such as:

      - Check that the following messages are exchanged \[\] DHCPv6

      - Verify from the packet capture that DHCPv6

    </div>

      - Parameters<span class="colon">:</span>

          - **on\_which\_device** (*LAN* *|* *WAN* *|* *Provisioner* *|* *CMTS*) – Object of the device class where tcpdump is captured

          - **fname** (*str*) – Name of the captured pcap file

          - **timeout** (*int*) – time out for `tshark` command to be executed, defaults to 30

          - **additional\_args** (*str*) – additional arguments for tshark command to display filtered output, defaults to dhcpv6

      - Raises<span class="colon">:</span>
        **UseCaseFailure** – on failure to parse DHCPv6 data

      - Returns<span class="colon">:</span>
        sequence of DHCPv6 packets filtered from captured pcap file

      - Return type<span class="colon">:</span>
        List\[DHCPV6TraceData\]

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">remove\_dhcp\_inform\_config</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">client</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">LAN</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">WAN</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">None</span></span></span>[¶](#boardfarm3.use_cases.dhcp.remove_dhcp_inform_config "Link to this definition")
    Remove the DHCPINFORM related configuration on dhclient.conf.

      - Parameters<span class="colon">:</span>
        **client** (*LAN* *|* *WAN*) – Device from where the configuration needs to be removed.

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">remove\_dhcp\_option125</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">client</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">LAN</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">WAN</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">None</span></span></span>[¶](#boardfarm3.use_cases.dhcp.remove_dhcp_option125 "Link to this definition")
    Remove the information in DHCP option 125.

    This function modifies the Linux device’s dhclient.conf.

      - Parameters<span class="colon">:</span>
        **client** (*LAN* *|* *WAN*) – Linux device to be configured.

</div>

</div>

<span id="document-networking"></span>

<div id="networking-use-cases" class="section">

## Networking Use Cases[¶](#networking-use-cases "Link to this heading")

<div id="module-boardfarm3.use_cases.networking" class="section">

<span id="from-boardfarm3"></span>

### from boardfarm3[¶](#module-boardfarm3.use_cases.networking "Link to this heading")

Common Networking use cases.

  - <span class="sig-name descname"><span class="pre">http\_get</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">device</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">LAN</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">WAN</span></span>*, *<span class="n"><span class="pre">url</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span></span>*, *<span class="n"><span class="pre">timeout</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">int</span></span><span class="w"> </span><span class="o"><span class="pre">=</span></span><span class="w"> </span><span class="default_value"><span class="pre">20</span></span>*, *<span class="n"><span class="pre">options</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span></span><span class="w"> </span><span class="o"><span class="pre">=</span></span><span class="w"> </span><span class="default_value"><span class="pre">''</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">HTTPResult</span></span></span>[¶](#boardfarm3.use_cases.networking.http_get "Link to this definition")
    Check if the given HTTP server is running.

    This Use Case executes a curl command with a given timeout from the given client. The destination is specified by the url parameter

    <div class="admonition hint">

    Hint

    This Use Case implements statements from the test suite such as:

      - Verify HTTP server is accessible from \[\] via erouter IP

      - Verify that the HTTP server running on the client is accessible

      - Try to connect to the HTTP server from \[\] client

    </div>

      - Parameters<span class="colon">:</span>

          - **device** (*LAN* *|* *WAN*) – the device from where HTTP response to get

          - **url** (*str*) – URL to get the response

          - **timeout** (*int*) – connection timeout for the curl command in seconds, default 20

          - **options** (*str*) – additional options to pass to the curl command, defaults to “”

      - Returns<span class="colon">:</span>
        parsed HTTP get response

      - Return type<span class="colon">:</span>
        HTTPResult

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">ping</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">device</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">LAN</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">WLAN</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">WAN</span></span>*, *<span class="n"><span class="pre">ping\_ip</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span></span>*, *<span class="n"><span class="pre">ping\_count</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">int</span></span><span class="w"> </span><span class="o"><span class="pre">=</span></span><span class="w"> </span><span class="default_value"><span class="pre">4</span></span>*, *<span class="n"><span class="pre">ping\_interface</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">None</span></span><span class="w"> </span><span class="o"><span class="pre">=</span></span><span class="w"> </span><span class="default_value"><span class="pre">None</span></span>*, *<span class="n"><span class="pre">timeout</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">int</span></span><span class="w"> </span><span class="o"><span class="pre">=</span></span><span class="w"> </span><span class="default_value"><span class="pre">50</span></span>*, *<span class="n"><span class="pre">json\_output</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">bool</span></span><span class="w"> </span><span class="o"><span class="pre">=</span></span><span class="w"> </span><span class="default_value"><span class="pre">False</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">bool</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">dict</span><span class="p"><span class="pre">\[</span></span><span class="pre">str</span><span class="p"><span class="pre">,</span></span><span class="w"> </span><span class="pre">Any</span><span class="p"><span class="pre">\]</span></span></span></span>[¶](#boardfarm3.use_cases.networking.ping "Link to this definition")
    Ping remote host ip.

    Return True if ping has 0% loss or parsed output in JSON if json\_output=True flag is provided.

      - Parameters<span class="colon">:</span>

          - **device** (*LAN*) – device on which ping is performed

          - **ping\_ip** (*str*) – ip to ping

          - **ping\_count** (*int*) – number of concurrent pings, defaults to 4

          - **ping\_interface** (*str* *|* *None*) – ping via interface, defaults to None

          - **timeout** (*int*) – timeout, defaults to 50

          - **json\_output** (*bool*) – True if ping output in dictionary format else False, defaults to False

      - Returns<span class="colon">:</span>
        bool or dict of ping output

      - Return type<span class="colon">:</span>
        bool | dict\[str, Any\]

<!-- end list -->

  - <span class="sig-name descname"><span class="pre">start\_http\_server</span></span><span class="sig-paren">(</span>*<span class="n"><span class="pre">device</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">LAN</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">WAN</span></span>*, *<span class="n"><span class="pre">port</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">int</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">str</span></span>*, *<span class="n"><span class="pre">ip\_version</span></span><span class="p"><span class="pre">:</span></span><span class="w"> </span><span class="n"><span class="pre">str</span><span class="w"> </span><span class="p"><span class="pre">|</span></span><span class="w"> </span><span class="pre">int</span></span>*<span class="sig-paren">)</span> <span class="sig-return"><span class="sig-return-icon">→</span> <span class="sig-return-typehint"><span class="pre">Generator</span></span></span>[¶](#boardfarm3.use_cases.networking.start_http_server "Link to this definition")
    Start http server on given client.

    <div class="admonition hint">

    Hint

    This Use Case implements statements from the test suite such as:

      - Start the HTTP server on the \[\] client

    </div>

      - Parameters<span class="colon">:</span>

          - **device** (*LAN* *|* *WAN*) – device on which server will start

          - **port** (*int* *|* *str*) – port on which the server listen for incomming connections

          - **ip\_version** (*str* *|* *int*) – ip version of server values can strictly be 4 or 6

      - Raises<span class="colon">:</span>
        **ValueError** – wrong ip\_version value is given in api call

      - Yield<span class="colon">:</span>
        PID of the http server process

</div>

</div>

</div>

</div>

<div class="clearer">

</div>

</div>

</div>

</div>

<div id="show_right_sidebar">

[<span class="icon">\<</span><span>Page contents</span>](#)

</div>

<div id="right_sidebar">

[<span class="icon">\></span><span>Page contents:</span>](#)

<div class="page_toc">

<span class="caption-text">Use Cases</span>

  - [CPE Use Cases](#document-cpe)
      - [from boardfarm3](index.html#module-boardfarm3.use_cases.cpe)
  - [Device getters Use Cases](#document-device_getters)
      - [from boardfarm3](index.html#module-boardfarm3.use_cases.device_getters)
  - [DHCP Use Cases](#document-dhcp)
      - [from boardfarm3](index.html#module-boardfarm3.use_cases.dhcp)
  - [Networking Use Cases](#document-networking)
      - [from boardfarm3](index.html#module-boardfarm3.use_cases.networking)

</div>

</div>

<div class="clearer">

</div>

</div>

<div class="button_nav_wrapper">

<div class="button_nav">

<div class="left">

</div>

<div class="right">

</div>

</div>

</div>

<div class="footer" role="contentinfo">

© Copyright 2025, Various. Created using [Sphinx](https://www.sphinx-doc.org/) 7.3.7.

</div>

Styled using the [Piccolo Theme](https://github.com/piccolo-orm/piccolo_theme)
