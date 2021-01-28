#!/bin/bash -xe

IFACE=${1:-undefined}
START_VLAN=${2:-101}
END_VLAN=${3:-144}
OPTS=${4:-"both"} # both, odd, even, odd-dhcp, even-dhcp
BRINT=br-bft
BF_IMG=${BF_IMG:-"bft:node"}
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"
STARTSSHPORT=5000
STARTWEBPORT=8000

if ! docker inspect --type=image $BF_IMG > /dev/null 2>&1 ; then
    (cd $DIR; docker build -t $BF_IMG ${BF_IMG/:/-})
fi

random_private_mac () {
    python3 - <<END
import random

def randomMAC():
    mac = [ (random.randint(0x00,0xff) & 0xfe), # the lsb is 0, i.e. no multicast bit
             random.randint(0x00, 0xff),
             random.randint(0x00, 0xff),
             random.randint(0x00, 0xff),
             random.randint(0x00, 0xff),
             random.randint(0x00, 0xff) ]
    mac_to_be_decided = ':'.join(map(lambda x : hex(x)[2:].lstrip("0x").zfill(2),mac))

    return (mac_to_be_decided)

if __name__ == '__main__':
    print(randomMAC())
END
}

local_route () {
    # TODO: This is a problem if the router network matches the host network
    host_dev=$(ip route list | grep ^default |  awk '{print $5}' )
    local_route=$(ip route | grep "dev $host_dev" | grep src | awk '{print $1}' | head -n1)
    docker0=$(ip -4 addr show docker0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
    docker exec $cname ip route add $local_route dev eth0 via $docker0
}

# helper function for lan containers to push the mgmt iface in a separate routing table
# and creates a bash alias named "mgmt" that should be used to bind commands to the
# mgmt iface (this is to allow internet connectivity to specific commands without imparing
# the default route of the iface_dut)
# This function should be called when the container has an eth0 and an eth1 ifaces and eth0
# needs to be isolated
isolate_management() {
    local cname=${1}
    local br_name=${2:-"docker0"}

    docker_dev=$(docker exec $cname ip route list | grep ^default |  awk '{print $5}' )
    docker_gw_ip=$(ip -4 addr show $br_name | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
    docker_dev_ip=$(docker exec $cname ip -4 addr show $docker_dev | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
    docker_nw=$(ip route | grep "dev ${br_name}" | grep src | awk '{print $1}' | head -n1)

    docker exec $cname bash -c "echo \"1 mgmt\" >> /etc/iproute2/rt_tables"
    docker exec $cname ip route add default via $docker_gw_ip table mgmt
    docker exec $cname ip rule add from $docker_dev_ip table mgmt
    docker exec $cname ip rule add to $docker_dev_ip table mgmt
    docker exec $cname ip rule add from $docker_nw table mgmt
    docker exec $cname ip rule add to $docker_nw table mgmt

    docker cp $cname:root/.bashrc bashrc_$cname
    echo "alias mgmt='BIND_ADDR=$docker_dev_ip LD_PRELOAD=/usr/lib/bind.so '" >> bashrc_$cname
    docker cp bashrc_$cname $cname:root/.bashrc; rm bashrc_$cname
}
# creates container running with ssh on eth0, adds DUT facing interface only
create_container_stub () {
    local cname=${1}
    local sshport=${2}
    local proxyport=${3}
    local ifacedut=${4}

    docker stop $cname && docker rm $cname
    docker run --name $cname --privileged -h $cname --restart=always \
        -p $sshport:22 \
        -p $proxyport:8080 \
        -d $BF_IMG /usr/sbin/sshd -D

    cspace=$(docker inspect --format '{{.State.Pid}}' $cname)
    # this should avoid the cli wrapping onto itself
    docker exec $cname bash -c 'echo "stty columns 200" >> /root/.bashrc'
    sudo ip link set netns $cspace dev $ifacedut
    docker exec $cname ip link set $ifacedut name eth1
    docker exec $cname ip link set dev eth1 address $(random_private_mac $vlan)

    isolate_management ${cname}
}

# eth0 is docker private network, eth1 is vlan on specific interface
create_container_eth1_vlan () {
    local vlan=$1
    local offset=${2:-0}

    cname=bft-node-$IFACE-$vlan-$offset

    sudo ip link del $IFACE.$vlan || true
    sudo ip link add link $IFACE name $IFACE.$vlan type vlan id $vlan

    create_container_stub $cname \
            $(( $STARTSSHPORT + $offset + $vlan )) \
            $(( $STARTWEBPORT + $offset + $vlan )) \
            $IFACE.$vlan
}

# eth0 is docker private network, eth1 is vlan on specific interface within a bridge
create_container_eth1_bridged_vlan () {
    local vlan=$1
    local offset=${2:-0}

    # verify settings are correct
    # TODO: verify the set
    sudo sysctl -w net.bridge.bridge-nf-call-arptables=0
    sudo sysctl -w net.bridge.bridge-nf-call-ip6tables=0
    sudo sysctl -w net.bridge.bridge-nf-call-iptables=0

    cname=bft-node-$IFACE-$vlan-$offset
    docker stop $cname && docker rm $cname
    docker run --name $cname --privileged -h $cname --restart=always \
        -p $(( $STARTSSHPORT + $offset + $vlan )):22 \
        -p $(( $STARTWEBPORT + $offset + $vlan )):8080 \
        -d $BF_IMG /usr/sbin/sshd -D

    cspace=$(docker inspect --format '{{.State.Pid}}' $cname)
    isolate_management ${cname}

    # create bridge
    sudo ip link add br-$IFACE.$vlan type bridge || true
    sudo ip link set br-$IFACE.$vlan up

    # create uplink vlan on IFACE
    sudo ip link delete $IFACE.$vlan || true
    sudo ip link add link $IFACE name $IFACE.$vlan type vlan id $vlan
    sudo ip link set dev $IFACE.$vlan address $(random_private_mac $vlan)
    sudo ip link set $IFACE.$vlan master br-$IFACE.$vlan
    sudo ip link set $IFACE up
    sudo ip link set $IFACE.$vlan up

    # add veth for new container (one per container vs. the two above are shared)
    sudo ip link add v$IFACE-$vlan-$offset type veth peer name eth1 netns $cspace
    sudo ip link set v$IFACE-$vlan-$offset master br-$IFACE.$vlan
    sudo ip link set v$IFACE-$vlan-$offset up

    docker exec $cname ip link set eth1 up
}

# eth0 is docker private network, eth1 is vlan on specific interface within a bridge
create_container_eth1_macvtap_vlan () {
    local vlan=$1
    local offset=${2:-0}

    # verify settings are correct
    # TODO: verify the set
    sudo sysctl -w net.bridge.bridge-nf-call-arptables=0
    sudo sysctl -w net.bridge.bridge-nf-call-ip6tables=0
    sudo sysctl -w net.bridge.bridge-nf-call-iptables=0

    cname=bft-node-$IFACE-$vlan-$offset
    docker stop $cname && docker rm $cname
    docker run --name $cname --privileged -h $cname --restart=always \
        -p $(( $STARTSSHPORT + $offset + $vlan )):22 \
        -p $(( $STARTWEBPORT + $offset + $vlan )):8080 \
        -d $BF_IMG /usr/sbin/sshd -D

    cspace=$(docker inspect --format '{{.State.Pid}}' $cname)
    isolate_management ${cname}

    # create uplink vlan on IFACE
    sudo ip link add link $IFACE name $IFACE.$vlan type vlan id $vlan
    sudo ip link set dev $IFACE.$vlan address $(random_private_mac $vlan)
    sudo ip link set $IFACE.$vlan up

    # add veth for new container (one per container vs. the two above are shared)
    sudo ip link add link $IFACE.$vlan name eth1 type macvtap
    sudo ip link set netns $cspace dev eth1

    docker exec $cname ip link set eth1 up
}

# eth0/eth1 are both dhcp on the main network
create_container_eth1_dhcp () {
    local vlan=$1

        cname=bft-node-$IFACE-$vlan
        docker stop $cname && docker rm $cname
        docker run --name $cname --privileged -h $cname --restart=always \
                -d --network=none $BF_IMG /usr/sbin/sshd -D

        cspace=$(docker inspect --format '{{.State.Pid}}' $cname)

        # create lab network access port
    sudo ip link add tempfoo link $IFACE type macvlan mode bridge
        sudo ip link set dev tempfoo up
        sudo ip link set netns $cspace dev tempfoo
        docker exec $cname ip link set tempfoo name eth1
        docker exec $cname ifconfig eth1 up
        docker exec $cname dhclient eth1
}

# eth1 is on main network and static
create_container_eth1_static () {
    local name=$1
    local ip=$2
    local default_route=$3
    local driver=${4:-macvlan}
    local ipv6_addr=${5:-"0"}
    local ipv6_default=${6:-"0"}

    cname=bft-node-$IFACE-$name
    docker stop $cname && docker rm $cname
    docker run --name $cname --privileged -h $cname --restart=always \
        -d --network=none $BF_IMG /usr/sbin/sshd -D

    cspace=$(docker inspect --format {{.State.Pid}} $cname)

    # create lab network access port
    if [ "$driver" = "ipvlan" ]
    then
        sudo ip link add tempfoo link $IFACE type $driver mode l2
    else
        sudo ip link add tempfoo link $IFACE type $driver mode bridge
    fi
    sudo ip link set dev tempfoo up
    sudo ip link set netns $cspace dev tempfoo
    docker exec $cname ip link set tempfoo name eth1
    docker exec $cname ip link set eth1 up
    docker exec $cname ip addr add $ip dev eth1
    docker exec $cname ip route add default via $default_route dev eth1
    docker exec $cname ping $default_route -c3

    ! [ "$ipv6_addr" != "0" -a "$ipv6_default" != "0" ] && echo "Error: missing ipv6 params" && return

    docker exec $cname sysctl net.ipv6.conf.eth1.disable_ipv6=0
    docker exec $cname ip -6 addr add $ipv6_addr dev eth1
    # if default route by link local does not get configured
    docker exec $cname ip -6 route add default via $ipv6_default dev eth1 || true
    sleep 3
    docker exec $cname bash -c "ping -c3 $ipv6_default"
}

# eth1 is on main network and static
create_container_eth1_static_ipvlan () {
    local name=$1
    local ip=$2
    local default_route=$3

    cname=bft-node-$IFACE-$name
    docker stop $cname && docker rm $cname
    docker run --name $cname --privileged -h $cname --restart=always \
        -d --network=none $BF_IMG /usr/sbin/sshd -D

    cspace=$(docker inspect --format {{.State.Pid}} $cname)

    # create lab network access port
    sudo ip link add tempfoo link $IFACE type ipvlan mode l2
    sudo ip link set dev tempfoo up
    sudo ip link set netns $cspace dev tempfoo
    docker exec $cname ip link set tempfoo name eth1
    docker exec $cname ip link set eth1 up
    docker exec $cname ip addr add $ip dev eth1
    docker exec $cname ip route add default via $default_route dev eth1
    docker exec $cname ping $default_route -c3
}

# eth0 is docker private network, eth1 is static ip
create_container_eth1_static_linked () {
    local name=$1
    local ip=$2
    local default_route=$3
    local offset=${4:-0}
    local driver=${5:-macvlan}
    local ipv6_addr=${6:-"0"}
    local ipv6_default=${7:-"0"}

    cname=bft-node-$IFACE-$name
    docker stop $cname && docker rm $cname
    docker run --name $cname --privileged -h $cname --restart=always \
        -p $(( $STARTSSHPORT + $offset )):22 \
        -p $(( $STARTWEBPORT + $offset )):8080 \
        -d $BF_IMG /usr/sbin/sshd -D

    cspace=$(docker inspect --format {{.State.Pid}} $cname)
    isolate_management ${cname}

    # create lab network access port
    if [ "$driver" = "ipvlan" ]
    then
        sudo ip link add tempfoo link $IFACE type $driver mode l2
    else
        # driver can be macvtap or macvlan. default=macvlan
        sudo ip link add tempfoo link $IFACE type $driver mode bridge
    fi
    sudo ip link set dev tempfoo up
    sudo ip link set netns $cspace dev tempfoo
    docker exec $cname ip link set tempfoo name eth1
    docker exec $cname ip link set eth1 up
    docker exec $cname ip addr add $ip dev eth1
    docker exec $cname ip route del default dev eth0
    docker exec $cname ip route add default via $default_route dev eth1
    docker exec $cname ping $default_route -c3

    ! [ "$ipv6_addr" != "0" -a "$ipv6_default" != "0" ] && echo "Error: missing ipv6 params" && return

    docker exec $cname sysctl net.ipv6.conf.eth1.disable_ipv6=0
    docker exec $cname ip -6 addr add $ipv6_addr dev eth1
    # if default route by link local does not get configured
    docker exec $cname ip -6 route add default via $ipv6_default dev eth1 || true
    sleep 3
    docker exec $cname bash -c "ping -c3 $ipv6_default"
}

add_docker_network () {
    local cname=$1
    local nw_name=$2
    local ip=$3
    local ipv6_addr=$4
    local table=$5

    prefix=$(docker inspect $nw_name | grep iface_prefix | awk -F '"' '{print $4}')
    local ip_default=$(docker network inspect $nw_name | grep Gateway | sed -n "1p" | awk -F '"' '{print $4}')
    local ipv6_default=$(docker network inspect $nw_name | grep Gateway | sed -n "2p" | awk -F '"' '{print $4}')
    local ip_nw=$(docker network inspect $nw_name | grep Subnet | sed -n "1p" | awk -F '"' '{print $4}')
    local ipv6_nw=$(docker network inspect $nw_name | grep Subnet | sed -n "2p" | awk -F '"' '{print $4}')

    docker network connect --ip $ip --ip6 $ipv6_addr $nw_name $cname

    docker exec $cname bash -c "echo \"$table $prefix\" >> /etc/iproute2/rt_tables"
    docker exec $cname ip route add default via $ip_default table $prefix
    docker exec $cname ip -6 route add default via $ipv6_default table $prefix
    # gateway lookups
    docker exec $cname ip rule add from $ip_default table $prefix
    docker exec $cname ip rule add to $ip_default table $prefix
    docker exec $cname ip -6 rule add from $ipv6_default table $prefix
    docker exec $cname ip -6 rule add to $ipv6_default table $prefix
    # subnet lookups
    docker exec $cname ip rule add from $ip_nw table $prefix
    docker exec $cname ip rule add to $ip_nw table $prefix
    docker exec $cname ip -6 rule add from $ipv6_nw table $prefix
    docker exec $cname ip -6 rule add to $ipv6_nw table $prefix
}

remove_docker_network () {
    local cname=$1
    local nw_name=$2
    local prefix=$(docker inspect $nw_name | grep iface_prefix | awk -F '"' '{print $4}')

    # delete ipv4 rules
    for i in $(docker exec $cname ip rule | grep $prefix | awk -F ":" '{print $1}'); do
        docker exec $cname ip rule del prio $i;
    done

    # delete ipv6 rules
    for i in $(docker exec $cname ip -6 rule | grep $prefix | awk -F ":" '{print $1}'); do
        docker exec $cname ip -6 rule del prio $i;
    done

    # delete routes and routing table
    docker exec $cname ip route flush table $prefix
    docker exec $cname ip -6 route flush table $prefix
    docker exec wan-mv1-docsis2-1 bash -c "sed -i '/${prefix}/d' /etc/iproute2/rt_tables"
    docker network disconnect $nw_name $cname
}

create_container_docker_network_linked () {
    local cname=$1
    local ip=$2
    local ipv6_addr=$3
    local offset=${4:-0}
    local nw_name=${5:-"0"}
    local br_name=${6:-"bridge"}

    docker stop $cname && docker rm $cname
    docker run --name $cname --privileged -h $cname --restart=always \
        --network $br_name \
        -p $(( $STARTSSHPORT + $offset )):22 \
        -p $(( $STARTWEBPORT + $offset )):8080 \
        -d $BF_IMG /usr/sbin/sshd -D

    cspace=$(docker inspect --format {{.State.Pid}} $cname)

    nw_gw=$(docker inspect -f '{{ index (index .IPAM.Config 0) "Gateway" }}' $br_name)
    br_iface=$(ifconfig | grep -B1 "inet $nw_gw" | head -1 | cut -d: -f1)

    isolate_management ${cname} $br_iface
    docker exec $cname ip route del default

    docker network connect --ip $ip --ip6 $ipv6_addr $nw_name $cname
    # com.docker.network.container_interface_prefix
    docker exec $cname sysctl net.ipv6.conf.eth1.disable_ipv6=0
    docker exec $cname sysctl net.ipv6.conf.eth1.autoconf=0

    # disable ipv6 on eth0 for installation of packages via ipv4
    docker exec $cname sysctl net.ipv6.conf.eth0.disable_ipv6=1

    local ip_default=$(docker network inspect $nw_name | grep Gateway | sed -n "1p" | awk -F '"' '{print $4}')
    local ipv6_default=$(docker network inspect $nw_name | grep Gateway | sed -n "2p" | awk -F '"' '{print $4}')

    docker exec $cname ip route add default via $ip_default
    docker exec $cname ip route add default via $ipv6_default
    docker exec $cname bash -c "ping -c3 $ip_default"
    docker exec $cname bash -c "ping6 -c3 $ipv6_default"
}

# eth0 is docker private network, eth1 physical device
create_container_eth1_phys () {
    local dev=$1
    local offset=$2

    cname=bft-node-$dev
    docker stop $cname && docker rm $cname
    docker run --name $cname --privileged -h $cname --restart=always \
        -p $(( $STARTSSHPORT + $offset )):22 \
        -p $(( $STARTWEBPORT + $offset )):8080 \
        -d $BF_IMG /usr/sbin/sshd -D

    cspace=$(docker inspect --format {{.State.Pid}} $cname)

    # create lab network access port
    sudo ip link set netns $cspace dev $dev
    docker exec $cname ip link set $dev name wlan1
    docker exec $cname ip link set wlan1 up
}

# eth0 is docker private network, eth1 with device
create_container_eth1_wifi () {
    local dev=$1
    local band=${2:-"2.4GHz"}
    local proxy_ip=${3:-"0"}
    local proxy_port=${4:-"8080"}
    local offset=${5:-"501"}

    cname=bft-wifi-node-$dev-$band
    docker stop $cname && docker rm $cname || true
    docker run --name $cname --privileged -h $cname --restart=always \
        -p $(( $STARTSSHPORT + $offset )):22 \
        -p $(( $STARTWEBPORT + $offset )):8080 \
        -d $BF_IMG /usr/sbin/sshd -D

    isolate_management ${cname}

    #add proxy details if specified
    local docker_gw_ip=$(ip -4 addr show docker0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
    if [ "$proxy_ip" != "0" ]
    then
        docker exec -e proxy_ip=$proxy_ip -e proxy_port=$proxy_port $cname \
                bash -c 'cat > /etc/apt/apt.conf.d/proxy.conf<<EOF
Acquire::http::Proxy "http://$proxy_ip:$proxy_port/";
Acquire::https::Proxy "http://$proxy_ip:$proxy_port/";
EOF
'

        docker exec $cname ip route add $proxy_ip via $docker_gw_ip table mgmt
    fi
    cspace=$(docker inspect --format {{.State.Pid}} $cname)

    # create lab network access port
    # rfkill and ip need to be added as rootLessCommands on the host
    # if Wi-Fi was associated to an SSID on the host, on pushing the interface
    # to container rfkill releases the wifi resource from host.
    sudo rfkill unblock wifi
    sudo iw phy $(cat /sys/class/net/"$dev"/phy80211/name) set netns $cspace
    docker exec $cname ip link set $dev name wlan1
    docker exec $cname ip link set wlan1 up
}

#voice container
create_container_voice () {
    #will be from /dev ACM dev name
    local dev=$1
    #keep offset as 40000
    local offset=${2:-1}
    local proxy_dir=${3:-"0"}
    local proxy_ip=${4:-"0"}

    cname=bft-node-$dev
    docker stop $cname && docker rm $cname
    docker run --name $cname --privileged -h $cname --restart=always \
        -p $(( 4000 + $offset )):22 \
        -d $BF_IMG /usr/sbin/sshd -D

    #add proxy details if specified
    local docker_gw_ip=$(ip -4 addr show docker0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
    if [ "$proxy_dir" != "0" ] && [ "$proxy_ip" != "0" ]
    then
        docker cp $proxy_dir/proxy.conf $cname:/etc/apt/apt.conf.d/
        docker exec $cname ip route add $proxy_ip via $docker_gw_ip
    fi
    docker exec $cname ln -s /dev/tty$dev  /root/line-$dev
}

[ "$IFACE" = "undefined" ] && return

echo "Creating nodes starting on vlan $START_VLAN to $END_VLAN on iface $IFACE"

for vlan in $(seq $START_VLAN $END_VLAN); do
    echo "Creating node on vlan $vlan"

    create_container_eth1_vlan $vlan

    [ "$OPTS" = "both" ] && { local_route; continue; }
    if [ $((vlan%2)) -eq 0 ]; then
        [ "$OPTS" = "even" ] && local_route
    elif [ "$OPTS" = "odd" ]; then
        local_route
    fi
done

echo "Running the command below will stop all containers and clean up everything:"
echo 'docker stop $(docker ps -q) && docker rm $(docker ps -a -q)'
