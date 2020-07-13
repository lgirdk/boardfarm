#!/usr/bin/env python

from boardfarm.lib.bft_logging import LoggerMeta


def test_check_signature():
    class A(object, metaclass=LoggerMeta):
        sign_check = True

        def set(self, x):
            self.x = x

        def get(self, x=0):
            return self.x if self.x else x

        def show(self):
            print(self.x)

    class B(A):
        model = "lan"

        def set(self):
            """This override shouldn't work because the signature is wrong"""

            pass

        def get(self):
            return self.x

        def show(self):
            print(self.x)

    class C(object):
        model = "lan1"
        sign_check = True

        def set(self):
            """This override shouldn't work because the signature is wrong"""
            print("set class C")
            pass

        def get(self):
            print("get class D")
            return self.x

    class D(A, C):
        model = "lan1"

        def set(self, x):
            """This override shouldn't work because the signature is wrong"""
            print("set class D")
            pass

        def get(self, x=None):
            print("get class D")
            return self.x

    # creating B instance
    B()
    C()
    D()


if __name__ == "__main__":
    test_check_signature()
