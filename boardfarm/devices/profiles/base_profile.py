class BaseProfile(object):
    profile = {}

    @classmethod
    def configure_profile(
        cls, instance, on_boot=None, pre_boot=None, post_boot=None, hosts=None
    ):
        # check if profile is preconfigured
        # device can have multiple profiles
        # each profile maintains an entry with key as it's model name
        # always deal with instance's profile

        if "profile" not in instance.__dict__:
            # initialize a profile for the instance
            instance.profile = {}

        if instance.name not in instance.profile:
            instance.profile[instance.name] = {}
        profile = instance.profile[instance.name]

        # add a key for current profile model
        profile[cls.model] = cls.profile
        if on_boot:
            cls.profile["on_boot"] = on_boot
        if pre_boot:
            cls.profile["pre_boot"] = pre_boot
        if post_boot:
            cls.profile["post_boot"] = post_boot
        if hosts:
            cls.profile["hosts"] = hosts
