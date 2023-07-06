# How to write inventory JSON?

Inventory JSON holds the data of the lab or physical devices.

## Supported options

- name,type & connection_type  are the mandatory fields
- #TODO

## Sample Inventory

```json
{
    "Demo-FRR": {
        "devices": [
            {
                "color": "cyan",
                "connection_type": "authenticated_ssh",
                "name": "board",
                "type": "debian_frr"
            },
            {
                "color": "cyan",
                "connection_type": "authenticated_ssh",
                "ipaddr": "10.64.40.16",
                "name": "wan",
                "port": 4001,
                "type": "debian_wan"
            },
            {
                "color": "blue",
                "connection_type": "authenticated_ssh",
                "ipaddr": "10.64.40.16",
                "name": "lan",
                "port": 4002,
                "type": "debian_lan"
            }
        ]
    }
}
```

You could also auto generate the inventory if docker-compose functionality is used.
