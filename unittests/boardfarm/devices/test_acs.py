import pytest
from boardfarm.devices.axiros_acs import AxirosACS
from boardfarm.exceptions import TR069FaultCode
from requests import HTTPError


class Response:
    def __init__(self, content, text):
        self.content = content
        self.text = text

    def content(self):
        return self.content

    def text(self):
        return self.text


text_1 = '<?xml version="1.0" encoding="UTF-8"?>\n<SOAP-ENV:Envelope\n  \n  xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"\n  xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"\n  xmlns:xsd3="http://www.w3.org/2001/XMLSchema"\n  xmlns:xsi3="http://www.w3.org/2001/XMLSchema-instance"\n>\n<SOAP-ENV:Body >\n<ns1:GetParameterValuesResponse xmlns:ns1="urn:AxessInterface">\n<Result>\n<code xsi3:type="xsd3:int">200</code>\n<details SOAP-ENC:arrayType="ns1:KeyValueStruct[1]" xsi3:type="SOAP-ENC:Array">\n<item>\n<key xsi3:type="xsd3:string">Device.ManagementServer.InstanceMode</key>\n<value xsi3:type="xsd3:string">InstanceNumber</value>\n</item>\n</details>\n<message xsi3:type="xsd3:string">OK</message>\n<ticketid xsi3:type="xsd3:int">85614</ticketid>\n</Result>\n</ns1:GetParameterValuesResponse>\n</SOAP-ENV:Body>\n</SOAP-ENV:Envelope>\n'

content_1 = b'<?xml version="1.0" encoding="UTF-8"?>\n<SOAP-ENV:Envelope\n  \n  xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"\n  xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"\n  xmlns:xsd3="http://www.w3.org/2001/XMLSchema"\n  xmlns:xsi3="http://www.w3.org/2001/XMLSchema-instance"\n>\n<SOAP-ENV:Body >\n<ns1:GetParameterValuesResponse xmlns:ns1="urn:AxessInterface">\n<Result>\n<code xsi3:type="xsd3:int">200</code>\n<details SOAP-ENC:arrayType="ns1:KeyValueStruct[1]" xsi3:type="SOAP-ENC:Array">\n<item>\n<key xsi3:type="xsd3:string">Device.ManagementServer.InstanceMode</key>\n<value xsi3:type="xsd3:string">InstanceNumber</value>\n</item>\n</details>\n<message xsi3:type="xsd3:string">OK</message>\n<ticketid xsi3:type="xsd3:int">85614</ticketid>\n</Result>\n</ns1:GetParameterValuesResponse>\n</SOAP-ENV:Body>\n</SOAP-ENV:Envelope>\n'

#200 and output dict
response_1 = Response(content_1, text_1)
out_1 = [{
    'key': 'Device.ManagementServer.InstanceMode',
    'type': 'string',
    'value': 'InstanceNumber'
}]

text_2 = '<?xml version="1.0" encoding="UTF-8"?>\n<SOAP-ENV:Envelope\n  \n  xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"\n  xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"\n  xmlns:xsd3="http://www.w3.org/2001/XMLSchema"\n  xmlns:xsi3="http://www.w3.org/2001/XMLSchema-instance"\n>\n<SOAP-ENV:Body >\n<ns1:GetParameterValuesResponse xmlns:ns1="urn:AxessInterface">\n<Result>\n<code xsi3:type="xsd3:int">500</code>\n<details SOAP-ENC:arrayType="ns1:KeyValueStruct[0]" xsi3:type="SOAP-ENC:Array">\n</details>\n<message xsi3:type="xsd3:string">No response from CPE, scenario was not completed or has error, lastResult - Stopped. {\'faultcode\': \'SOAP-ENV:Client\', \'code\': \'9005\', \'detail\': \'Invalid Parameter Name\'}</message>\n<ticketid xsi3:type="xsd3:int">38386</ticketid>\n</Result>\n</ns1:GetParameterValuesResponse>\n</SOAP-ENV:Body>\n</SOAP-ENV:Envelope>\n'

content_2 = b'<?xml version="1.0" encoding="UTF-8"?>\n<SOAP-ENV:Envelope\n  \n  xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"\n  xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"\n  xmlns:xsd3="http://www.w3.org/2001/XMLSchema"\n  xmlns:xsi3="http://www.w3.org/2001/XMLSchema-instance"\n>\n<SOAP-ENV:Body >\n<ns1:GetParameterValuesResponse xmlns:ns1="urn:AxessInterface">\n<Result>\n<code xsi3:type="xsd3:int">500</code>\n<details SOAP-ENC:arrayType="ns1:KeyValueStruct[0]" xsi3:type="SOAP-ENC:Array">\n</details>\n<message xsi3:type="xsd3:string">No response from CPE, scenario was not completed or has error, lastResult - Stopped. {\'faultcode\': \'SOAP-ENV:Client\', \'code\': \'9005\', \'detail\': \'Invalid Parameter Name\'}</message>\n<ticketid xsi3:type="xsd3:int">38386</ticketid>\n</Result>\n</ns1:GetParameterValuesResponse>\n</SOAP-ENV:Body>\n</SOAP-ENV:Envelope>\n'

#500 and fault code
response_2 = Response(content_2, text_2)

text_3 = '<?xml version="1.0" encoding="UTF-8"?>\n<SOAP-ENV:Envelope\n  \n  xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"\n  xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"\n  xmlns:xsd3="http://www.w3.org/2001/XMLSchema"\n  xmlns:xsi3="http://www.w3.org/2001/XMLSchema-instance"\n>\n<SOAP-ENV:Body >\n<ns1:SetParameterValuesResponse xmlns:ns1="urn:AxessInterface">\n<Result>\n<code xsi3:type="xsd3:int">507</code>\n<details SOAP-ENC:arrayType="ns1:KeyValueStruct[0]" xsi3:type="SOAP-ENC:Array">\n</details>\n<message xsi3:type="xsd3:string">Lifetime Expired</message>\n<ticketid xsi3:type="xsd3:int">85202</ticketid>\n</Result>\n</ns1:SetParameterValuesResponse>\n</SOAP-ENV:Body>\n</SOAP-ENV:Envelope>\n'

content_3 = b'<?xml version="1.0" encoding="UTF-8"?>\n<SOAP-ENV:Envelope\n  \n  xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"\n  xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"\n  xmlns:xsd3="http://www.w3.org/2001/XMLSchema"\n  xmlns:xsi3="http://www.w3.org/2001/XMLSchema-instance"\n>\n<SOAP-ENV:Body >\n<ns1:SetParameterValuesResponse xmlns:ns1="urn:AxessInterface">\n<Result>\n<code xsi3:type="xsd3:int">507</code>\n<details SOAP-ENC:arrayType="ns1:KeyValueStruct[0]" xsi3:type="SOAP-ENC:Array">\n</details>\n<message xsi3:type="xsd3:string">Lifetime Expired</message>\n<ticketid xsi3:type="xsd3:int">85202</ticketid>\n</Result>\n</ns1:SetParameterValuesResponse>\n</SOAP-ENV:Body>\n</SOAP-ENV:Envelope>\n'

#507 and no fault code
response_3 = Response(content_3, text_3)

text_4 = '<?xml version="1.0" encoding="UTF-8"?>\n<SOAP-ENV:Envelope\n  \n  xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"\n  xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"\n  xmlns:xsd3="http://www.w3.org/2001/XMLSchema"\n  xmlns:xsi3="http://www.w3.org/2001/XMLSchema-instance"\n>\n<SOAP-ENV:Body >\n<ns1:SetParameterValuesResponse xmlns:ns1="urn:AxessInterface">\n<Result>\n<code xsi3:type="xsd3:int">500</code>\n<details SOAP-ENC:arrayType="ns1:KeyValueStruct[0]" xsi3:type="SOAP-ENC:Array">\n</details>\n<message xsi3:type="xsd3:string">No response from CPE, scenario was not completed or has error, lastResult - invalid literal for int() with base 10: \'abc\'</message>\n<ticketid xsi3:type="xsd3:int">85202</ticketid>\n</Result>\n</ns1:SetParameterValuesResponse>\n</SOAP-ENV:Body>\n</SOAP-ENV:Envelope>\n'

content_4 = b'<?xml version="1.0" encoding="UTF-8"?>\n<SOAP-ENV:Envelope\n  \n  xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"\n  xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"\n  xmlns:xsd3="http://www.w3.org/2001/XMLSchema"\n  xmlns:xsi3="http://www.w3.org/2001/XMLSchema-instance"\n>\n<SOAP-ENV:Body >\n<ns1:SetParameterValuesResponse xmlns:ns1="urn:AxessInterface">\n<Result>\n<code xsi3:type="xsd3:int">500</code>\n<details SOAP-ENC:arrayType="ns1:KeyValueStruct[0]" xsi3:type="SOAP-ENC:Array">\n</details>\n<message xsi3:type="xsd3:string">No response from CPE, scenario was not completed or has error, lastResult - invalid literal for int() with base 10: \'abc\'</message>\n<ticketid xsi3:type="xsd3:int">85202</ticketid>\n</Result>\n</ns1:SetParameterValuesResponse>\n</SOAP-ENV:Body>\n</SOAP-ENV:Envelope>\n'

#500 and no faultcode
response_4 = Response(content_4, text_4)

text_5 = '<?xml version="1.0" encoding="UTF-8"?>\n<SOAP-ENV:Envelope\n  \n  xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"\n  xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"\n  xmlns:xsd3="http://www.w3.org/2001/XMLSchema"\n  xmlns:xsi3="http://www.w3.org/2001/XMLSchema-instance"\n>\n<SOAP-ENV:Body >\n<ns1:GetParameterValuesResponse xmlns:ns1="urn:AxessInterface">\n<Result>\n<code xsi3:type="xsd3:int">507</code>\n<details SOAP-ENC:arrayType="ns1:KeyValueStruct[0]" xsi3:type="SOAP-ENC:Array">\n</details>\n<message xsi3:type="xsd3:string">No response from CPE, scenario was not completed or has error, lastResult - Stopped. {\'faultcode\': \'SOAP-ENV:Client\', \'code\': \'1234\', \'detail\': \'Some random fault code\'}</message>\n<ticketid xsi3:type="xsd3:int">38386</ticketid>\n</Result>\n</ns1:GetParameterValuesResponse>\n</SOAP-ENV:Body>\n</SOAP-ENV:Envelope>\n'

content_5 = b'<?xml version="1.0" encoding="UTF-8"?>\n<SOAP-ENV:Envelope\n  \n  xmlns:SOAP-ENC="http://schemas.xmlsoap.org/soap/encoding/"\n  xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"\n  xmlns:xsd3="http://www.w3.org/2001/XMLSchema"\n  xmlns:xsi3="http://www.w3.org/2001/XMLSchema-instance"\n>\n<SOAP-ENV:Body >\n<ns1:GetParameterValuesResponse xmlns:ns1="urn:AxessInterface">\n<Result>\n<code xsi3:type="xsd3:int">507</code>\n<details SOAP-ENC:arrayType="ns1:KeyValueStruct[0]" xsi3:type="SOAP-ENC:Array">\n</details>\n<message xsi3:type="xsd3:string">No response from CPE, scenario was not completed or has error, lastResult - Stopped. {\'faultcode\': \'SOAP-ENV:Client\', \'code\': \'1234\', \'detail\': \'Some random fault code\'}</message>\n<ticketid xsi3:type="xsd3:int">38386</ticketid>\n</Result>\n</ns1:GetParameterValuesResponse>\n</SOAP-ENV:Body>\n</SOAP-ENV:Envelope>\n'

#507 and fault code
response_5 = Response(content_5, text_5)


@pytest.mark.parametrize("test_parse_soap_response, expected_result", [
    (response_1, out_1),
])
def test_parse_soap_response(test_parse_soap_response, expected_result):
    assert expected_result == AxirosACS._parse_soap_response(
        test_parse_soap_response)


@pytest.mark.parametrize(
    "TR069_exception_parse_soap_response, expected_result", [
        (response_2, None),
    ])
def test_TR069_exception_parse_soap_response(
    TR069_exception_parse_soap_response, expected_result):
    with pytest.raises(TR069FaultCode):
        AxirosACS._parse_soap_response(TR069_exception_parse_soap_response)


@pytest.mark.parametrize("HTTP_exception_parse_soap_response, expected_result",
                         [
                             (response_3, None),
                             (response_4, None),
                             (response_5, None),
                         ])
def test_HTTP_exception_parse_soap_response(HTTP_exception_parse_soap_response,
                                            expected_result):
    with pytest.raises(HTTPError):
        AxirosACS._parse_soap_response(HTTP_exception_parse_soap_response)
