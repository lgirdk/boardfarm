#! /bin/bash

service mysql start
fwconsole restart

if [[ $# -gt 0 ]]; then
    exec "$@"
else
    exec /usr/sbin/sshd -D
fi
