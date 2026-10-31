-- Runs once, when the Postgres volume is first created.

-- Tools read company data through this user: SELECT only, nothing else.
CREATE ROLE tool_reader LOGIN PASSWORD 'tool_reader';
GRANT CONNECT ON DATABASE company TO tool_reader;
GRANT USAGE ON SCHEMA public TO tool_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT ON TABLES TO tool_reader;

-- Chat history lives in a separate database that tool_reader cannot open.
CREATE ROLE chainlit LOGIN PASSWORD 'chainlit';
CREATE DATABASE chainlit OWNER chainlit;
REVOKE CONNECT ON DATABASE chainlit FROM PUBLIC;
