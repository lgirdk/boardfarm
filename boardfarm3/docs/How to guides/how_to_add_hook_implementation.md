# How to write env JSON?

Boardfarm boots and configures the devices with the settings mentioned in the env.json. Thus env.json is a mandatory parameter to run boardfarm.

- In env Json, number of devices required could be mentioned
- Any number of required devices could be mentioned. An exception is thrown when the number is not supported.
- Detailed configuration details could be provided for the device.

## Basic env Json

```json
{
    "environment_def": {
        "board": {
            "lan_clients": [
            {}
            ]
        }
    }
}
```

### Detailed env Json

```json
{
    "environment_def": {
        "board": {
            "lan_clients": [{},
                {},
                {},
                {}
            ],
            "model": "XXXX",
            "software": {
                "factory_reset": true,
                "flash_strategy": "meta_build",
                "image_uri": "XXXX"
            },
            "wifi_clients": [{
                    "authentication": "WPA-PSK",
                    "band": "5",
                    "network": "private",
                    "protocol": "802.11ac"
                },
                {
                    "authentication": "WPA-PSK",
                    "band": "2.4",
                    "network": "private",
                    "protocol": "802.11n"
                }
            ]
        },
        "tr-069": {}
    },
    "version": "2.23"
}
```
