FROM debian:9

RUN echo "root:bigfoot1" | chpasswd

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    apache2-utils \
    curl \
    dnsutils \
    iperf \
    iperf3 \
    iproute \
    iptables \
    isc-dhcp-server \
    isc-dhcp-client \
    lighttpd \
    net-tools \
    netcat \
    nmap \
    openssh-server \
    pppoe \
    psmisc \
    procps \
    python-pip \
    python-mysqldb \
    tinyproxy \
    traceroute \
    tftpd-hpa \
    tcpdump \
    vim-common \
    xinetd \
    less \
    wget \
    iw \
    wpasupplicant \
    ntpdate \
    build-essential

# NOTE: apparmor will interfere with dhclient, disable on HOST by running:
# sudo service apparmor stop
# sudo service apparmor teardown

RUN mkdir /var/run/sshd
RUN sed -i 's/.*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
RUN sed -i 's/.*GatewayPorts.*/GatewayPorts yes/' /etc/ssh/sshd_config
RUN sed -i 's/.*PermitTunnel.*/PermitTunnel yes/' /etc/ssh/sshd_config

# The following lines compile a shim to bind a process to an IP address
# using LD_PRELOAD. To run the shim use the following syntax:
# BIND_ADDR="X.X.X.X" LD_PRELOAD=/usr/lib/bind.so [command to run]
RUN wget http://daniel-lange.com/software/bind.c -O /root/bind.c
RUN cd /root; sed -i '/#include <errno.h>/a #include <arpa\/inet.h>' ./bind.c; gcc -nostartfiles -fpic -shared bind.c -o bind.so -ldl -D_GNU_SOURCE; strip bind.so; mv ./bind.so /usr/lib/

EXPOSE 22
