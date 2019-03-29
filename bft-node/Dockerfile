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
	xinetd

# NOTE: apparmor will interfere with dhclient, disable on HOST by running:
# sudo service apparmor stop
# sudo service apparmor teardown

RUN mkdir /var/run/sshd
RUN sed -i 's/.*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config

EXPOSE 22
