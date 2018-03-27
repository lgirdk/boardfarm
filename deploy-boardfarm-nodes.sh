#!/bin/bash -xe

IFACE=${1:-bond0}
START_VLAN=${2:-101}
END_VLAN=${3:-144}
LOCAL_ROUTE=${4:-"both"} # both, odd, even

echo "Creating nodes starting on vlan $START_VLAN to $END_VLAN on iface $IFACE"

random_private_mac () {
	echo $1$1$1$1$1$1 | od -An -N6 -tx1 | sed -e 's/^  *//' -e 's/  */:/g' -e 's/:$//' -e 's/^\(.\)[13579bdf]/\10/'
}

local_route () {
	# TODO: This is a problem if the router network matches the host network
	host_dev=$(ip route list | grep ^default |  awk '{print $5}' )
	local_route=$(ip route | grep "dev $host_dev" | grep -v ^default | grep -v via | awk '{print $1}' | head -n1)
	docker exec $cname ip route add $local_route dev eth0 via 172.17.0.1
}

for vlan in $(seq $START_VLAN $END_VLAN); do
	echo "Creating node on vlan $vlan"

	cname=bft-node-$IFACE-$vlan
	docker stop $cname && docker rm $cname
	docker run --name $cname --privileged -h $cname --restart=always \
		-p $(( 5000 + $vlan )):22 \
		-p $(( 8000 + $vlan )):8080 \
		-d bft:node /usr/sbin/sshd -D

	sudo ip link del $IFACE.$vlan || true
	sudo ip link add link $IFACE name $IFACE.$vlan type vlan id $vlan

	cspace=$(docker inspect --format '{{.State.Pid}}' $cname)
	sudo ip link set netns $cspace dev $IFACE.$vlan
	docker exec $cname ip link set $IFACE.$vlan name eth1
	docker exec $cname ip link set dev eth1 address $(random_private_mac $vlan)

	[ "$LOCAL_ROUTE" = "both" ] && { local_route; continue; }
	if [ $((vlan%2)) -eq 0 ]; then
		[ "$LOCAL_ROUTE" = "even" ] && local_route
	elif [ "$LOCAL_ROUTE" = "odd" ]; then
		local_route
	fi
done

echo "Running the command below will stop all containers and clean up everything:"
echo 'docker stop $(docker ps -q) && docker rm $(docker ps -a -q)'
