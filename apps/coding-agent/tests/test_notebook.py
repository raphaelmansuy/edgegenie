

def test_a_header_only_block_is_not_a_cell():
    """It was cell 1 for real, and running it produced a SQL syntax error about '#'."""
    from api.domain.notebook import parse_source

    assert parse_source("-- Databricks notebook source\n", "SQL") == []
    assert parse_source("\ufeff-- Databricks notebook source\n", "SQL") == []
    assert parse_source("\n\n-- Databricks notebook source\n", "SQL") == []
    cells = parse_source("-- Databricks notebook source\n-- COMMAND ----------\nselect 1\n", "SQL")
    assert [c.source.strip() for c in cells] == ["select 1"]


def test_a_python_style_header_is_stripped_from_a_sql_notebook():
    """The file's own comment prefix wins over the language we were asked to parse.

    A notebook created as SQL but written with `#` lines kept its header as cell 1, which then got
    run as SQL and failed with a syntax error about '#'.
    """
    from api.domain.notebook import parse_source

    assert parse_source("# Databricks notebook source\n", "SQL") == []
    cells = parse_source("# Databricks notebook source\n# COMMAND ----------\nselect 1\n", "SQL")
    assert [c.source.strip() for c in cells] == ["select 1"]
    # and the ordinary SQL spelling still works
    assert parse_source("-- Databricks notebook source\n", "SQL") == []
