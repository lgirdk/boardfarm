#!/usr/bin/python

import random

def randomMAC():
    """generates and returns random mac address

    :return : random mac address
    :rtype : string
    """
    mac = [(random.randint(0x00, 0xff) & 0xfe),  # the lsb is 0, i.e. no multicat bit
             random.randint(0x00, 0xff),
             random.randint(0x00, 0xff),
             random.randint(0x00, 0xff),
             random.randint(0x00, 0xff),
             random.randint(0x00, 0xff)]
    mac_to_be_decided = ':'.join(map(lambda x: hex(x)[2:].lstrip("0x").zfill(2), mac))

    return (mac_to_be_decided)
