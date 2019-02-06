import rootfs_boot

from devices import board

class IPTablesDump(rootfs_boot.RootFSBootTest):
    '''Dumps all IPTables rules with stats'''
    def runTest(self):
        pp = board.get_pp_dev()
        for tbl in ['filter', 'nat', 'mangle', 'raw', 'security']:
            pp.sendline('iptables -n -t %s -L -v; echo DONE' % tbl)
            pp.expect_exact('echo DONE')
            pp.expect_exact('DONE')
            pp.expect(pp.prompt)

class IPTablesFlushMangle(rootfs_boot.RootFSBootTest):
    '''Flushes mangle table'''
    def runTest(self):
        pp = board.get_pp_dev()
        pp.sendline('iptables -t mangle -F; iptables -t mangle -X')
        pp.expect(pp.prompt)
