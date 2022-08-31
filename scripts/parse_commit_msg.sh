#!/bin/bash -xe

for change_id in $(repo forall -r ^$GERRIT_PROJECT$ -c  'git show --format=%b -s HEAD' | grep '^Depends-on: ' | awk '{print $2}'); do
    raw=$(ssh $auto_user@$GERRIT_HOST -p $GERRIT_PORT gerrit query --format JSON --patch-sets $change_id | \
        jq -r 'if .patchSets then .patchSets[-1].ref,.project else empty end')

    if [ "$raw" = "" ]; then
        exit 1
    fi

    read -r ref proj <<<$(echo $raw)

    echo "Picking $ref from $proj"
    repo forall -r ^$proj\$ -c "pwd && git fetch gerrit ${ref} && git checkout FETCH_HEAD"
done

rm -f .env
touch .env

if repo forall -r ^$GERRIT_PROJECT$ -c 'git show --format=%b -s HEAD' | grep ^Environment:; then
    for COMMIT_ENV in $(repo forall -r ^$GERRIT_PROJECT$ -c 'git show --format=%b -s HEAD' | grep ^Environment: | awk '{print $2}'); do
        COMMIT_ENV_PATH=$(realpath $COMMIT_ENV)
        if [ ! -f "$COMMIT_ENV_PATH" ]; then
            exit 1
        fi
        CONFIG_BOARD_MODEL=$(jq .environment_def.board.model $COMMIT_ENV_PATH | tr -d '"')
        if [ $board = $CONFIG_BOARD_MODEL ]; then
            echo export BFT_ARGS=$COMMIT_ENV_PATH >> .env
        fi
    done
fi

if repo forall -r ^$GERRIT_PROJECT$ -c 'git show --format=%b -s HEAD' | grep Boards:; then
    echo export boards=\"$(repo forall -r ^$GERRIT_PROJECT$ -c 'git show --format=%b -s HEAD' | grep Boards: | sed 's/.*Boards: //g')\" >> .env
else
    export boards=$board
fi

if repo forall -r ^$GERRIT_PROJECT$ -c 'git show --format=%b -s HEAD' | grep Features:; then
    echo export BFT_FEATURES=\"$(repo forall -r ^$GERRIT_PROJECT$ -c 'git show --format=%b -s HEAD' | grep Features: | sed 's/.*Features: //g')\" >> .env
fi

if repo forall -r ^$GERRIT_PROJECT$ -c 'git show --format=%b -s HEAD' | grep Filters:; then
    echo export BFT_FILTERS=\"$(repo forall -r ^$GERRIT_PROJECT$ -c 'git show --format=%b -s HEAD' | grep Filters: | sed 's/.*Filters: //g')\" >> .env
fi

if repo forall -r ^$GERRIT_PROJECT$ -c 'git show --format=%b -s HEAD' | grep Inventory:; then
    echo export BFT_CONFIG=\"$(repo forall -r ^$GERRIT_PROJECT$ -c 'git show --format=%b -s HEAD' | grep Inventory: | sed 's/.*Inventory: //g')\" >> .env
fi
