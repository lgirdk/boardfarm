"""Module mysql

Defines class MySQL"""
from boardfarm.lib.installers import apt_install


class MySQL:
    """Mysql database specific class"""

    def __init__(self, dev, username="root", password="test"):
        """Instance initialisation."""
        self.username = username
        self.password = password
        self.mysql_prompt = ">"
        self.default_charset = "latin1"
        self.handle = dev

    def install(self):
        """Install mysql server."""
        apt_install(self.handle, "default-mysql-server", timeout=300)

    def start(self):
        """Start the mysql server."""
        self.handle.sendline("service mysql start")
        self.handle.expect("Starting")
        self.handle.expect(self.handle.prompt)

    def stop(self):
        """Stop the mysql server."""
        self.handle.sendline("service mysql stop")
        self.handle.expect("Stopping")
        self.handle.expect(self.handle.prompt)

    def status(self):
        """Status of the mysql server."""
        self.handle.sendline("service mysql status")
        index = self.handle.expect(["stopped", "uptime"], timeout=5)
        self.handle.expect(self.handle.prompt)
        if index == 1:
            return "Running"
        return "Not running"

    def login_root_user(self):
        """Login to root user."""
        self.handle.sendline("mysql -u %s -p" % self.username)
        self.handle.expect("Enter password:")
        self.handle.sendline(self.password)
        self.handle.expect(self.mysql_prompt)

    def exit_root_user(self):
        """Exit the mysql user."""
        self.handle.sendline("exit")
        self.handle.expect(self.handle.prompt)

    def setup_root_user(self):
        """ Setup the root user."""
        self.login_root_user()
        self.exit_root_user()

    def update_user_password(self, user):
        """Update user password.

        param user: the username to be updated
        type user: string
        """
        self.login_root_user()
        self.handle.sendline(
            "SET PASSWORD FOR '%s'@'localhost' = PASSWORD('%s');"
            % (user, self.password)
        )
        self.handle.expect(self.mysql_prompt)
        self.exit_root_user()

    def check_db_exists(self, db_name):
        """Check if the name of the DB exists.

        param db_name: name of the database
        type db_name:string
        """
        self.login_root_user()
        self.handle.sendline("SHOW DATABASES LIKE '%s';" % db_name)
        index = self.handle.expect(["1 row in set", "Empty set"])
        self.exit_root_user()
        if index == 0:
            return True
        return False
