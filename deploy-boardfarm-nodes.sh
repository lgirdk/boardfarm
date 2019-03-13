#!/bin/bash -xe

IFACE=${1:-undefined}
START_VLAN=${2:-101}
END_VLAN=${3:-144}
OPTS=${4:-"both"} # both, odd, even, odd-dhcp, even-dhcp
BRINT=br-bft
BF_IMG=${BF_IMG:-"bft:node"}
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null && pwd )"

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
        docker0=$(ip -4 addr show docker0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
        # moving the default route for eth0 (docker0 interface) and add it to table 102
        docker exec $cname ip route del  default
        docker exec $cname ip route add default  dev eth0 via $docker0 table 102
        docker exec $cname ip rule add from $(docker exec $cname ip route|awk '{print $1}') table 102
}

# eth0 is docker private network, eth1 is vlan on specific interface
create_container_eth1_vlan () {
	local vlan=$1
	local offset=${2:-0}

	cname=bft-node-$IFACE-$vlan-$offset
	docker stop $cname && docker rm $cname
	docker run --name $cname --privileged -h $cname --restart=always \
		-p $(( 5000 + $offset + $vlan )):22 \
		-p $(( 8000 + $offset + $vlan )):8080 \
		-d $BF_IMG /usr/sbin/sshd -D

	sudo ip link del $IFACE.$vlan || true
	sudo ip link add link $IFACE name $IFACE.$vlan type vlan id $vlan

	cspace=$(docker inspect --format '{{.State.Pid}}' $cname)
	sudo ip link set netns $cspace dev $IFACE.$vlan
	docker exec $cname ip link set $IFACE.$vlan name eth1
	docker exec $cname ip link set dev eth1 address $(random_private_mac $vlan)
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
		-p $(( 5000 + $offset + $vlan )):22 \
		-p $(( 8000 + $offset + $vlan )):8080 \
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

	cname=bft-node-$IFACE-$name
	docker stop $cname && docker rm $cname
	docker run --name $cname --privileged -h $cname --restart=always \
		-d --network=none $BF_IMG /usr/sbin/sshd -D

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
		-p $(( 5000 + $offset )):22 \
		-p $(( 8000 + $offset )):8080 \
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
		-p $(( 5000 + $offset )):22 \
		-p $(( 8000 + $offset )):8080 \
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
		-p $(( 5000 + $offset )):22 \
		-p $(( 8000 + $offset )):8080 \
		-d $BF_IMG /usr/sbin/sshd -D

	cspace=$(docker inspect --format {{.State.Pid}} $cname)

	# create lab network access port
	sudo iw phy $(cat /sys/class/net/"$dev"/phy80211/name) set netns $cspace
	docker exec $cname ip link set $dev name wlan1
	docker exec $cname ip link set wlan1 up
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
