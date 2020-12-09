class ISIPCenter:
    """Sipserver Interface"""

    def sipserver_install(self):
        """Install sipserver."""
        pass

    def sipserver_configuration(self):
        """Configure sipserver."""
        pass

    def sipserver_start(self):
        """Start the server"""
        pass

    def sipserver_stop(self):
        """Stop the server."""
        pass

    def sipserver_restart(self):
        """Restart the server."""
        pass

    def sipserver_status(self):
        """Print the status of the server."""
        pass

    def sipserver_kill(self):
        """Kill the server."""
        pass

    def sipserver_user_add(self, user, password: str):
        """Add user to the directory."""
        pass

    def sipserver_user_update(self, user: str, password: str):
        """Remove user from the directory."""
        pass

    def sipserver_user_registration_status(self, user: str) -> str:
        """Print the registration status."""
        pass
