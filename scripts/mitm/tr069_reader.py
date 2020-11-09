"""mitmproxy script to read headers and body from TR069 XML messages and write them to terminal
Usage:
## Read all bodies and headers from tr069 packets:
mitmdump -ns tr069_reader.py -q -r log.mitm
## Read bodies and headers from tr069 PERIODIC packets. Filter is applied to XML in plaintext
mitmdump -ns addons/tr069_reader.py -q -r log.mitm --set filter=PERIODIC
## Read all in realtime:
mitmdump --mode transparent --showhost -q -s tr069_reader.py --set block_global=false
"""
from xml.etree import ElementTree

from mitmproxy import ctx

################################################
# MITM HOOKS. DO NOT RENAME
################################################


def load(loader):
    """Hook to handle script parameters
    Each parameter passed separately via --set
    --set filter=INFORM

    :param loader: mitmproxy loader object. Propagated automatically
    :return: None
    """
    loader.add_option(
        name="filter",
        typespec=str,
        default="",
        help="Filter packets by tr069 contents. Will be searched in request xml in plaintext",
    )


def response(flow):
    """Hook to handle each response event

    :param flow: HTTP flow. Propagated automatically
    :return: None
    """
    if is_suitable(flow.request):
        request_content = flow.request.content.decode("utf-8")
        parse_and_print_xml(request_content)
    if is_suitable(flow.response):
        response_content = flow.response.content.decode("utf-8")
        parse_and_print_xml(response_content)


#####################################################
# HELPERS
#####################################################


tr069_soap_namespaces = {
    "soap": "http://schemas.xmlsoap.org/soap/envelope/",
    "cwmp": "urn:dslforum-org:cwmp-1-2",
}


def element_to_dict(elem):
    """Helper to convert XML element to dict
    with same nested structure where element
    id (without namespace) is the key.
    0,1,2... is added to keys in case there are
    duplicates

    :param elem: XML ET element to be converted
    :rtype: dict
    """
    result = dict()
    for index, child in enumerate(elem):
        name = child.tag.split("}").pop()
        if list(child):
            #  Next statement checks if there are duplicates in tag names inside of element
            #  In case there are - adds an index to the end to maintain uniqueness
            if len({element.tag.split("}").pop() for element in elem}) != len(elem):
                result.update({f"{name}{index}": element_to_dict(child)})
            else:
                result.update({f"{name}": element_to_dict(child)})
        else:
            result.update({name: child.text})
    return result


def parse_and_print_xml(content: str) -> None:
    """Parse str->XML and print body and headers

    :param content: XML string to be converted
    :return: None
    """
    xml_tree = ElementTree.fromstring(content)
    xml_headers = list(xml_tree.find("soap:Header", namespaces=tr069_soap_namespaces))
    xml_body = list(xml_tree.find("soap:Body", namespaces=tr069_soap_namespaces))
    print(f"HEADERS:{element_to_dict(xml_headers)}")
    print(f"BODY:{element_to_dict(xml_body)}")


def is_suitable(packet):
    """Filtering

    :return: True if flow is suitable for all filters, False otherwise
    """
    content = packet.content.decode("utf-8")
    result = bool(
        content
    )  # Initialize to False in case there is no content in packet. No content - no party.
    if ctx.options.filter:
        result = result and ctx.options.filter in content
    return result
