#!/usr/bin/env python3
import json
import os
import time
import unittest

from plumbum import FG, local
from plumbum.cmd import cat, docker
from plumbum.commands.processes import ProcessExecutionError

# Make sure all paths are relative to tests dir
local.cwd.chdir(os.path.dirname(__file__))
certgen = local["./certgen"]


class PostgresAutoconfCase(unittest.TestCase):
    """Test behavior for this docker image"""
    def setUp(self):
        with local.cwd(local.cwd / ".."):
            print("Building image")
            local["./hooks/build"] & FG
        docker("network", "create", "lan")
        docker("network", "create", "wan")
        self.version = os.environ["DOCKER_TAG"]
        self.image = "tecnativa/postgres-autoconf:{}".format(self.version),
        self.cert_files = {
            "client.ca.cert.pem",
            "server.cert.pem",
            "server.key.pem",
        }
        return super().setUp()

    def tearDown(self):
        try:
            print("Postgres container logs:")
            docker["container", "logs", self.postgres_container] & FG
            docker["container", "stop", self.postgres_container] & FG
            docker["container", "rm", self.postgres_container] & FG
        except AttributeError:
            pass  # No postgres daemon
        docker("network", "rm", "lan", "wan")
        return super().tearDown()

    def _generate_certs(self):
        """Generate certificates for testing the image."""
        certgen("example.com", "test_user")

    def _check_local_connection(self):
        """Check that local connection works fine."""
        # The 1st test could fail while postgres boots
        for attempt in range(10):
            try:
                time.sleep(5)
                # Test local connections via unix socket work
                self.assertEqual("1\n", docker(
                    "container", "exec", self.postgres_container, "psql",
                    "--command", "SELECT 1",
                    "--dbname", "test_db",
                    "--no-align",
                    "--tuples-only",
                    "--username", "test_user",
                ))
            except AssertionError:
                if attempt < 9:
                    print("Failure number {}. Retrying...".format(attempt))
                else:
                    raise
            else:
                continue

    def _check_password_auth(self, host=None):
        """Test connection with password auth work fine."""
        if not host:
            # Connect via LAN by default
            host = self.postgres_container[:12]
        self.assertEqual("1\n", docker(
            "container", "run",
            "--network", "lan",
            "-e", "PGDATABASE=test_db",
            "-e", "PGPASSWORD=test_password",
            "-e", "PGSSLMODE=disable",
            "-e", "PGUSER=test_user",
            self.image, "psql",
            "--host", host,
            "--command", "SELECT 1",
            "--no-align",
            "--tuples-only",
        ))

    def _connect_wan_network(self, alias="example.com"):
        """Bind a new network, to imitate WAN connections."""
        docker(
            "network", "connect",
            "--alias", alias,
            "wan",
            self.postgres_container,
        )

    def _check_cert_auth(self):
        """Test connection with cert auth work fine."""
        # Test connection with cert auth works fine
        self.assertEqual("1\n", docker(
            "container", "run",
            "--network", "wan",
            "-e", "PGDATABASE=test_db",
            "-e", "PGSSLCERT=/certs/client.cert.pem",
            "-e", "PGSSLKEY=/certs/client.key.pem",
            "-e", "PGSSLMODE=verify-full",
            "-e", "PGSSLROOTCERT=/certs/server.ca.cert.pem",
            "-e", "PGUSER=test_user",
            "-v", "{}:/certs".format(local.cwd),
            self.image, "psql",
            "--host", "example.com",
            "--command", "SELECT 1",
            "--no-align",
            "--tuples-only",
        ))

    def test_server_certs_var(self):
        """Test server enables cert authentication through env vars."""
        with local.tempdir() as tdir:
            with local.cwd(tdir):
                self._generate_certs()
                certs_var = {name: cat(name) for name in self.cert_files}
                self.postgres_container = docker(
                    "container", "run",
                    "-d", "--network", "lan",
                    "-e", "CERTS=" + json.dumps(certs_var),
                    "-e", "POSTGRES_DB=test_db",
                    "-e", "POSTGRES_PASSWORD=test_password",
                    "-e", "POSTGRES_USER=test_user",
                    self.image,
                ).strip()
                self._check_local_connection()
                self._check_password_auth()
                self._connect_wan_network()
                self._check_cert_auth()

    def test_server_certs_mount(self):
        """Test server enables cert authentication through file mounts."""
        with local.tempdir() as tdir:
            with local.cwd(tdir):
                self._generate_certs()
                cert_vols = [
                    "-v{0}/{1}:/etc/postgres/{1}".format(local.cwd, cert)
                    for cert in [
                        "client.ca.cert.pem",
                        "server.cert.pem",
                        "server.key.pem",
                    ]
                ]
                self.postgres_container = docker(
                    "container", "run",
                    "-d", "--network", "lan",
                    "-e", "POSTGRES_DB=test_db",
                    "-e", "POSTGRES_PASSWORD=test_password",
                    "-e", "POSTGRES_USER=test_user",
                    *cert_vols,
                    self.image,
                ).strip()
                self._check_local_connection()
                self._check_password_auth()
                self._connect_wan_network()
                self._check_cert_auth()

    def test_no_certs_lan(self):
        """Normal configuration without certs works fine."""
        self.postgres_container = docker(
            "container", "run", "-d",
            "--network", "lan",
            "-e", "POSTGRES_DB=test_db",
            "-e", "POSTGRES_PASSWORD=test_password",
            "-e", "POSTGRES_USER=test_user",
            self.image,
        ).strip()
        self._check_local_connection()
        self._check_password_auth()
        self._connect_wan_network()
        with self.assertRaises(ProcessExecutionError):
            self._check_password_auth("example.com")

    def test_no_certs_wan(self):
        """Unencrypted WAN access works (although this is dangerous)."""
        self.postgres_container = docker(
            "container", "run", "-d",
            "--network", "lan",
            "-e", "POSTGRES_DB=test_db",
            "-e", "POSTGRES_PASSWORD=test_password",
            "-e", "POSTGRES_USER=test_user",
            "-e", "WAN_AUTH_METHOD=md5",
            "-e", "WAN_CONNECTION=host",
            self.image,
        ).strip()
        self._check_local_connection()
        self._check_password_auth()
        self._connect_wan_network()
        with self.assertRaises(ProcessExecutionError):
            self._check_password_auth("example.com")

    def test_certs_falsy_lan(self):
        """Configuration with falsy values for certs works fine."""
        self.postgres_container = docker(
            "container", "run", "-d",
            "--network", "lan",
            "-e", "POSTGRES_DB=test_db",
            "-e", "POSTGRES_PASSWORD=test_password",
            "-e", "POSTGRES_USER=test_user",
            "-e", "CERTS={}".format(json.dumps({
                "client.ca.cert.pem": False,
                "server.cert.pem": False,
                "server.key.pem": False,
            })),
            self.image,
        ).strip()
        self._check_local_connection()
        self._check_password_auth()
        self._connect_wan_network()
        with self.assertRaises(ProcessExecutionError):
            self._check_password_auth("example.com")


if __name__ == "__main__":
    unittest.main()
