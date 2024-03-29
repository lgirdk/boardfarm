# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import random

from boardfarm.devices import prompt
from boardfarm.lib import installers
from boardfarm.tests import rootfs_boot


class RandomWebBrowse(rootfs_boot.RootFSBootTest):
    """Created light web traffic."""

    def runTest(self):
        """Run Test to Create light web traffic."""
        board = self.dev.board
        lan = self.dev.lan

        installers.apt_install(lan, "wget")

        urls = [
            "www.amazon.com",
            "www.apple.com",
            "www.baidu.com",
            "www.bing.com",
            "www.cnn.com",
            "www.ebay.com",
            "www.facebook.com",
            "www.google.com",
            "www.imdb.com",
            "www.imgur.com",
            "www.instagram.com",
            "www.linkedin.com",
            "www.microsoft.com",
            "www.nbcnews.com",
            "www.netflix.com",
            "www.pinterest.com",
            "www.reddit.com",
            "www.twitter.com",
            "www.wikipedia.org",
            "www.yahoo.com",
        ]
        random.shuffle(urls)
        user = (
            "Mozilla/5.0 (Windows NT 6.1; WOW64; rv:39.0) Gecko/20100101 Firefox/39.0"
        )
        cmd = (
            "wget -Hp http://%(url)s "
            + "-e robots=off "
            + "-P /tmp/webbrowse-test "
            + "-T 10 "
            + "--header='Accept: text/html' "
            + "-U '%(user)s' "
            + "2>&1 | tail -1"
        )
        for url in urls:
            lan.sendline("mkdir -p /tmp/webbrowse-test")
            print(f"\n{url}")
            tmp = cmd % {"url": url, "user": user}
            lan.sendline(tmp)
            try:
                lan.expect("Downloaded:", timeout=20)
            except Exception:
                lan.sendcontrol("c")
            lan.expect(prompt)
            lan.sendline("rm -rf /tmp/webbrowse-test")
            lan.expect(prompt)

            board.touch()
