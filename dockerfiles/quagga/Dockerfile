FROM debian_ssh_server

# Install packages required for the following repositories.
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates=20200601~deb10u2 \
    curl=7.64.0-4+deb10u2 \
    gnupg=2.2.12-1+deb10u1

# Add DVMRP daemon and monit repositories
RUN curl -sS https://deb.troglobit.com/pubkey.gpg | apt-key add - \
    ; echo "deb [arch=amd64] https://deb.troglobit.com/debian stable main" \
    | tee /etc/apt/sources.list.d/troglobit.list \
    ; echo "deb http://ftp.de.debian.org/debian buster-backports main" \
    | tee /etc/apt/sources.list.d/buster-backports.list

RUN apt-get update && apt-get install -y --no-install-recommends \
    dnsutils=1:9.11.5.P4+dfsg-5.1+deb10u6 \
    iproute2=4.20.0-2+deb10u1 \
    iptables=1.8.2-4 \
    iputils-ping=3:20180629-2+deb10u2 \
    isc-dhcp-relay=4.4.1-2+deb10u1 \
    kmod=26-1 \
    monit=1:5.27.1-1~bpo10+1 \
    mrouted=4.4 \
    net-tools=1.60+git20180626.aebd88e-1 \
    quagga=1.2.4-3 \
    telnet=0.17-41.2 \
    traceroute=1:2.1.0-2 \
    && rm -rf /var/lib/apt/lists/*

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

EXPOSE 22

ENV PATH "/sbin:/bin:/usr/sbin:/usr/bin"
ENTRYPOINT [ "/root/init" ]
