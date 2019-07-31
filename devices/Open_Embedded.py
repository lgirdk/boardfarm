import linux, os, re
import pexpect

class OpenEmbedded(linux.LinuxDevice):
    '''OE core implementation'''

    def reset(self, break_into_uboot=False):
        '''Power-cycle this device.'''
        if not break_into_uboot:
            self.power.reset()
            return
        for attempt in range(3):
            try:
                self.power.reset()
                self.expect('U-Boot', timeout=30)
                self.expect('Hit any key ')
                self.sendline('\n\n\n\n\n\n\n') # try really hard
                self.expect(self.uprompt, timeout=4)
                # Confirm we are in uboot by typing any command.
                # If we weren't in uboot, we wouldn't see the command
                # that we type.
                self.sendline('echo FOO')
                self.expect('echo FOO', timeout=4)
                self.expect(self.uprompt, timeout=4)
                return
            except Exception as e:
                print(e)
                print("\nWe appeared to have failed to break into U-Boot...")

    def get_memfree(self):
        '''Return the kB of free memory.'''
        # free pagecache, dentries and inodes for higher accuracy
        self.sendline('\nsync; echo 3 > /proc/sys/vm/drop_caches')
        self.expect('drop_caches')
        self.expect(self.prompt)
        self.sendline('cat /proc/meminfo | head -2')
        self.expect('MemFree:\s+(\d+) kB')
        memFree = self.match.group(1)
        self.expect(self.prompt)
        return int(memFree)

    def install_package(self, fname):
        '''Install OpenWrt package (opkg).'''
        target_file = fname.replace('\\', '/').split('/')[-1]
        new_fname = self.prepare_file(fname)
        local_file = self.tftp_get_file(self.tftp_server, new_fname, timeout=60)
        # opkg requires a correct file name
        self.sendline("mv %s %s" % (local_file, target_file))
        self.expect(self.prompt)
        self.sendline("opkg install --force-downgrade %s" % target_file)
        self.expect(['Installing', 'Upgrading', 'Downgrading'])
        self.expect(self.prompt, timeout=60)
        self.sendline("rm -f /%s" % target_file)
        self.expect(self.prompt)

    def check_memory_addresses(self):
        '''Check/set memory addresses and size for proper flashing.'''
        pass

    def flash_uboot(self, uboot):
        raise Exception('Code not written for flash_uboot for this board type, %s' % self.model)

    def flash_rootfs(self, ROOTFS):
        raise Exception('Code not written for flash_rootfs for this board type, %s' % self.model)

    def flash_linux(self, KERNEL):
        raise Exception('Code not written for flash_linux for this board type, %s.' % self.model)

    def flash_meta(self, META_BUILD, wan, lan):
        raise Exception('Code not written for flash_meta for this board type, %s.' % self.model)

    def wait_for_network(self):
        '''Wait until network interfaces have IP Addresses.'''
        for interface in [self.wan_iface, self.lan_iface]:
            for i in range(5):
                try:
                    if interface is not None:
                        ipaddr = self.get_interface_ipaddr(interface).strip()
                        if not ipaddr:
                            continue
                        self.sendline("route -n")
                        self.expect(interface, timeout=2)
                        self.expect(self.prompt)
                except pexpect.TIMEOUT:
                    print("waiting for wan/lan ipaddr")
                else:
                    break

    def network_restart(self):
        '''Restart networking.'''
        self.sendline('\nifconfig')
        self.expect('HWaddr', timeout=10)
        self.expect(self.prompt)
        self.sendline('/etc/init.d/network restart')
        self.expect(self.prompt, timeout=40)
        self.sendline('ifconfig')
        self.expect(self.prompt)
        self.wait_for_network()

    def boot_linux(self, rootfs=None, bootargs=""):
        print("\nWARNING: We don't know how to boot this board to linux "
              "please write the code to do so.")

    def wait_for_linux(self):
        '''Verify Linux starts up.'''
        i = self.expect(['Reset Button Push down', 'Linux version', 'Booting Linux', 'Starting kernel ...', 'Kernel command line specified:'], timeout=45)
        if i == 0:
            self.expect('httpd')
            self.sendcontrol('c')
            self.expect(self.uprompt)
            self.sendline('boot')
        i = self.expect(['U-Boot', 'login:', 'Please press Enter to activate this console'] + self.prompt, timeout=150)
        if i == 0:
            raise Exception('U-Boot came back when booting kernel')
        elif i == 1:
            self.sendline('root')
            if 0 == self.expect(['assword:'] + self.prompt):
                self.sendline('password')
                self.expect(self.prompt)

        # Give things time to start or crash on their own.
        # Some things, like wifi, take a while.
        self.expect(pexpect.TIMEOUT, timeout=40)
        self.sendline('\r')
        self.expect(self.prompt)
        self.sendline('uname -a')
        self.expect('Linux ')
        self.expect(self.prompt)

    def wait_for_mounts(self):
        '''wait for overlay to finish mounting'''
        for i in range(5):
            try:
                board.sendline('mount')
                board.expect_exact('overlayfs:/overlay on / type overlay', timeout=15)
                board.expect(prompt)
                break
            except:
                pass
        else:
                print("WARN: Overlay still not mounted")

    def get_dns_server(self):
        '''get dns server ip '''
        return "%s" % lan_gateway

    def get_dns_server_upstream(self):
        '''Get the IP of name server'''
        self.sendline('cat /etc/resolv.conf')
        self.expect('nameserver (.*)\r\n', timeout=5)
        ret = self.match.group(1)
        self.expect(self.prompt)
        return ret

    def touch(self):
        '''Keeps consoles active, so they don't disconnect for long running activities'''
        self.sendline()

    def get_user_id(self, user_id):
        '''Get the status of the user id in the device'''
        self.sendline('cat /etc/passwd | grep -w ' + user_id)
        idx = self.expect([user_id] + self.prompt)
        if idx == 0:
            self.expect(self.prompt)
        return 0 == idx

    def get_nf_conntrack_conn_count(self):
        '''Get the total number of connections in the network '''
        pp = self.get_pp_dev()

        for not_used in range(5):
            try:
                pp.sendline('cat /proc/sys/net/netfilter/nf_conntrack_count')
                pp.expect_exact('cat /proc/sys/net/netfilter/nf_conntrack_count', timeout=2)
                pp.expect(pp.prompt, timeout=15)
                ret = int(pp.before.strip())

                self.touch()
                return ret
            except:
                continue
            else:
                raise Exception("Unable to extract nf_conntrack_count!")

    def get_proc_vmstat(self, pp=None):
        # could be useful for both cores
        if pp is None:
            pp = self.get_pp_dev()

        for not_used in range(5):
            try:
                pp.sendline('cat /proc/vmstat')
                pp.expect_exact('cat /proc/vmstat')
                pp.expect(pp.prompt)
                results = re.findall('(\w+) (\d+)', pp.before)
                ret = {}
                for key, value in results:
                    ret[key] = int(value)

                return ret
            except Exception as e:
                print(e)
                continue
            else:
                raise Exception("Unable to parse /proc/vmstat!")

