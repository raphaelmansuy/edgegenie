"""Databricks AST semantics: syntax operators, normalized built-ins and execution policy differ."""

import pytest
from sqlglot.dialects.databricks import Databricks

from api.domain.sqlpolicy import validate
from api.domain.sqlquery import SqlError

# One row per trip enters the CTE; the outer result has one row per pickup date.
TAXI_CTE = """WITH trip_metrics AS (
    SELECT date(tpep_pickup_datetime) AS pickup_date, trip_distance, fare_amount,
           ROUND((unix_timestamp(tpep_dropoff_datetime) - unix_timestamp(tpep_pickup_datetime)) / 60.0, 2) AS duration_minutes
    FROM samples.nyctaxi.trips
    WHERE trip_distance > 0 AND fare_amount > 0
)
SELECT pickup_date, COUNT(*) AS total_trips,
       ROUND(AVG(trip_distance), 2) AS avg_distance_miles,
       ROUND(AVG(fare_amount), 2) AS avg_fare_amount,
       ROUND(AVG(duration_minutes), 2) AS avg_duration_minutes
FROM trip_metrics GROUP BY pickup_date ORDER BY pickup_date ASC;"""


@pytest.mark.parametrize(
    "sql",
    [
        TAXI_CTE,
        "SELECT 1 WHERE 1 > 0 AND 2 > 0",
        "SELECT 1 WHERE 1 > 0 OR 2 > 0",
        "SELECT 1 WHERE NOT (1 > 0 AND 2 < 0)",
        "SELECT 1 WHERE EXISTS (SELECT 1 WHERE 1 > 0 AND 2 > 0)",
        "WITH a AS (SELECT 1 AS n), b AS (SELECT n FROM a WHERE n > 0 AND n < 5) SELECT n FROM b",
        "SELECT 'AND custom_udf(1); DELETE FROM x' AS harmless",
    ],
)
def test_read_queries_allow_structural_operators_throughout_ctes_and_subqueries(sql):
    assert validate(sql, [], dialect=Databricks) == []


@pytest.mark.parametrize(
    "expression",
    [
        "COUNT(*)",
        "SUM(1)",
        "AVG(1)",
        "MIN(1)",
        "MAX(1)",
        "COALESCE(NULL, 1)",
        "CAST(1 AS BIGINT)",
        "TRY_CAST('1' AS INT)",
        "ABS(-1)",
        "ROUND(1.234, 2)",
        "LOWER('A')",
        "UPPER('a')",
        "LENGTH('abc')",
        "CONCAT('a', 'b')",
        "SUBSTRING('abc', 1, 2)",
        "TRIM(' a ')",
        "CURRENT_DATE()",
        "CURRENT_TIMESTAMP()",
        "DATE_TRUNC('DAY', CURRENT_TIMESTAMP())",
        "YEAR(CURRENT_DATE())",
        "MONTH(CURRENT_DATE())",
        "DAY(CURRENT_DATE())",
        "ROW_NUMBER() OVER ()",
        "RANK() OVER (ORDER BY 1)",
        "DENSE_RANK() OVER (ORDER BY 1)",
        "LAG(1) OVER (ORDER BY 1)",
        "LEAD(1) OVER (ORDER BY 1)",
        "IF(TRUE, 1, 0)",
        "CASE WHEN 1 = 1 AND 2 = 2 THEN 1 ELSE 0 END",
        "DATE('2026-01-01')",
        "TO_DATE('01/01/2026', 'dd/MM/yyyy')",
        "UNIX_TIMESTAMP('2026-01-01 00:00:00')",
        "TO_UNIX_TIMESTAMP('2026-01-01', 'yyyy-MM-dd')",
        "YEAR(:day)",
        "DATE_TRUNC('DAY', :day)",
        "CURRENT_DATE",
        "CURRENT_TIMESTAMP",
        "UNIX_TIMESTAMP /* comment */ ('2026-01-01 00:00:00')",
        "NVL(NULL, 1)",
        "IFNULL(NULL, 1)",
        "LCASE('A')",
        "UCASE('a')",
        "LEN('abc')",
        "CHAR_LENGTH('abc')",
        "CHARACTER_LENGTH('abc')",
        "SUBSTR('abc',1,2)",
        "CURDATE()",
        "NOW()",
    ],
)
def test_documented_databricks_functions_accept_their_normalized_ast(expression):
    parameters = [{"name": "day", "type": "DATE", "value": "2026-01-01"}] if ":day" in expression else []
    assert validate("SELECT " + expression, parameters, dialect=Databricks) == parameters


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT custom_udf(1) WHERE 1 > 0 AND 2 > 0",
        "SELECT 1 WHERE EXISTS (SELECT custom_udf(1))",
        "WITH x AS (SELECT custom_udf(1) AS n) SELECT n FROM x WHERE n > 0 AND n < 5",
        "SELECT read_files('s3://example') WHERE 1 = 1 OR 2 = 2",
        "SELECT system.ai.query('endpoint', 'text')",
        "WITH x AS (SELECT 1) INSERT INTO target SELECT * FROM x",
        "WITH x AS (SELECT 1) DELETE FROM target WHERE EXISTS (SELECT * FROM x)",
        "SELECT 1 WHERE 1 > 0 AND 2 > 0; DROP TABLE target",
        # Internal AST names can parse as built-ins even though they are not Databricks SQL names.
        "SELECT str_to_unix('2026-01-01')",
        "SELECT ts_or_ds_to_date('2026-01-01')",
        "SELECT `str_to_unix`('2026-01-01')",
    ],
)
def test_operator_support_never_bypasses_nested_mutations_or_unknown_function_calls(sql):
    with pytest.raises(SqlError):
        validate(sql, [], dialect=Databricks)


def test_unsupported_function_error_is_specific_without_echoing_private_sql():
    with pytest.raises(SqlError) as error:
        validate(
            "SELECT private_secret_udf('private literal') WHERE 1 = 1 AND 2 = 2", [], dialect=Databricks
        )
    assert error.value.code == "UNSUPPORTED_FUNCTION"
    assert "Unrecognized or external function calls" in str(error.value)
    assert "private" not in str(error.value) and "mutations" not in str(error.value)
    with pytest.raises(SqlError) as builtin:
        validate("SELECT ACOS(0.5)", [], dialect=Databricks)
    assert builtin.value.code == "UNSUPPORTED_FUNCTION" and "ACOS" in str(builtin.value)
