#!/bin/bash -xe

IFACE=${1:-undefined}
START_VLAN=${2:-101}
END_VLAN=${3:-144}
OPTS=${4:-"both"} # both, odd, even, odd-dhcp, even-dhcp
BRINT=br-bft

random_private_mac () {
	echo $1$1$1$1$1$1 | od -An -N6 -tx1 | sed -e 's/^  *//' -e 's/  */:/g' -e 's/:$//' -e 's/^\(.\)[13579bdf]/\10/'
}

local_route () {
	# TODO: This is a problem if the router network matches the host network
	host_dev=$(ip route list | grep ^default |  awk '{print $5}' )
	local_route=$(ip route | grep "dev $host_dev" | grep src | awk '{print $1}' | head -n1)
	docker0=$(ip -4 addr show docker0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
	docker exec $cname ip route add $local_route dev eth0 via $docker0
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
		-d bft:node /usr/sbin/sshd -D

	sudo ip link del $IFACE.$vlan || true
	sudo ip link add link $IFACE name $IFACE.$vlan type vlan id $vlan

	cspace=$(docker inspect --format '{{.State.Pid}}' $cname)
	sudo ip link set netns $cspace dev $IFACE.$vlan
	docker exec $cname ip link set $IFACE.$vlan name eth1
	docker exec $cname ip link set dev eth1 address $(random_private_mac $vlan)
}

# eth0/eth1 are both dhcp on the main network
create_container_eth1_dhcp () {
	local vlan=$1

        cname=bft-node-$IFACE-$vlan
        docker stop $cname && docker rm $cname
        docker run --name $cname --privileged -h $cname --restart=always \
                -d --network=none bft:node /usr/sbin/sshd -D

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
		-d --network=none bft:node /usr/sbin/sshd -D

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
