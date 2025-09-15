# Boardfarm

<p align=center>
    <img src="https://raw.githubusercontent.com/lgirdk/boardfarm/master/docs/images/BoardFarm.png" width="350"/> <br>
    <img alt="GitHub" src="https://img.shields.io/github/license/lgirdk/boardfarm">
    <img alt="GitHub commit activity (branch)"
    src="https://img.shields.io/github/commit-activity/t/lgirdk/boardfarm/master">
    <img alt="GitHub last commit (branch)"
    src="https://img.shields.io/github/last-commit/lgirdk/boardfarm/master">
    <img alt="Python Version" src="https://img.shields.io/badge/python-3.11+-blue">
    <a href="https://github.com/psf/black"><img alt="Code style: black"
    src="https://img.shields.io/badge/code%20style-black-000000.svg"></a>
    <a href="https://github.com/astral-sh/ruff"><img alt="Code style: black"
    src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json"></a>
</p> <hr>

Boardfarm is an open-source IT automation framework purely written in Python (3.11+).

Its primary focus revolves around systems configuration, infrastructure deployment,
and orchestration of advanced IT tasks such as Subscriber Provisioning,
Line Termination System bootups (LTS) or a CPE firmware flash via bootloader.

It empowers its users with the ability to automate and comprehensively
test their devices across a wide range of target environments.

## Motivation

Boardfarm was initially developed at Qualcomm to automate testing of OpenWrt
routers and other embedded devices.

<img src="https://raw.githubusercontent.com/lgirdk/boardfarm/master/docs/images/basic_setup.png" width="600"/>

Over time, the framework evolved to support RDK-B derived boards and IoT devices,
along with the essential OSS and back-office components necessary for simulating
a Telecom Service Providers' environment.

<img src="https://raw.githubusercontent.com/lgirdk/boardfarm/master/docs/images/advance_setup.png" width="600"/>

The operation of a device or the configuration of a server can vary depending
on the specific hardware variant or the infrastructure layout of the deploying
Telecom Operator.

To address this variability, Boardfarm utilizes Pluggy to introduce a hook
structure that enables its users to register customized code through plugins
for each individual infrastructure component.

This structure also enforces a uniform API specification, allowing plugins to
invoke their implementation at any of the predefined checkpoints within the
Boardfarm's execution cycle, offering flexibility and extensibility.

## Features

- Modular Hook definitions enabling users to independently
initiate the bootup/deployment process for each component within the infrastructure,
offering granular control and flexibility.
- Seamless integration with Pytest. Provides easy access to devices along with their
pre-set operations through protocol-specific libraries.
- A versatile connection manager that abstracts physical device connections,
offering a unified set of APIs for RS232, SSH, Telnet, SNMP, and HTTP(s)
communication with the infrastructure.
- A library of device templates (Python ABCs) that can be inherited and customized
for implementing hardware interactions without application or server specific constraints.
- A plugin architecture that enables vendors and OEMs to perform testing and provisioning
on their firmware builds/devices, whether in a predefined production or fully
simulated test environment.
- Integration with Docker/QEMU to simulate various test environments and devices.

## Installation

Run the following command to directly install the package from the repo:

```bash
pip install git+https://github.com/lgirdk/boardfarm.git
```

Run the following command to install from PyPI:

```bash
pip install boardfarm3
```

### Plugin

If you also want to install Boardfarm’s plugins for
DOCSIS ([`boardfarm3-docsis`](https://github.com/lgirdk/boardfarm-docsis)) and Pytest ([`pytest-boardfarm3`](https://github.com/lgirdk/pytest-boardfarm)),
you can install them together using extras:

```bash
pip install "boardfarm3[docsis, pytest]"
```

## Usage

```bash
boardfarm -h
```

This will display help for the framework. Here are all the switches it supports.

```text
usage: boardfarm [-h] --board-name BOARD_NAME --env-config ENV_CONFIG --inventory-config INVENTORY_CONFIG [--legacy] [--skip-boot] [--skip-contingency-checks] [--save-console-logs]

options:
  -h, --help            show this help message and exit
  --board-name BOARD_NAME
                        Board name
  --env-config ENV_CONFIG
                        Environment JSON config file path
  --inventory-config INVENTORY_CONFIG
                        Inventory JSON config file path
  --legacy              allows for devices.<device> obj to be exposed (only for legacy use)
  --skip-boot           Skips the booting process, all devices will be used as they are
  --skip-contingency-checks
                        Skip contingency checks while running tests
  --save-console-logs   Save console logs to the disk
```

## Documentation

For full documentation, including installation, tutorials and architecture overview and how
to run a prplOS demo with  a CPE, ACS, lan, wan devices, please see the following.

## Table of Contents

- [Getting Started](https://github.com/lgirdk/boardfarm/blob/master/docs/getting_started.md)
  - [Installation](https://github.com/lgirdk/boardfarm/blob/master/docs/getting_started.md#installation)
  - [Running an interactive session](https://github.com/lgirdk/boardfarm/blob/master/docs/getting_started.md#running-an-interactive-session)
  - [Booting up a lab environment](https://github.com/lgirdk/boardfarm/blob/master/docs/getting_started.md#booting-up-a-lab-environment)
- [Overview](https://github.com/lgirdk/boardfarm/blob/master/docs/architecture.md#overview)
  - [Architecture](https://github.com/lgirdk/boardfarm/blob/master/docs/architecture.md#architecture)
  - [Hook Specification and Pluggy](https://github.com/lgirdk/boardfarm/blob/master/docs/architecture.md#hooks-specification-and-pluggy)
- [Development (How-to-Guide)](https://github.com/lgirdk/boardfarm/blob/master/docs/development.md)
  - [Writing a Boardfarm plugin](https://github.com/lgirdk/boardfarm/blob/master/docs/development.md#writing-a-boardfarm-plugin)
  - [Writing a Connection class](https://github.com/lgirdk/boardfarm/blob/master/docs/development.md#writing-a-connection-class)
  - [Writing a Device class](https://github.com/lgirdk/boardfarm/blob/master/docs/development.md#writing-a-device-class)
  - [Writing a Use Case](https://github.com/lgirdk/boardfarm/blob/master/docs/development.md#writing-a-use-case)
- [API Reference](https://github.com/lgirdk/boardfarm/blob/master/docs/README.md)

## Changelog

Consult the [CHANGELOG](https://github.com/lgirdk/boardfarm/blob/master/CHANGELOG.md) page for fixes and enhancements of each version.

## Contributing

By making a contribution to this project, I certify that:

1. The contribution was created in whole or in part by me and I have the right to submit it under the open source license indicated in the file; or
2. The contribution is based upon previous work that, to the best of my knowledge, is covered under an appropriate open source license and I have the right under that license to submit that work with modifications, whether created in whole or in part by me, under the same open source license (unless I am permitted to submit under a different license), as indicated in the file; or
3. The contribution was provided directly to me by some other person who certified (a), (b) or (c) and I have not modified it.
4. I understand and agree that this project and the contribution are public and that a record of the contribution (including all personal information I submit with it, including my sign-off) is maintained indefinitely and may be redistributed consistent with this project or the open source license(s) involved.

### Using this Process

In short, you need to include a "Signed-off-by" tag in every patch. "Signed-off-by" is a developer's certification that he or she has the right to submit the patch for inclusion into the project. It is an agreement to the Developer's Certificate of Origin (above). Code without a proper signoff cannot be merged into the mainline.

## License

Distributed under the terms of the Clear BSD License, Boardfarm is free and
open source software.
