"""Provide Dockerfile data."""
from io import BytesIO
from pathlib import Path

image_mappings = {
    "bft:orchestrator": "alpine_orchestrator",
    # this is the base docker file
    "bft:node": "Dockerfile",
    "bft:router": "alpine_orchestrator",
    "bft:wan": "debian_wan",
    "bft:lan": "debian_lan",
    "bft:dns": "debian_dns",
    "bft:fxs": "debian_fxs",
}


def get_dockerfile(image_name):
    """Return bytes stream dockerfile contents for docker manager."""
    cwd = Path(__file__).parent
    file = cwd.joinpath(image_mappings[image_name])
    return BytesIO(open(file, "r").read().encode("utf-8"))
