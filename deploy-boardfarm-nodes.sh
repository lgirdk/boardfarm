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
