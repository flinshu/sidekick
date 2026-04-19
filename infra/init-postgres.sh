#!/bin/bash
set -e

# Create sidekick + langfuse databases (POSTGRES_MULTIPLE_DATABASES env var)
if [ -n "$POSTGRES_MULTIPLE_DATABASES" ]; then
    for db in $(echo "$POSTGRES_MULTIPLE_DATABASES" | tr ',' ' '); do
        echo "Creating database: $db"
        psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
            CREATE DATABASE "$db";
            GRANT ALL PRIVILEGES ON DATABASE "$db" TO "$POSTGRES_USER";
EOSQL
    done
fi
