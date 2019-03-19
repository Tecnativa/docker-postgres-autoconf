# PostgreSQL Auto-Conf

[![Build Status](https://travis-ci.org/Tecnativa/docker-postgres-autoconf.svg?branch=master)](https://travis-ci.org/Tecnativa/docker-postgres-autoconf)
[![Docker Pulls](https://img.shields.io/docker/pulls/tecnativa/postgres-autoconf.svg)](https://hub.docker.com/r/tecnativa/postgres-autoconf)
[![Layers](https://images.microbadger.com/badges/image/tecnativa/postgres-autoconf.svg)](https://microbadger.com/images/tecnativa/postgres-autoconf)
[![Commit](https://images.microbadger.com/badges/commit/tecnativa/postgres-autoconf.svg)](https://microbadger.com/images/tecnativa/postgres-autoconf)
[![License](https://img.shields.io/github/license/Tecnativa/docker-postgres-autoconf.svg)](https://github.com/Tecnativa/docker-postgres-autoconf/blob/master/LICENSE)

## What

Image that configures Postgres before starting it.

## Why

To automate dealing with specific users accessing from specific networks to a postgres server.

## How

It tries to configure as good as possible, differentiating between connections made from LAN (docker networks attached) and from WAN (all others). This is done at entrypoint time, because it's the only way to know dynamic IP ranges in attached networks.

Then it generates appropriate [`postgres.conf`](https://www.postgresql.org/docs/current/runtime-config.html) and [`pg_hba.conf`](https://www.postgresql.org/docs/current/auth-pg-hba-conf.html) files.

It doesn't validate your settings, so you should be aware of proper configuration:

- Do not set `cert` auth method if `client.ca.cert.pem` is not supplied.
- Do not enable TLS if `server.cert.pem` and `server.key.pem` are not supplied.
- Do not publish ports without encryption.
- Use good passwords if you don't use cert auth.

### Environment variables

Variables' defaults are all found in the [`Dockerfile`][].

The container is mainly configured via these environment variables:

#### `CERTS`

JSON object with some or all of these keys:

- `client.ca.cert.pem`: PEM contents for Postgres' `ssl_ca_file` parameter. Enables `cert` authentication in remote postgres clients. It's the most secure remote auth option. All clients must authenticate with a cert signed by this CA.
- `server.cert.pem`: PEM contents for Postgres' `ssl_cert_file` parameter. The Postgres server will identify himself and encrypt the connection with this certificate.
- `server.key.pem`: PEM contents for Postgres' `ssl_key_file` parameter. The Postgres server will identify himself and encrypt the connection with this private key.

If you pass `server.cert.pem`, you should pass `server.key.pem` too, and viceversa, or TLS encryption will not be properly configured. You also need both of them if you use `client.ca.cert.pem`.

It is safer to mount files with secrets instead of passing a JSON string in an env variable. You can mount the equivalents:

- `/etc/postgres/client.ca.cert.pem`
- `/etc/postgres/server.cert.pem`
- `/etc/postgres/server.key.pem`

#### `CONF_EXTRA`

String with contents appended to the generated `postgres.conf` file.

#### `LAN_AUTH_METHOD`

Method required to authenticate clients that connect from LAN.

#### `LAN_CONNECTION`

Connection type allowed for LAN connections.

#### `LAN_DATABASES`

JSON array with database names whose access is allowed from LAN.

#### `LAN_HBA_TPL`

Template applied for each combination of LAN CIDR/USER/DATABASE in the `pg_hba.conf` file.

Some placeholders can be expanded. See the [`Dockerfile`][] to know them.

#### `LAN_TLS`

Wether to enable or not TLS in LAN connections.

#### `LAN_USERS`

Users allowed to connect from LAN.

#### `WAN_AUTH_METHOD`

Method required to authenticate clients that connect from WAN.

#### `WAN_CONNECTION`

Connection type allowed for WAN connections.

#### `WAN_DATABASES`

JSON array with database names whose access is allowed from WAN.

#### `WAN_HBA_TPL`

Template applied for each combination of USER/DATABASE in the `pg_hba.conf` file, for public connections.

Some placeholders can be expanded. See the [`Dockerfile`][] to know them.

#### `WAN_TLS`

Wether to enable or not TLS in WAN connections.

#### `WAN_USERS`

Users allowed to connect from WAN.

[`Dockerfile`]: https://github.com/Tecnativa/docker-postgres-autoconf/blob/master/Dockerfile
