#!/usr/bin/env python
"""Unit tests for boardfarm.lib.env_helper.py."""
import boardfarm.exceptions
import pytest
from boardfarm.lib import env_helper


class TestEnvHelper_env_check:
    """Suite of tests for boardfarm.lib.EnvHelper.env_check()."""

    env_with_devices = {
        "environment_def": {
            "board": {
                "software": {
                    "bootloader_image": "Some_bios_image.bin",
                    "downgrade_images": ["image.bin"],
                    "load_image": "image.bin",
                    "upgrade_images": ["image.bin"],
                },
                "prov_mode": "dual",
            },
            "devices": {"lan": True, "wlan": True},
        },
        "version": "1.0",
    }

    env_no_devices = {
        "environment_def": {
            "board": {
                "software": {
                    "bootloader_image": "Some_bios_image.bin",
                    "downgrade_images": ["image.bin"],
                    "load_image": "image.bin",
                    "upgrade_images": ["image.bin"],
                },
                "prov_mode": "dual",
            }
        },
        "version": "1.0",
    }

    env_multiple_images = {
        "environment_def": {
            "board": {
                "software": {
                    "bootloader_image": "Some_bios_image.bin",
                    "downgrade_images": ["image1", "image2", "image3", "image4"],
                    "load_image": "image.bin",
                    "upgrade_images": ["imageA.bin", "imageB.bin"],
                },
                "prov_mode": "dual",
            }
        },
        "version": "1.0",
    }

    env_prov_mode_dual = {
        "environment_def": {"board": {"eRouter_prov_mode": "dual",},},
        "version": "1.0",
    }

    env_prov_mode_ipv4 = {
        "environment_def": {"board": {"eRouter_prov_mode": "ipv4",},},
        "version": "1.0",
    }

    env_prov_mode_bridge = {
        "environment_def": {"board": {"eRouter_prov_mode": "bridge",},},
        "version": "1.0",
    }

    env_prov_mode_none = {
        "environment_def": {"board": {"eRouter_prov_mode": None,},},
        "version": "1.0",
    }

    # Creates a few environments sets and keep them static, this will mimic
    # the real world EnvHelper class usage
    eh_with_devs = env_helper.EnvHelper(env_with_devices)
    eh_no_devs = env_helper.EnvHelper(env_with_devices)
    eh_multiple_images = env_helper.EnvHelper(env_multiple_images)
    eh_prov_mode_dual = env_helper.EnvHelper(env_prov_mode_dual)
    eh_prov_mode_ipv4 = env_helper.EnvHelper(env_prov_mode_ipv4)
    eh_prov_mode_bridge = env_helper.EnvHelper(env_prov_mode_bridge)
    eh_prov_mode_none = env_helper.EnvHelper(env_prov_mode_none)

    def test_env_check_is_a_subset(self):
        """The test env IS a subset of the EnvHelper."""
        tcenv = {
            "environment_def": {
                "board": {
                    "software": {"bootloader_image": "Some_bios_image.bin"},
                    "prov_mode": "dual",
                },
                "devices": {"lan": True},
            },
            "version": "1.0",
        }
        assert self.eh_with_devs.env_check(tcenv)

    def test_env_check_is_not_a_subset_nested_value(self):
        """Test env is NOT subset of EnvHelper (as
        ['environment_def']['devices']['lan'] values differ) and BftEnvMismatch
        must be raised"""
        tcenv = {
            "environment_def": {
                "board": {
                    "software": {"bootloader_image": "Some_bios_image.bin"},
                    "prov_mode": "dual",
                },
                # Must detect this difference
                "devices": {"lan": False},
            },
            "version": "1.0",
        }
        with pytest.raises(boardfarm.exceptions.BftEnvMismatch):
            self.eh_with_devs.env_check(tcenv)

    def test_env_check_is_not_a_subset_top_value(self):
        """Test env is NOT subset of EnvHelper (as ['version'] values differ)
        and BftEnvMismatch must be raised"""
        tcenv = {"version": "2.0"}
        with pytest.raises(boardfarm.exceptions.BftEnvMismatch):
            self.eh_no_devs.env_check(tcenv)

    def test_env_check_is_a_subset_with_lists(self):
        """Test env is a subset of EnvHelper (and has lists values)."""
        tcenv = {
            "environment_def": {
                "board": {
                    "software": {"downgrade_images": ["image1", "image3"]},
                    "prov_mode": "dual",
                }
            },
            "version": "1.0",
        }
        assert self.eh_multiple_images.env_check(tcenv)

    def test_env_check_is_not_a_subset_with_lists(self):
        """Test env is NOT a subset of EnvHelper (and has lists values), as the
        list of images are not contained in the EnvHelper"""
        tcenv = {
            "environment_def": {
                "board": {
                    "software": {
                        # one image name is different
                        "downgrade_images": ["image", "image3"]
                    },
                    "prov_mode": "dual",
                }
            },
            "version": "1.0",
        }
        with pytest.raises(boardfarm.exceptions.BftEnvMismatch):
            self.eh_multiple_images.env_check(tcenv)

    def test_env_check_is_a_subset_with_lists_wildcard(self):
        """Test env is a subset of EnvHelper (and has lists values), and the
        test env accepts ANY downgrade images in the EnvHelper"""
        tcenv = {
            "environment_def": {
                "board": {"software": {"downgrade_images": [None]}, "prov_mode": "dual"}
            },
            "version": "1.0",
        }
        assert self.eh_multiple_images.env_check(tcenv)

    def test_env_check_is_a_subset__with_lists_and_value_has_wildcard(self):
        """Test env is a subset of EnvHelper (and has lists values), and the
        test env accepts ANY prov_mode in the EnvHelper"""
        tcenv = {
            "environment_def": {
                "board": {
                    "software": {"downgrade_images": ["image3", "image4"]},
                    "prov_mode": None,
                }
            },
            "version": "1.0",
        }
        assert self.eh_multiple_images.env_check(tcenv)

    def test_env_is_subest_of_test_erotuter_prov_mode_dual(self):
        """Test env is a subset of EnvHelper and the erotuter_prov_mode
        and the EnvHelper erotuter_prov_mode is one of the test env prov
        modes"""
        tcenv = {
            "environment_def": {
                "board": {"eRouter_prov_mode": ["dual", "ipv4", "ipv6"]}
            }
        }
        assert self.eh_prov_mode_dual.env_check(tcenv)

    def test_env_is_subset_of_test_erotuter_prov_mode_ipv4(self):
        """Test env is a subset of EnvHelper and the erotuter_prov_mode
        and the EnvHelper erotuter_prov_mode is one of the test env prov
        modes"""
        tcenv = {
            "environment_def": {
                "board": {"eRouter_prov_mode": ["dual", "ipv4", "ipv6"]}
            }
        }
        assert self.eh_prov_mode_ipv4.env_check(tcenv)

    def test_env_is_NOT_subset_of_test_erotuter_prov_mode_bridge(self):
        """Test env is a subset of EnvHelper and the erotuter_prov_mode
        and the EnvHelper erotuter_prov_mode is one of the test env prov
        modes"""
        tcenv = {
            "environment_def": {
                # this is checked against 'bridge' and MUST fail
                "board": {"eRouter_prov_mode": ["dual", "ipv4", "ipv6"]}
            }
        }
        with pytest.raises(boardfarm.exceptions.BftEnvMismatch):
            self.eh_prov_mode_bridge.env_check(tcenv)

    def test_env_key_is_NOT_in_EnvHelper(self):
        """Test env has a key that is not in the EnvHelper, MUST throw a
        BftEnvMismatch!!!"""
        tcenv = {
            "non_existing_key": True,
            "environment_def": {"board": {"prov_mode": "dual"}},
        }
        with pytest.raises(boardfarm.exceptions.BftEnvMismatch):
            self.eh_multiple_images.env_check(tcenv)

    def test_env_is_NOT_a_dict(self):
        """Test env is not a dict , MUST throw a BftEnvMismatch!!!"""
        tcenv = "this is not a dict"

        with pytest.raises(boardfarm.exceptions.BftEnvMismatch):
            self.eh_multiple_images.env_check(tcenv)

    def test_env_helper_has_none_value(self):
        """Test against an EnvHelper with a None value, MUST throw a BftEnvMismatch!!!
        Probably EnvHelper schema will catch this"""
        tcenv = {
            "environment_def": {"board": {"eRouter_prov_mode": "some_prov",},},
            "version": "1.0",
        }
        with pytest.raises(boardfarm.exceptions.BftEnvMismatch):
            self.eh_prov_mode_none.env_check(tcenv)

    def test_env_helper_is_list_and_testenv_is_value_match(self):
        """If the EnvHelper is a value (e.g. 1 FW image) and the test
        env has a list, where 1 value matches the EnvHelper"""
        tcenv = {
            "environment_def": {
                "board": {
                    "software": {"load_image": ["image.bin", "image3", "image4"]}
                },
            },
            "version": "1.0",
        }
        assert self.eh_multiple_images.env_check(tcenv)

    def test_env_helper_is_list_and_testenv_is_value_not_match(self):
        """If the EnvHelper is a value (e.g. 1 FW image) and the test
        env has a list, where 1 value matches the EnvHelper"""
        tcenv = {
            "environment_def": {
                "board": {
                    "software": {"load_image": ["image1.bin", "image3", "image4"]}
                },
            },
            "version": "1.0",
        }
        with pytest.raises(boardfarm.exceptions.BftEnvMismatch):
            self.eh_multiple_images.env_check(tcenv)
