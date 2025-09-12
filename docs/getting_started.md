# Getting Started with Boardfarm

## Installation

Depending on your distribution you need some dependencies. On Debian these usually are:

```bash
sudo apt install -y automake libtool libsnmp-dev bison make gcc flex git libglib2.0-dev libfl-dev python3.13-venv
```

It is recommended to install boardfarm in a virtualenv:

```bash
python3.13 -m venv --prompt bf-venv venv
source venv/bin/activate
pip install --upgrade pip wheel
```

### Install Latest Release

```bash
(bf-venv)$ pip install boardfarm
```

### Install Development Build

Start by cloning the repository and installing boardfarm:

```bash
(bf-venv)$ git clone https://github.com/lgirdk/boardfarm
(bf-venv)$ cd boardfarm && pip install -e .[doc,dev,test]
```

> **Note:** For certain boardfarm plugin packages like ```boardfarm[docsis]```, additional tools need to be installed as prerequisite.
> e.g. [DOCSIS bootfile encoder tool](https://github.com/rlaager/docsis)

## Running an interactive session

***Interact*** is a key feature in boardfarm that connects to every device currently deployed in a testbed and exposes a menu-driven CLI to interact with any of those devices. Every console interaction can be preserved in per-device log files.

Boardfarm also provides an interactive **IPython** console that enables a user to execute commands on their devices via their corresponding Python APIs.

### Prerequisites

#### 1. No hardware testbed? Try a virtual environment

In case you don’t have access to a physical testbed, we have a Docker Compose script that spins up a virtual CPE (PrplOS) with a back-office.
This lets you explore interact sessions and device APIs locally on your workstation.

More details can be found in the [raikou-net](https://github.com/lgirdk/raikou-net.git) project if you’re interested in a more complete and in depth virtualized setup.
To quickly deploy a local environment, run:

```bash
# Assuming boardfarm repo is already cloned

cd resources/deploy/prplos
docker compose up -f docker-compose.yaml -d
```

> **Note:** If you want to explore more examples, see `/examples/double_hop` directory in [raikou-net](https://github.com/lgirdk/raikou-net.git)

#### 2. Understanding Inventory and Environment files

Boardfarm needs **two configuration files** to know what to deploy and how to interact with it:

1. **Inventory file** (`inventory.json`)
    - Describes the *devices* in your testbed and how Boardfarm connects to them.
    - Each device entry specifies:
        - **connection type** (serial, ssh, docker exec, etc.)
        - **login credentials / ports / proxies**
        - **role/type** (CPE, WAN, LAN, ACS, DHCP, SIP server, phones, etc.)
        - **options** that customize network behavior (e.g., static IPs, DHCP off/on, DNS, VLAN).
    - Think of it as a **map of your deployed infrastructure** and the “doorways” Boardfarm can use to reach each device.

    **Example (excerpt taken from `boardfarm3/configs/boardfarm_config_example.json`):**

    ```json
    {
        "prplos-docker-1": {
        "devices": [
            {
            "conn_cmd": ["docker exec -it cpe ash"],
            "connection_type": "local_cmd",
            "name": "board",
            "type": "bf_cpe",
            "gui_password": "admin"
            },
            {
            "connection_type": "authenticated_ssh",
            "ipaddr": "localhost",
            "port": 4001,
            "name": "wan",
            "type": "bf_wan",
            "options": "wan-no-dhcp-server, dns-server, wan-static-ip:172.25.1.2/24"
            }
            // ... more devices like lan, acs, phones, provisioner, etc.
        ]
        }
    }
    ```

    In this setup, the board is reached through a local Docker exec command, while WAN, LAN, ACS, and phones are accessed via SSH on different forwarded ports.

    Please see [Inventory Schema](https://github.com/lgirdk/boardfarm/blob/boardfarm3/boardfarm3/configs/boardfarm_inventory_schema.json) for a list of all possible options that can be configured for a device in an Inventory file.

2. **Environment file** (`env.json`)
    - Tells Boardfarm **how to provision the testbed** once devices are connected.
    - Defines higher-level **testbed behavior and requirements**, such as:
        - Which firmware to flash on the board/CPE
        - How DHCP should behave (options, VLANs, DNS)
        - Whether to create multiple LAN/WLAN containers
        - How subscriber configurations look if an LTS (Line Termination System) is present
        - Other provisioning knobs (IPv4/IPv6 mode, model identifiers, etc.)

    **Example (simple):**

    ```json
    {
        "environment_def": {
        "board": {
            "eRouter_Provisioning_mode": "ipv4",
            "model": "prplOS"
        }
        }
    }
    ```

3. **How they work together?**

    Inventory = “what’s there”
    - A catalog of devices, connection methods, roles.

    Environment = “what to do with it”
    - Provisioning rules, firmware flashing, DHCP setup, network topology.

    This tells Boardfarm:

    Connect to all devices listed in the inventory.
    Provision and configure them according to the environment definition.
    Expose them via the interact session (menu + IPython).

### Start an interact session

Now that we have our **environment** and **inventory** files, we can start an interactive session with Boardfarm.

```bash
boardfarm --board-name  prplos-docker-1 \
    --env-config ./boardfarm3/configs/boardfarm_env_example.json \
    --inventory-config ./boardfarm3/configs/boardfarm_config_example.json \
    --skip-boot --legacy
```

> (Optional) --save-console-logs enabled to persist console logs to disk.

This will bring up the Boardfarm Interactive Shell, where all deployed devices are listed and ready for interaction.
![Interact Demo](https://raw.githubusercontent.com/lgirdk/boardfarm/boardfarm3/docs/images/interact.gif)

When you see this menu:

```scss
                BOARDFARM INTERACTIVE SHELL
 ─────────────────────────────────────────────────────────
  Choice   Description                           Consoles
 ─────────────────────────────────────────────────────────
    1      board (bf_cpe)                           1
 ─────────────────────────────────────────────────────────
    2      genieacs (bf_acs)                        1
 ─────────────────────────────────────────────────────────
    3      lan (bf_lan)                             1
 ─────────────────────────────────────────────────────────
    4      lan_phone (bf_phone)                     1
 ─────────────────────────────────────────────────────────
    5      provisioner (bf_dhcp)                    1
 ─────────────────────────────────────────────────────────
    6      sipcenter (bf_kamailio)                  1
 ─────────────────────────────────────────────────────────
    7      wan (bf_wan)                             1
 ─────────────────────────────────────────────────────────
    8      wan_phone (bf_phone)                     1
 ─────────────────────────────────────────────────────────
    p      python interactive shell (ptpython)
 ─────────────────────────────────────────────────────────
    q      exit
 ─────────────────────────────────────────────────────────
Enter your choice: [1/2/3/4/5/6/7/8/p/q]:
```

You have two main options:

- Device console access → enter the number (1–8) beside a device to drop directly into its console session.

- Python interactive shell → enter `p` to open an IPython-like interface (ptpython) where you can import devices and call their Python APIs to run commands or tests programmatically.

This makes it easy to switch between manual console exploration and Python-based automation in the same session.

## Booting up a lab environment

In the previous example, we started Boardfarm with the `--skip-boot` option to quickly attach to already running devices.
If we **remove the `--skip-boot` option**, Boardfarm will not just connect to devices — it will also **provision them based on the environment file** you provided.

Behind the scenes, Boardfarm uses [Pluggy](https://pluggy.readthedocs.io/) (the same plugin system used by pytest).
This means that devices participate in different **lifecycle phases** by implementing specific plugin hooks.

### Boot/Provisioning Hooks

When boot is not skipped, Boardfarm’s plugin manager executes the following hooks in order:

```markdown
boardfarm_server_boot
↓
boardfarm_server_configure
↓
boardfarm_device_boot
↓
boardfarm_device_configure
↓
boardfarm_attached_device_boot
↓
boardfarm_attached_device_configure
```

Each of the above is an actual `@hookspec` that a device class can implement.
If a registered device provides an implementation, it will participate in that phase of booting/provisioning.

- **Server hooks** (`boardfarm_server_*`) → for back office infrastructure or virtualized service containers (e.g., DHCP, DNS, WAN, ACS, SIP servers).
- **Device hooks** (`boardfarm_device_*`) → for the main CPE/board a.k.a DUT.
- **Attached device hooks** (`boardfarm_attached_device_*`) → for LAN/WLAN clients, phones, or other peripherals that can only be provisioned once the main board is up.

This layered boot sequence ensures that back-office infrastructure services are available before devices boot, and devices are provisioned before attached clients are configured.

Please have a look at the boardfarm hooks section for more details.

## TLDR

```bash
git clone -b boardfarm3 https://github.com/lgirdk/boardfarm.git
cd boardfarm

cd resources/deploy/prplos
docker-compose up -f docker-compose.yaml -d
docker ps # make sure the containers are up and running

cd - # go back to the boardfarm repo root dir

python3.13 -m venv --prompt bf-venv venv # will work on 3.11 as well
source venv/bin/activate

pip install -U pip wheel
pip install -e .[dev,test,doc]

boardfarm --board-name  prplos-docker-1 \
          --env-config ./boardfarm3/configs/boardfarm_env_example.json \
          --inventory-config ./boardfarm3/configs/boardfarm_config_example.json \
          --save-console-logs ./logs
```
