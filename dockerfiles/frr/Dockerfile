FROM ubuntu_ssh_server:focal

# Install packages required for the following repositories.
ENV DEBIAN_FRONTEND=noninteractive
ENV PATH "/sbin:/bin:/usr/sbin:/usr/bin:/usr/local/sbin"

RUN FRR_BUILD_DEPS='\
    git=1:2.25.1-1ubuntu3.6 \
    autoconf=2.69-11.1 \
    automake=1:1.16.1-4ubuntu6 \
    flex=2.6.4-6.2 \
    bison=2:3.5.1+dfsg-1 \
    curl=7.68.0-1ubuntu2.14 \
    ca-certificates=20211016ubuntu0.20.04.1 \
    gnupg=2.2.19-3ubuntu2.2 \
    build-essential=12.8ubuntu1.1' && \
    \
    apt-get update && apt-get install -y --no-install-recommends \
    $FRR_BUILD_DEPS && \
    \
    # Add DVMRP daemon and monit repositories
    curl -sS https://deb.troglobit.com/pubkey.gpg | apt-key add - && \
    echo "deb [arch=amd64] https://deb.troglobit.com/debian stable main" \
    | tee /etc/apt/sources.list.d/troglobit.list && \
    \
    # Add FRR source list for JAMMY release
    curl -s https://deb.frrouting.org/frr/keys.asc |  apt-key add - && \
    echo deb https://deb.frrouting.org/frr focal frr-stable |  tee -a /etc/apt/sources.list.d/frr.list && \
    \
    apt-get update && apt-get install -y --no-install-recommends \
    dnsutils=1:9.16.1-0ubuntu2.11 \
    iproute2=5.5.0-1ubuntu1 \
    iptables=1.8.4-3ubuntu2 \
    iputils-ping=3:20190709-3 \
    isc-dhcp-relay=4.4.1-2.1ubuntu5.20.04.4 \
    kmod=27-1ubuntu2.1 \
    monit=1:5.26.0-4 \
    mrouted=4.4 \
    net-tools=1.60+git20180626.aebd88e-1ubuntu1 \
    frr=8.4.1-0~ubuntu20.04.1 \
    frr-pythontools=8.4.1-0~ubuntu20.04.1 \
    telnet=0.17-41.2build1 \
    tcpdump=4.9.3-4ubuntu0.1 \
    traceroute=1:2.1.0-2 && \
    \
    # Need to install mrouted first before installing smcroute
    apt-get update && apt-get install -y --no-install-recommends \
    smcroute=2.4.2-4 &&\
    ## Fix "the END problem" in Quagga vtysh
    echo VTYSH_PAGER=more >> /etc/environment && \
    ## Enable IPv6 and IPv4 forwarding
    echo 'net.ipv4.conf.all.forwarding = 1' >> /etc/sysctl.conf && \
    echo 'net.ipv4.conf.default.forwarding = 1' >> /etc/sysctl.conf && \
    echo 'net.ipv4.conf.all.mc_forwarding = 1' >> /etc/sysctl.conf && \
    echo 'net.ipv4.conf.default.mc_forwarding = 1' >> /etc/sysctl.conf && \
    echo 'net.ipv6.conf.all.forwarding = 1' >> /etc/sysctl.conf && \
    echo 'net.ipv6.conf.default.forwarding = 1' >> /etc/sysctl.conf && \
    echo 'net.ipv6.conf.all.disable_ipv6 = 0' >> /etc/sysctl.conf && \
    echo 'net.ipv6.conf.default.disable_ipv6 = 0' >> /etc/sysctl.conf && \
    echo 'net.ipv6.conf.default.accept_ra = 2' >> /etc/sysctl.conf && \
    echo 'net.ipv6.conf.all.mc_forwarding = 1' >> /etc/sysctl.conf && \
    echo 'net.ipv6.conf.default.mc_forwarding = 1' >> /etc/sysctl.conf && \
    echo 'net.ipv6.conf.all.accept_ra = 2' >> /etc/sysctl.conf && \
    echo 'net.ipv4.conf.all.rp_filter = 0' >> /etc/sysctl.conf && \
    ## Enable vlan
    echo 8021q >> /etc/modules && \
    ldconfig && \
    ## Set Precedence to IPv4
    sed -i 's/#precedence ::ffff:0:0\/96  100/precedence ::ffff:0:0\/96  100/' /etc/gai.conf && \
    apt-get purge -y $FRR_BUILD_DEPS && \
    apt-get -y autoremove && \
    rm -rf /var/lib/apt/lists/*

# Copy Quagga Daemon configs
COPY ripd.conf /etc/frr/ripd.conf
COPY zebra.conf /etc/frr/zebra.conf
COPY smcroute.conf /etc/smcroute.conf
COPY init /root/init

# Permissions
RUN chown -R frr /etc/frr \
    ;chmod +x /root/init

RUN echo "root:bigfoot1" | chpasswd

EXPOSE 22

ENTRYPOINT [ "/root/init" ]
