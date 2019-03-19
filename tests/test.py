#!/usr/bin/env python3
import json
import os
import time
import unittest

from plumbum import FG, local
from plumbum.cmd import cat, docker

# Make sure all paths are relative to tests dir
local.cwd.chdir(os.path.dirname(__file__))
certgen = local["./certgen"]


class PostgresAutoconfCase(unittest.TestCase):
    """Test behavior for this docker image"""
    def setUp(self):
        with local.cwd(local.cwd / ".."):
            local["./hooks/build"]()
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
            docker("container", "stop", self.postgres_container)
            docker("container", "rm", self.postgres_container)
        except AttributeError:
            pass  # No postgres daemon
        docker("network", "rm", "lan", "wan")
        return super().tearDown()

    def generate_certs(self):
        """Generate certificates for testing the image."""
        certgen("example.com", "test_user")

    def check_cert_config(self):
        """Check that the cert config is OK."""
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
        run = docker[
            "container", "run",
        ]
        # Test LAN connection with password auth works fine
        self.assertEqual("1\n", run(
            "--network", "lan",
            "-e", "PGDATABASE=test_db",
            "-e", "PGPASSWORD=test_password",
            "-e", "PGSSLMODE=disable",
            "-e", "PGUSER=test_user",
            self.image, "psql",
            "--host", self.postgres_container[:12],
            "--command", "SELECT 1",
            "--no-align",
            "--tuples-only",
        ))
        # Attach a new network to mock a WAN connection
        docker(
            "network", "connect",
            "--alias", "example.com",
            "wan",
            self.postgres_container,
        )
        # Test WAN connection with cert auth works fine
        self.assertEqual("1\n", run(
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
                self.generate_certs()
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
                self.check_cert_config()

    def test_server_certs_mount(self):
        """Test server enables cert authentication through file mounts."""
        with local.tempdir() as tdir:
            with local.cwd(tdir):
                self.generate_certs()
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
                self.check_cert_config()


if __name__ == "__main__":
    unittest.main()
