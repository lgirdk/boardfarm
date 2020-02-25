#!/bin/bash -xe

for change_id in $(repo forall -r ^$GERRIT_PROJECT$ -c  'git log -n1' | grep '^Depends-on: ' | awk '{print $2}'); do
	raw=$(ssh $auto_user@$GERRIT_HOST -p $GERRIT_PORT gerrit query --format JSON --patch-sets $change_id | \
		jq -r 'if .patchSets then .patchSets[-1].ref,.project else empty end')

	if [ "$raw" = "" ]; then
		exit 1
	fi

	read -r ref proj <<<$(echo $raw)

	echo "Picking $ref from $proj"
	repo forall -r ^$proj\$ -c 'pwd && git fetch gerrit '$ref' && git rebase FETCH_HEAD && git rebase m/master'
done

rm -f .env
touch .env

if repo forall -r ^$GERRIT_PROJECT$ -c 'git log -n1' | grep '^    Environment:'; then
	echo export BFT_ARGS=$(realpath $(repo forall -r ^$GERRIT_PROJECT$ -c 'git log -n1' | grep '^    Environment:' | awk '{print $2}')) >> .env
	. ./.env
	if [ ! -f "$BFT_ARGS" ]; then
		exit 1
	fi
fi

if repo forall -r ^$GERRIT_PROJECT$ -c 'git log -n1' | grep Boards:; then
	echo export boards=\"$(repo forall -r ^$GERRIT_PROJECT$ -c 'git log -n1' | grep Boards: | sed 's/.*Boards: //g')\" >> .env
else
	export boards=$board
fi
