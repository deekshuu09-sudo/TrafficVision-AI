Data Layer Documentation

AI-Powered Traffic Prediction and Intelligent Congestion Management Platform



1\. Overview

The data layer stores road information, traffic readings, historical records, road conditions, and aggregated traffic metrics. PostgreSQL provides persistent data storage, while Redis is used for caching recent traffic data where configured.

2\. Database Tables

Table	Purpose

roads	Stores monitored road information.

traffic\_readings	Stores individual traffic readings, vehicle counts, speeds, densities, timestamps, and congestion levels.

traffic\_history	Stores historical traffic records.

road\_conditions	Stores road-condition information.

hourly\_traffic\_metrics	Stores hourly aggregated traffic statistics.

daily\_traffic\_metrics	Stores daily aggregated traffic statistics.

3\. Data Flow

1\. Traffic readings enter through the ingestion process.

2\. PostgreSQL stores persistent traffic records.

3\. Redis can cache frequently requested live traffic data.

4\. Historical records and aggregated metrics support analytics.

5\. API endpoints provide traffic data to clients and dashboards.

4\. Production API Validation

The following endpoints were tested:

\- GET /health — returned HTTP 200.

\- GET /api/v1/traffic/live — returned six road records, R001–R006.

\- /docs — provides interactive API documentation.

Data freshness: The live API returned the timestamp 2026-08-26T22:00:00+05:30 during October testing. The endpoint was accessible, but the freshness of the returned traffic data still needs confirmation.

5\. Local and Production Data Comparison

The recorded table counts matched between local and production databases.

Table	Row count

roads	6

daily\_traffic\_metrics	168

hourly\_traffic\_metrics	4,032

road\_conditions	9

traffic\_history	4,032

traffic\_readings	2,892

Matching counts establish count parity at the time of testing, but do not guarantee that every row is identical.

6\. Database Optimization

PostgreSQL query plans and index usage were examined. Both tested queries used existing indexes.

Query	Index	Execution time

Recent traffic readings for R001	idx\_traffic\_road\_time	0.166 ms

Recent traffic history for R001	idx\_traffic\_history\_road\_time	0.170 ms

These timings were measured using EXPLAIN (ANALYZE, BUFFERS). They represent individual test runs and are not guarantees of performance under heavy load. No production indexes were added or removed based solely on these results.

7\. Backup and Recovery

A PostgreSQL custom-format backup was created using pg\_dump, and a restore-verification exercise was recorded as successful.

Recommended safeguards:

\- Keep backups in a secure location.

\- Never commit database passwords to Git.

\- Store credentials in environment variables or the hosting platform's secret configuration.

\- Test database restoration periodically.

\- Verify automated backup scheduling and retention separately.

8\. Security and Maintenance

\- Use SSL/TLS for remote database connections where required.

\- Apply least-privilege database permissions.

\- Use parameterized SQL queries.

\- Monitor database connectivity, data freshness, and cache behavior.

\- Verify Redis configuration in the deployed environment.

9\. Conclusion

The data layer supports persistent traffic storage through PostgreSQL and the configured Redis caching path. Testing covered database table-count parity, API health, live traffic responses, indexed query plans, query execution timings, and backup/restore verification. Live-data freshness and deployed Redis behavior remain items for confirmation.

