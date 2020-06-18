from boardfarm.orchestration import TestStep as TS
from boardfarm.tests.bft_base_test import BftBaseTest


class test_teardown1(BftBaseTest):
    def startMarker(self):
        pass

    def endMarker(self):
        pass

    def executionWrapper(self):
        pass

    def run(self, *args, **kwargs):
        pass

    def set_action_1(self, unset=False):
        """Test execution
        Set/Unset both will succeed
        """
        self.action1_op = [100, None][unset]
        return self.action1_op

    def set_action_2(self, unset=False):
        """Test execution method 2
        Set will suceed. Unset will fail
        """
        self.action2_op = [200, 200][unset]
        return self.action2_op

    def set_action_3(self):
        """This one will throw an exception
        """
        raise KeyError("Intended unset error")

    def test_main(self):
        print("This is runTest of Test1")

        # working with TestStep variant
        with TS(self, "execute step 1") as ts:
            ts.call(self.set_action_1)
            ts.verify(ts.result[-1].output() == 100, "step 1 verification")
        with TS(self, "execute step 2") as ts:
            ts.call(self.set_action_2)
            ts.verify(ts.result[-1].output() == 200, "step 2 verification")

    @classmethod
    def teardown_class(cls):
        obj = cls.test_obj
        cls.call(obj.set_action_1, unset=True, exp=None)
        cls.call(obj.set_action_2, unset=True, exp=None)
        cls.call(obj.set_action_3)
        # need to figure out from here how to mark test as fail
