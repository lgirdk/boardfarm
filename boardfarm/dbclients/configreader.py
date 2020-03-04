# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
#!/usr/bin/env python

import re

try:
    from urllib.request import urlopen
except:
    from urllib2 import urlopen


class TestsuiteConfigReader(object):
    """Read config file (in our case testsuite.cfg) like:

      [testsuiteA]
      test1
      test2
      test1
      test2
      [testsuiteB]
      test7
      test2
      [testsuiteC]
      @testsuiteB
      test3

    And from that, create dictionary like:

      {'testsuiteA' : [test1, test2, test1, test2, ...]
       'testsuiteB' : [test7, test2, ...]
       'testsuiteC' : [test7, test2, test3, ...]
      }
    """
    def __init__(self):
        """This method initializes the self.section to empty dict.
        """
        self.section = {}

    def read(self, filenames):
        """This method reads the config which in turn uses the methods read_config for every file in the list of filenames.

        :param filenames: list of filenames to be read from.
        :type filenames: list
        """
        for f in filenames:
            try:
                self.read_config(f)
            except Exception as e:
                print(e)
                continue

    def read_config(self, fname):
        """Read local or remote (http) config file and parse into a dictionary.
           Performs the operations based on the data format available. Example: suite will be appended with "@" at begin
           if it is supposed to be called in another test suite.

        :param fname: name of the file to be read from.
        :type fname: string
        :raises: Exception
        """
        try:
            if fname.startswith("http"):
                s_config = urlopen(fname).read()
            else:
                with open(fname, 'r') as f:
                    s_config = f.read()
        except Exception as e:
            print(e)
            raise Exception("Warning: Unable to read/access %s" % fname)
        current_section = None
        for i, line in enumerate(s_config.split('\n')):
            try:
                if line == '' or re.match(r'^\s+',
                                          line) or line.startswith('#'):
                    continue
                if '[' in line:
                    current_section = re.search(r'\[(.*)\]', line).group(1)
                    if current_section not in self.section:
                        self.section[current_section] = []
                elif re.match(r'[@\w]+', line):
                    if current_section:
                        self.section[current_section].append(line)
            except Exception as e:
                print(e)
                print("Error line %s of %s" % (i + 1, fname))
                continue

        for section in self.section:
            new_section = []
            for item in self.section[section]:
                if item.startswith('@'):
                    ref_section = re.search('@(.*)', item).group(1)
                    if ref_section in self.section:
                        new_section += self.section[ref_section]
                    else:
                        print(
                            "Failed to find '%s' testsuite referenced by '%s'."
                            % (ref_section, section))
                        continue
                else:
                    new_section.append(item)
            self.section[section] = new_section

    def __str__(self):
        """The method is used to format the string representation of self object (instance).
        """
        result = []
        for name in sorted(self.section):
            result.append('* %s' % name)
            for i, x in enumerate(self.section[name]):
                result.append(' %2s %s' % (i + 1, x))
        return "\n".join(result)


if __name__ == '__main__':
    import os
    import glob
    import boardfarm

    for modname in sorted(boardfarm.plugins):
        overlay = os.path.dirname(boardfarm.plugins[modname].__file__)
        # Find testsuite config files
        filenames = glob.glob(os.path.join(overlay, 'testsuites.cfg')) + \
                      glob.glob(os.path.join(overlay, '*', 'testsuites.cfg'))

    t = TestsuiteConfigReader()
    t.read(filenames)
    print(t)
