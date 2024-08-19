# Boardfarm
<p align=center>
    <img src="BoardFarm.png" width="350"/> <br>
    <img alt="GitHub" src="https://img.shields.io/github/license/lgirdk/boardfarm">
    <img alt="GitHub commit activity (branch)"
    src="https://img.shields.io/github/commit-activity/t/lgirdk/boardfarm/boardfarm3">
    <img alt="GitHub last commit (branch)"
    src="https://img.shields.io/github/last-commit/lgirdk/boardfarm/boardfarm3">
    <img alt="Python Version" src="https://img.shields.io/badge/python-3.11+-blue">
    <a href="https://github.com/psf/black"><img alt="Code style: black"
    src="https://img.shields.io/badge/code%20style-black-000000.svg"></a>
    <a href="https://github.com/astral-sh/ruff"><img alt="Code style: black"
    src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json"></a>
</p> <hr>


## Running the prplOS demo

The code runs on Linux (tested on a few flavours), the system requires docker, docker-compose and python (3.11 or 3.12) to be installed.

TLDR;


```
git clone -b boardfarm3 https://github.com/lgirdk/boardfarm.git
cd boardfarm

# The following is needed to deploy the devices (as docker containers) locally
git clone  https://github.com/lgirdk/raikou-net.git

cd raikou-net/examples/double_hop/
docker-compose up -d
docker ps # make sure the containers are up and running

cd ../../../  # go back to the boardfarm repo root dir

python3.12 -m venv .venv # but will work on 3.11 as well
. .venv/bin/activate

pip install -U pip
pip install -U pip wheel
pip install -e .[dev,test,doc]

boardfarm --board-name  prplos-docker-1 \
          --env-config ./boardfarm3/configs/boardfarm_env_example.json \
          --inventory-config ./boardfarm3/configs/boardfarm_config_example.json \
```
Fedora

Install the latest  [Fedora docker-compose](https://computingforgeeks.com/install-and-use-docker-compose-on-fedora/) as currently the OS package is not up to date.
Make sure the firewall does not block the ports required by boardfarm (you could temporarily stop firewalld if you feel brave).

Ubuntu

Should just work by installing the OS docker and  docker-compose.

RH/CentOS
