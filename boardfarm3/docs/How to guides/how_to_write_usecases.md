
# How to write Use cases?

- Use cases are written under the /usecases folder.
- Use cases are to be written from the user's point of view. It could be structured, depending on the applications which use them.
- These use cases could be executed in the interact.
- Use cases could be used in tests.

## Sample Usecase

```python
def http_get(
    device: Union[LAN, WAN], url: str, timeout: int = 20
) -> HTTPResult:
    """Check if the given HTTP server in WAN is running.
    This Use Case executes a curl command with a given timeout from the given
    client. The destination is specified by the url parameter
    :param device: the device from where http response to get
    :type device: Union[LAN, WAN]
    :param url: url to get the response
    :type url: str
    :param timeout: connection timeout for the curl command in seconds, default 20
    :type timeout: int
    :return: parsed http get response
    :rtype: HTTPResult
    """
    return device.http_get(url, timeout)
```
