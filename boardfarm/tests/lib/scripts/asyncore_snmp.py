import sys, re
def SnmpwalkAsync(target_IP=None, oid=None, walk_timeout=10):
        import time
        from pysnmp.proto.api import v2c
        from pysnmp.carrier.asyncore.dgram import udp, udp6
        from pysnmp.entity.rfc3413.oneliner import cmdgen
        from pysnmp.carrier.asyncore.dispatch import AsyncoreDispatcher
        from pyasn1.codec.ber import encoder, decoder

        # Create command generator
        cmdGen = cmdgen.CommandGenerator()

        # SNMP table header
        headVars = [v2c.ObjectIdentifier((oid))]

        # Build PDU
        reqPDU = v2c.GetBulkRequestPDU()
        v2c.apiBulkPDU.setDefaults(reqPDU)
        v2c.apiBulkPDU.setNonRepeaters(reqPDU, 0)
        v2c.apiBulkPDU.setMaxRepetitions(reqPDU, 25)
        v2c.apiBulkPDU.setVarBinds(reqPDU, [(x, v2c.null) for x in headVars])

        # Build message
        reqMsg = v2c.Message()
        v2c.apiMessage.setDefaults(reqMsg)
        v2c.apiMessage.setCommunity(reqMsg, 'public')
        v2c.apiMessage.setPDU(reqMsg, reqPDU)

        startedAt = time.time()
        output_list= []

        def cbTimerFun(timeNow):
            # Duration
            if timeNow - startedAt > walk_timeout:
                if walk_timeout != 0:
                    raise Exception("Request timed out")
                else:
                    if timeNow - startedAt > 30:
                        transportDispatcher.jobFinished(1)

        # noinspection PyUnusedLocal
        def cbRecvFun(transportDispatcher, transportDomain, transportAddress,
                      wholeMsg, reqPDU=reqPDU, headVars=headVars):
            startedAt = time.time()
            while wholeMsg:
                rspMsg, wholeMsg = decoder.decode(wholeMsg, asn1Spec=v2c.Message())
                rspPDU = v2c.apiMessage.getPDU(rspMsg)

                # Match response to request
                if v2c.apiBulkPDU.getRequestID(reqPDU) == v2c.apiBulkPDU.getRequestID(rspPDU):
                    # Format var-binds table
                    varBindTable = v2c.apiBulkPDU.getVarBindTable(reqPDU, rspPDU)

                    # Check for SNMP errors reported
                    errorStatus = v2c.apiBulkPDU.getErrorStatus(rspPDU)
                    if errorStatus and errorStatus != 2:
                        errorIndex = v2c.apiBulkPDU.getErrorIndex(rspPDU)
                        print('%s at %s' % (errorStatus.prettyPrint(),
                                            errorIndex and varBindTable[int(errorIndex) - 1] or '?'))
                        transportDispatcher.jobFinished(1)
                        break

                    # Report SNMP table
                    for tableRow in varBindTable:
                        for name, val in tableRow:
                            # print mib data
                            print('from: %s, %s = %s' % (
                                transportAddress, name.prettyPrint(), val.prettyPrint()
                            ))
                            output_list.append('from: %s, %s = %s\n' % (
                                transportAddress, name.prettyPrint(), val.prettyPrint()
                            ))

                    # Stop on EOM
                    for oid, val in varBindTable[-1]:
                        if not isinstance(val, v2c.Null):
                            break
                        else:
                            transportDispatcher.jobFinished(1)

                    # Generate request for next row
                    v2c.apiBulkPDU.setVarBinds(
                        reqPDU, [(x, v2c.null) for x, y in varBindTable[-1]]
                    )
                    v2c.apiBulkPDU.setRequestID(reqPDU, v2c.getNextRequestID())
                    transportDispatcher.sendMessage(
                        encoder.encode(reqMsg), transportDomain, transportAddress
                    )
                    startedAt = time.time()
            return wholeMsg

        transportDispatcher = AsyncoreDispatcher()
        transportDispatcher.registerRecvCbFun(cbRecvFun)
        transportDispatcher.registerTimerCbFun(cbTimerFun)
        ValidIpv4AddressRegex='(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)'
        match = re.search(ValidIpv4AddressRegex,target_IP)
        if match:
            transportDispatcher.registerTransport(
                udp.domainName, udp.UdpSocketTransport().openClientMode()
            )
            transportDispatcher.sendMessage(
                encoder.encode(reqMsg), udp.domainName, (target_IP, 161)
            )
        else:
            transportDispatcher.registerTransport(
                udp6.domainName, udp6.Udp6SocketTransport().openClientMode()
            )
            transportDispatcher.sendMessage(
                encoder.encode(reqMsg), udp6.domainName, (target_IP, 161)
            )
        transportDispatcher.jobStarted(1)
        # Dispatcher will finish as job#1 counter reaches zero
        transportDispatcher.runDispatcher()
        transportDispatcher.closeDispatcher()

        if output_list != []:
            return output_list
        else:
            return

SnmpwalkAsync(target_IP=str(sys.argv[1]), oid=str(sys.argv[2]), walk_timeout=str(sys.argv[3]))
