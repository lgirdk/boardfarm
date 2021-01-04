""" Module sipcenter_interface

Defines the Sipcenter interface"""


class ISIPCenter:
    """Sipserver Interface"""

    def __init__(self):
        """init class"""
        pass

    def sipserver_install(self):
        """Install sipserver."""
        raise NotImplementedError

    def sipserver_purge(self):
        """To purge the sipserver installation."""
        raise NotImplementedError

    def sipserver_configuration(self):
        """Configure sipserver."""
        raise NotImplementedError

    def sipserver_start(self):
        """Start the server"""
        raise NotImplementedError

    def sipserver_stop(self):
        """Stop the server."""
        raise NotImplementedError

    def sipserver_restart(self):
        """Restart the server."""
        raise NotImplementedError

    def sipserver_status(self):
        """Return the status of the server."""
        raise NotImplementedError

    def sipserver_kill(self):
        """Kill the server."""
        raise NotImplementedError

    def sipserver_user_add(self, user, password):
        """Add user to the directory."""
        raise NotImplementedError

    def sipserver_user_update(self, user, password):
        """Remove user from the directory."""
        raise NotImplementedError

    def sipserver_user_registration_status(self, user, ip_address):
        """Return the registration status."""
        raise NotImplementedError
