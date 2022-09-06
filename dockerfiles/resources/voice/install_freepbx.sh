#!/bin/bash -xe

cd /usr/src/freepbx
cp -R /etc/odbc.ini /usr/src/freepbx/installlib/files/odbc.ini

# RUN asterisk and MariaDB before installing FreePBX
./start_asterisk start
service mysql start

# Install FreePBX
./install -n
fwconsole ma downloadinstall framework core
fwconsole ma download cdr
fwconsole ma install cdr
fwconsole ma downloadinstall backup callrecording conferences dashboard featurecodeadmin filestore fw_langpacks infoservices languages logfiles music recordings sipsettings soundlang voicemail
fwconsole ma downloadinstall certman userman pm2
fwconsole setting SHOWLANGUAGE 1
fwconsole chown
fwconsole reload

# Assign Access rights and fix UCP
chown -RH asterisk. /home/asterisk/.npm
touch /usr/bin/icu-config
echo "icuinfo 2>/dev/null|grep \"version\"|sed 's/.*>\(.*\)<.*/\1/g'" > /usr/bin/icu-config
chmod +x /usr/bin/icu-config
fwconsole ma downloadinstall ucp
fwconsole reload
fwconsole stop --immediate

cp -R /etc/freepbx.conf /data/etc/
rm -f /etc/freepbx.conf
chown asterisk. /data/etc/freepbx.conf
ln -s /data/etc/freepbx.conf /etc/freepbx.conf

### Set RTP ports and fix a FreePBX bug with upgrades
mysql -e 'USE asterisk; ALTER TABLE featurecodes CHANGE column helptext helptext VARCHAR(10000); INSERT INTO sipsettings (keyword, data, seq, type) VALUES ("rtpstart","'"$RTP_START"'",1,0) ON DUPLICATE KEY UPDATE data="'"$RTP_START"'";INSERT INTO sipsettings (keyword, data, seq, type) VALUES ("rtpend","'"$RTP_FINISH"'",1,0) ON DUPLICATE KEY UPDATE data="'"$RTP_FINISH"'";'
a2enmod rewrite
