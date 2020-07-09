from boardfarm.exceptions import BftEnvExcKeyError, BftEnvMismatch


class EnvHelper(object):
    """
    Example env json.

    {
        "environment_def": {
            "board": {
                "software": {
                    "bootloader_image": "none",
                    "downgrade_images": [
                        "image.bin"
                    ],
                    "load_image": "image.bin",
                    "upgrade_images": [
                        "image.bin"]
                },
                }
        },
        "version": "1.0"
    }
    """
    def __init__(self, env, mirror=None):
        """Instance initialization."""
        if env is None:
            return

        assert env["version"] in ["1.0", "1.1", "1.2",
                                  2.0], "Unknown environment version!"
        self.env = env
        self.mirror = ""
        if mirror:
            self.mirror = mirror

    def get_image(self, mirror=True):
        """Get image.

        returns the desired image for this to run against concatenated with the
        site mirror for automated flashing without passing args to bft
        """
        try:
            if mirror:
                return (self.mirror + self.env["environment_def"]["board"]
                        ["software"]["load_image"])
            else:
                return self.env["environment_def"]["board"]["software"][
                    "load_image"]
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError

    def has_image(self):
        """Return true or false if the env has specified an image to load."""
        try:
            self.get_image()
            return True
        except Exception:
            return False

    def get_downgrade_image(self):
        """Return the desired downgrade image to test against."""
        try:
            return self.env["environment_def"]["board"]["software"][
                "downgrade_images"][0]
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError

    def get_upgrade_image(self):
        """Return the desired upgrade image to test against."""
        try:
            return self.env["environment_def"]["board"]["software"][
                "upgrade_images"][0]
        except (KeyError, AttributeError):
            raise BftEnvExcKeyError

    def has_upgrade_image(self):
        """Return true or false.

        if the env has specified an upgrade image to load
        """
        try:
            self.get_upgrade_image()
            return True
        except Exception:
            return False

    def has_downgrade_image(self):
        """Return true or false.

        if the env has specified an downgrade image to load
        """
        try:
            self.get_downgrade_image()
            return True
        except Exception:
            return False

    def get_software(self):
        """Get software."""
        sw = self.env["environment_def"]["board"].get("software", {})
        out = {}
        for k, v in sw.items():
            if k == "dependent_software":
                continue
            if k in ["load_image", "image_uri"]:
                out[k] = "{}{}".format(self.mirror, v)
            else:
                out[k] = v
        return out

    def get_dependent_software(self):
        """Get dependent software."""
        d = self.env["environment_def"]["board"].get("software", {})
        sw = d.get("dependent_software", {})
        out = {}
        for k, v in sw.items():
            if k in ["load_image", "image_uri"]:
                out[k] = "{}{}".format(self.mirror, v)
            else:
                out[k] = v
        return out

    def env_check(self, test_environment):
        """Test environment check.

        Given an environment (in for of a dictionary) as a parameter, checks
        if it is a subset of the environment specs contained by the EnvHelper.

        :param test_environment: the environment to be checked against the EnvHelper environment
        :type test_environment: dict

        .. note:: raises BftEnvMismatch  if the test_environment is not contained in the env helper environment
        .. note:: recursively checks dictionaries
        .. note:: A value of None in the test_environment is used as a wildcard, i.e. matches any values int the EnvHelper
        """
        def contained(env_test, env_helper, path="root"):
            if type(env_test) is dict:
                for k in env_test:
                    if k not in env_helper or not contained(
                            env_test[k], env_helper[k], path + "->" + k):
                        return False
            elif type(env_test) is list:
                # Handle case where env_test is a list and the env_helper is a value:
                # e.g. the env helper is configured in mode A
                # the test can run in A, B or C configuration modes
                if not type(env_helper) is list and env_helper in env_test:
                    return True
                # Handle case where list is [None] and we just need *some value* in the env_helper
                if env_test[0] is None and len(env_helper) > 0:
                    return True
                for i in range(len(env_test)):
                    # assumes no dicts or other structures in the list
                    if env_test[i] not in env_helper:
                        return False
            else:
                if env_test is None and env_helper is not None:
                    return True
                elif env_test == env_helper:
                    return True
                else:
                    return False

            return True

        if not contained(test_environment, self.env):
            print("---------------------")
            print(" test case env: ")
            print(test_environment)
            print(" env_helper   : ")
            print(self.env)
            print("---------------------")
            raise BftEnvMismatch()

        return True
