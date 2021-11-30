FROM debian:buster-slim

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    traceroute \
    telnet \
    bash \
    quagga \
    iproute2 \
    iptables \
    net-tools\
    isc-dhcp-relay \
    openssh-server \
    iputils-ping \
    dnsutils \
    curl \
    gnupg \
    kmod

# Configure SSH
RUN mkdir /var/run/sshd && \
    sed -i 's/.*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's/.*GatewayPorts.*/GatewayPorts yes/' /etc/ssh/sshd_config && \
    sed -i 's/.*PermitTunnel.*/PermitTunnel yes/' /etc/ssh/sshd_config

# Quagga configurations
RUN mkdir /var/run/quagga \
    ;mkdir /var/log/quagga \
    ## Fix "the END problem" in Quagga vtysh
    ;echo VTYSH_PAGER=more >> /etc/environment \
    ## Enable IPv6 and IPv4 forwarding
    ;echo 'net.ipv4.conf.all.forwarding = 1' >> /etc/sysctl.conf \
    ;echo 'net.ipv4.conf.default.forwarding = 1' >> /etc/sysctl.conf \
    ;echo 'net.ipv4.conf.all.mc_forwarding = 1' >> /etc/sysctl.conf \
    ;echo 'net.ipv4.conf.default.mc_forwarding = 1' >> /etc/sysctl.conf \
    ;echo 'net.ipv6.conf.all.forwarding = 1' >> /etc/sysctl.conf \
    ;echo 'net.ipv6.conf.default.forwarding = 1' >> /etc/sysctl.conf \
    ;echo 'net.ipv6.conf.all.disable_ipv6 = 0' >> /etc/sysctl.conf \
    ;echo 'net.ipv6.conf.default.disable_ipv6 = 0' >> /etc/sysctl.conf \
    ;echo 'net.ipv6.conf.default.accept_ra = 2' >> /etc/sysctl.conf \
    ;echo 'net.ipv6.conf.all.accept_ra = 2' >> /etc/sysctl.conf \
    ;echo 'net.ipv4.conf.all.rp_filter = 0' >> /etc/sysctl.conf \
    ## Enable vlan
    ;echo 8021q >> /etc/modules \
    ;ldconfig \
    ## Set Precedence to IPv4
    ;sed -i 's/#precedence ::ffff:0:0\/96  100/precedence ::ffff:0:0\/96  100/' /etc/gai.conf


# Install DVMRP daemon and monit
RUN curl -sS https://deb.troglobit.com/pubkey.gpg | apt-key add - \
    ;echo "deb [arch=amd64] https://deb.troglobit.com/debian stable main" | \
    tee /etc/apt/sources.list.d/troglobit.list \
    ;echo "deb http://ftp.de.debian.org/debian buster-backports main" | \
    tee /etc/apt/sources.list.d/buster-backports.list \
    ;apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    mrouted \
    monit

# Copy Quagga Daemon configs
COPY ripd.conf /etc/quagga/ripd.conf
COPY zebra.conf /etc/quagga/zebra.conf
COPY init /root/init

# Permissions
RUN chown -R quagga /etc/quagga \
    ;chown quagga /var/run/quagga \
    ;chown quagga /var/log/quagga \
    ;chmod +x /root/init

RUN echo "root:bigfoot1" | chpasswd

ENV PATH "/sbin:/bin:/usr/sbin:/usr/bin"
ENTRYPOINT [ "/root/init" ]
