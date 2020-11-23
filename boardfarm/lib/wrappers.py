"""Decorators for boardfarm libraries"""


def singleton(cls):
    """Allow a class to become a decorator"""
    instances = {}

    def getinstance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)

        return instances[cls]

    return getinstance
