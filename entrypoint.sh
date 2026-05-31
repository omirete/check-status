#!/bin/sh
# Export Docker environment variables so cron jobs can access them.
printenv | grep -v "^_=" > /etc/environment
exec cron -f
