FROM ubuntu_ssh_server

# Install packages required for the following repositories.
ENV DEBIAN_FRONTEND=noninteractive
ENV PATH "/sbin:/bin:/usr/sbin:/usr/bin:/usr/local/sbin"

RUN QUAGGA_BUILD_DEPS='\
    git=1:2.25.1-1ubuntu3.5 \
    autoconf=2.69-11.1 \
    automake=1:1.16.1-4ubuntu6 \
    flex=2.6.4-6.2 \
    bison=2:3.5.1+dfsg-1 \
    curl=7.68.0-1ubuntu2.13 \
    ca-certificates=20211016~20.04.1 \
    gnupg=2.2.19-3ubuntu2.2 \
    build-essential=12.8ubuntu1' && \
    \
    apt-get update && apt-get install -y --no-install-recommends \
    $QUAGGA_BUILD_DEPS && \
    \
    # Add DVMRP daemon and monit repositories
    curl -sS https://deb.troglobit.com/pubkey.gpg | apt-key add - && \
    echo "deb [arch=amd64] https://deb.troglobit.com/debian stable main" \
    | tee /etc/apt/sources.list.d/troglobit.list && \
    \
    apt-get update && apt-get install -y --no-install-recommends \
    dnsutils=1:9.16.1-0ubuntu2.10 \
    iproute2=5.5.0-1ubuntu1 \
    iptables=1.8.4-3ubuntu2 \
    iputils-ping=3:20190709-3 \
    isc-dhcp-relay=4.4.1-2.1ubuntu5.20.04.3 \
    kmod=27-1ubuntu2.1 \
    monit=1:5.26.0-4 \
    mrouted=4.4 \
    net-tools=1.60+git20180626.aebd88e-1ubuntu1 \
    quagga=1.2.4-4build1 \
    telnet=0.17-41.2build1 \
    traceroute=1:2.1.0-2 && \
    \
    # Quagga configurations
    mkdir /var/run/quagga && \
    mkdir /var/log/quagga && \
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
    echo 'net.ipv6.conf.all.accept_ra = 2' >> /etc/sysctl.conf && \
    echo 'net.ipv4.conf.all.rp_filter = 0' >> /etc/sysctl.conf && \
    ## Enable vlan
    echo 8021q >> /etc/modules && \
    ldconfig && \
    ## Set Precedence to IPv4
    sed -i 's/#precedence ::ffff:0:0\/96  100/precedence ::ffff:0:0\/96  100/' /etc/gai.conf && \
    git clone https://github.com/troglobit/pim6sd.git && \
    cd pim6sd/ && \
    ./autogen.sh && \
    ./configure && make && \
    make install-strip && cd .. && \
    rm -rf pim6sd && \
    apt-get purge -y $QUAGGA_BUILD_DEPS && \
    apt-get -y autoremove && \
    rm -rf /var/lib/apt/lists/*

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

ENTRYPOINT [ "/root/init" ]
