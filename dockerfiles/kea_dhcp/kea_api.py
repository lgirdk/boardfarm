"""To update KEA configuration over FAST API."""
# pylint: disable=import-error
# pylint: disable=W0622
# pylint: disable=too-few-public-methods
import json
from asyncio import Lock, TimeoutError, wait_for
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, status
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

_LOCK = Lock()
APP = FastAPI()

LOG_CONFIG = uvicorn.config.LOGGING_CONFIG
LOG_HANDLERS = {
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
        "access": {
            "formatter": "access",
            "filename": "/var/log/access.log",
            "class": "logging.handlers.RotatingFileHandler",
            "maxBytes": 1024,
            "backupCount": 3,
        },
    },
}


class DHCPData(BaseModel):
    """DHCP Config Data."""

    board_id: str
    reservation_data: dict


def _update_reservation(data: DHCPData, mode: str):
    """Use to update DHCPv4/v6 reservation data for a board."""
    # Hardcoding the path, since it runs for a Debian Image.
    fpath = f"/etc/kea/board-v{mode}-{data.board_id}.json"

    path = Path(fpath)
    reservation = json.load(path.open(encoding="UTF-8"))
    # make a copy for rollback
    json.dump(reservation, Path(f"{fpath}.old").open("w", encoding="UTF-8"), indent=4)

    # write new config
    reservation.update(data.reservation_data)
    json.dump(reservation, path.open("w", encoding="UTF-8"), indent=4)

    # reload the DHCP server via KEA Backend API.
    response = httpx.post(
        url="http://localhost:8000",
        json={"command": "config-reload", "service": [f"dhcp{mode}"]},
    )
    response.raise_for_status()
    # Turns out error messages on KEA don't throw an error code.
    output = response.json()
    if output[0]["result"] != 0:
        raise ValueError(output[0]["text"])


def rollback(data: DHCPData, mode: str):
    """Rollback DHCPv4/v6 configurations."""
    fpath = f"/etc/kea/board-v{mode}-{data.board_id}.json"

    backup = json.load(Path(f"{fpath}.old").open(encoding="UTF-8"))
    json.dump(backup, Path(fpath).open("w", encoding="UTF-8"), indent=4)

    response = httpx.post(
        url="http://localhost:8000",
        json={"command": "config-reload", "service": [f"dhcp{mode}"]},
    )
    response.raise_for_status()


async def update_dhcp_reservations(data: DHCPData):
    """Update DHCPv4 reservations."""
    _update_reservation(data=data, mode="4")


async def update_dhcp6_reservations(data: DHCPData):
    """Update DHCPv6 reservations."""
    _update_reservation(data=data, mode="6")


@APP.post("/update_dhcp")
async def update_dhcp_with_lock(data: DHCPData) -> JSONResponse:
    """Update DHCP server only if you have a lock."""
    output = JSONResponse(content={"detail": "Success"})

    if _LOCK.locked():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service busy"
        )

    async with _LOCK:
        try:
            await wait_for(update_dhcp_reservations(data), timeout=15)
        except TimeoutError as exc:
            rollback(data, mode="4")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Update request timed Out!!",
                headers={"exc-msg": f"{exc}"},
            )
        except ValueError as exc:
            rollback(data, mode="4")
            raise HTTPException(
                status_code=512,
                detail="Failed to update DHCP reservation.",
                headers={"kea-error": f"{exc}"},
            )
    return output


@APP.post("/update_dhcp6")
async def update_dhcp6_with_lock(data: DHCPData) -> JSONResponse:
    """Update DHCP6 server only if you have a lock."""
    output = JSONResponse(content={"detail": "Success"})

    if _LOCK.locked():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service busy"
        )

    async with _LOCK:
        try:
            await wait_for(update_dhcp6_reservations(data), timeout=15)
        except TimeoutError as exc:
            rollback(data, mode="6")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Update request timed Out!!",
                headers={"exc-msg": f"{exc}"},
            )
        except ValueError as exc:
            rollback(data, mode="6")
            raise HTTPException(
                status_code=512,
                detail="Failed to update DHCP reservation.",
                headers={"kea-error": f"{exc}"},
            )

    return output


if __name__ == "__main__":
    LOG_CONFIG.update(LOG_HANDLERS)
    uvicorn.run(APP, port=8080, host="0.0.0.0", log_config=LOG_CONFIG)
