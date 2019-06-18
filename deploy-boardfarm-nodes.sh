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
	python - <<END
import random

def randomMAC():
    mac = [ (random.randint(0x00,0xff) & 0xfe), # the lsb is 0, i.e. no multicat bit
             random.randint(0x00, 0xff),
             random.randint(0x00, 0xff),
             random.randint(0x00, 0xff),
             random.randint(0x00, 0xff),
             random.randint(0x00, 0xff) ]
    mac_to_be_decided = ':'.join(map(lambda x : hex(x)[2:].lstrip("0x").zfill(2),mac))

    return (mac_to_be_decided)

if __name__ == '__main__':
    print randomMAC()
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

	docker_dev=$(docker exec $cname ip route list | grep ^default |  awk '{print $5}' )
	docker_gw_ip=$(ip -4 addr show docker0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
	docker_dev_ip=$(docker exec $cname ip -4 addr show $docker_dev | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
	docker_nw=$(ip route | grep "dev docker0" | grep src | awk '{print $1}' | head -n1)

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
	docker exec $cname ip -6 route add default via $ipv6_default dev eth1
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
	local offset=$4

	cname=bft-node-$IFACE-$name
	docker stop $cname && docker rm $cname
	docker run --name $cname --privileged -h $cname --restart=always \
		-p $(( $STARTSSHPORT + $offset )):22 \
		-p $(( $STARTWEBPORT + $offset )):8080 \
		-d $BF_IMG /usr/sbin/sshd -D

	cspace=$(docker inspect --format {{.State.Pid}} $cname)

	# create lab network access port
	sudo ip link add tempfoo link $IFACE type macvlan mode bridge
	sudo ip link set dev tempfoo up
	sudo ip link set netns $cspace dev tempfoo
	docker exec $cname ip link set tempfoo name eth1
	docker exec $cname ip link set eth1 up
	docker exec $cname ip addr add $ip dev eth1
	docker exec $cname ip route add default via $default_route dev eth1
	docker exec $cname ping $default_route -c3
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
	local offset=$2

	cname=bft-node-$dev
	docker stop $cname && docker rm $cname
	docker run --name $cname --privileged -h $cname --restart=always \
		-p $(( $STARTSSHPORT + $offset )):22 \
		-p $(( $STARTWEBPORT + $offset )):8080 \
		-d $BF_IMG /usr/sbin/sshd -D

	cspace=$(docker inspect --format {{.State.Pid}} $cname)
	isolate_management ${cname}

	# create lab network access port
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

# helper function for spawn_container() and create_container_lan_factory()
get_iface() {
	local vlan=${1:-None}
	local ifacevlan
	if [ "$vlan" == "None" ]
	then
		ifacevlan="$IFACE"
	else
		ifacevlan="$IFACE.$vlan"
	fi
	echo "$ifacevlan"
}

# this is a helper function, this function is invoked by create_container_lan_factory
# DO NOT INVOKE THIS DIRECTLY, create_container_lan_factory will invoke this
# this function takes 3 arguments
#    $1 is the sequence value (for example 1)
#    $2 is the clan value (for example 103)
#    $3 is the name of the container (for example bft-node-enp1s0-103-1)
spawn_container() {
    local i=$1
    local vlan=$2
    local cname=$3
    local proxy_dir=${4:-"0"}
    local proxy_ip=${5:-"0"}

    local ifacevlan

    iface=$(get_iface $vlan)

    # on direct connections we space the container ports by a factor of 10 (may have many ifaces,
    # this is to avoid overlapping ports values)
    # on vlan connections we space the container ports by a factor of 100 (ATM 1 vlan iface only)
    [ "$vlan" == "None" ] && multiplier=10 || multiplier=100

    docker run --name $cname --privileged -h $cname --restart=always \
    -p $(( STARTSSHPORT  + ((i*multiplier)) + vlan )):22 \
    -p $(( STARTWEBPORT  + ((i*multiplier)) + vlan )):8080 \
    -d $BF_IMG /usr/sbin/sshd -D

    #sudo ip link add link $IFACE.$vlan name tempfoo.$i type macvtap mode bridge
    sudo ip link add link ${iface} name tempfoo.$i type macvtap mode bridge
    cspace=$(docker inspect --format '{{.State.Pid}}' $cname)


    isolate_management ${cname}
    docker exec ${cname} ip route del default

    #add proxy details if specified
    local docker_gw_ip=$(ip -4 addr show docker0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
    if [ "$proxy_dir" != "0" ] && [ "$proxy_ip" != "0" ]
    then
        docker cp $proxy_dir/proxy.conf $cname:/etc/apt/apt.conf.d/
        docker exec $cname ip route add $proxy_ip via $docker_gw_ip table mgmt
    fi

    sudo ip link set netns $cspace dev tempfoo.$i
    docker exec $cname ip link set tempfoo.$i name eth1
    docker exec $cname ip link set eth1 up
    j=0
    # if dhclient fails, retries one more time
    while [ $j -lt 2 ]
    do
        docker exec $cname dhclient -v eth1
        host_gw=$(docker exec $cname ip route list | grep ^default |  awk '{print $3}' )
        [ "X$host_gw" != "X" ] && break
        j=$((j+1))
    done
    docker exec $cname ping -c 3 $host_gw
}

destroy_container_lan_factory() {
    local vlan=${1:None}
    local count=${2:-0}
    local ifacevlan

    ifacevlan=$(get_iface $vlan)

    local suffix
    if [[ "$ifacevlan" == *.* ]]
    then
        suffix=`echo "$ifacevlan" | tr '.' '-'`
        l=`docker ps -f name=bft-node-$suffix -aq`
    else
        l=`docker ps -f name=bft-node-$ifacevlan -aq`
        suffix=${ifacevlan}"-lan"
    fi
    docker stop $l && docker rm $l
    echo "$suffix"
}

# this is the container factory, this function takes the following arguments
#    $1 is the vlan number (for example 103)
#    $2 is how many containers we want to create ON THE SAME VLAN
# so if you want to create 33 containers on vlan 103 you will use this as follow:
#
#    set -x ; create_container_lan_factory 103 32 ;set +x

create_container_lan_factory() {
    local vlan=${1:None}
    local count=${2:-0}
    local proxy_dir=${3:-"0"}
    local proxy_ip=${4:-"0"}
    local ifacevlan

    ifacevlan=$(get_iface $vlan)

    # if no vlan is provided skip the following
    if [ "$vlan" != "None" ]
    then
        sudo ip link del $ifacevlan || true
        sudo ip link add name $ifacevlan link $IFACE type vlan id $vlan # needs TLC
        sudo ip link set $ifacevlan up
    fi
    echo "Stop all containers for $ifacevlan"

    # container naming
    # direct: bft-node-<iface>-lan-<count>    e.g.: bft-node-enx503eaa8b7ae4-lan-0
    # vlan:   bft-node-<iface>-<vlan>-<count> e.g.: bft-node-enp1s0-104-1
    local suffix

    if [[ "$ifacevlan" == *.* ]]
    then
        suffix=`echo "$ifacevlan" | tr '.' '-'`
        l=`docker ps -f name=bft-node-$suffix -aq`
    else
        l=`docker ps -f name=bft-node-$ifacevlan -aq`
        suffix=${ifacevlan}"-lan"
    fi
    docker stop $l && docker rm $l

    for i in $( seq 0 $count )
    do
        cname=bft-node-$suffix-$i

        # WAIT for the container to be fully instantiated
        spawn_container $i $vlan $cname $proxy_dir $proxy_ip

        # The following line is commented out BECAUSE
        # if many containers send the DHCP request close to each other
        # the cable modem DHCP server FAILS to offer ip addresses
        #
        #spawn_container $i $vlan $cname > /tmp/${cname}.log  2>&1 &
    done
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
