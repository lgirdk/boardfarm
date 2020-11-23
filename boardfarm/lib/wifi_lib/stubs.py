class WiFiStub:
    """Wifi_stub."""

    apply_changes_no_delay = True

    # The above variable can tweak the behavior of the below functions
    # If it is set to True, it will apply the changes after setting wifi parameters
    # If it is set to False, it will not save any changes & apply_changes() will be skipped
    def enable_wifi(self, *args, **kwargs):
        """Stub for enabling wifi on CM.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def set_ssid(self, *args, **kwargs):
        """Stub to set SSID.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def set_broadcast(self, *args, **kwargs):
        """Stub to set broadcast.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def set_security(self, *args, **kwargs):
        """Stub to set security.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def set_password(self, *args, **kwargs):
        """Stub to set password.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def enable_channel_utilization(self, *args, **kwargs):
        """Stub to enable channel utilization.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def set_operating_mode(self, *args, **kwargs):
        """Stub to set operating mode.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def set_bandwidth(self, *args, **kwargs):
        """Stub to set bandwidth.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def set_channel_number(self, *args, **kwargs):
        """Stub to enable channel utilization.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_wifi_enabled(self, *args, **kwargs):
        """Stub to get WiFi enabled.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_ssid(self, *args, **kwargs):
        """Stub to get SSID.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_security(self, *args, **kwargs):
        """Stub to get security mode.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_password(self, *args, **kwargs):
        """Stub to get password.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_channel_utilization(self, *args, **kwargs):
        """Stub to get channel utilization.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_operating_mode(self, *args, **kwargs):
        """Stub to get operating mode.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_bandwidth(self, *args, **kwargs):
        """Stub to get bandwidth.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_broadcast(self, *args, **kwargs):
        """Stub to get the broadcast.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_channel_number(self, *args, **kwargs):
        """Stub to get the channel number.

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def prepare(self):
        """Stub to prepare.

        :param self: self object
        :type self: object
        """
        pass

    def cleanup(self):
        """Stub to cleanup.

        :param self: self object
        :type self: object
        """
        pass

    def apply_changes(self):
        """Stub used to save the configs to be modified.

        :param self: self object
        :type self: object
        """
        pass


class WiFiClientStub:
    """Wifi client stub."""

    def enable_wifi(self):
        """Wifi client stub used to enable WiFi/ make the WiFi interface UP.

        :param self: self object
        :type self: object
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def disable_wifi(self):
        """Wifi client stub used to enable WiFi/ make the WiFi interface DOWN.

        :param self: self object
        :type self: object
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def disable_and_enable_wifi(self):
        """Wifi client stub used to disable and enable WiFi/.

         Make the WiFi interface DOWN and UP

        :param self: self object
        :type self: object
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def wifi_scan(self):
        """Wifi client stub used to scan for SSIDs on a particular radio and return a list of SSID.

        Note: this code does not execute, but rather serves as an example for
        the API
        return "SSID: <ssid_name1> SSID: <ssid_name2>.."

        :param self: self object
        :type self: object
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def wifi_check_ssid(self, ssid_name):
        """Wifi client stub used to scan for particular SSID.

        Note: this code does not execute, but rather serves as an example for
        the API
        return True  if found
        return False  if not found

        :param self: self object
        :type self: object
        :param ssid_name: ssid name to be scanned for
        :type ssid_name: string
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def wifi_connect(self, ssid_name, password, security_mode):
        """Wifi client stub used to connect to wifi.

         Either with ssid name and password or with ssid name alone.

        :param self: self object
        :type self: object
        :param ssid_name: ssid name to be scanned for
        :type ssid_name: string
        :param password: password to be used to connect to SSID
        :type password: string
        :param security_mode: security mode of WiFi
        :type security_mode: string
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def wifi_connectivity_verify(self):
        """Wifi client stub used to verify wifi connectivity.

        Note : this code does not execute, but rather serves as an example for
        the API
        return True or False

        :param self: self object
        :type self: object
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def wifi_disconnect(self):
        """Wifi client stub used to disconnect WiFi.

        :param self: self object
        :type self: object
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def wifi_change_region(self, country):
        """Wifi client stub used to change the country.

        :param self: self object
        :type self: object
        :param country: country to change to
        :tSype country: string
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")
