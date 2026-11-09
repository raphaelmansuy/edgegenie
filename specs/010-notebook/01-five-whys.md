# 01. Five whys, and the principles they force

[Index](README.md) · next: [02 Grounding](02-grounding.md)

The request was "on par or better than Databricks." Asked five times, that is not "copy the toolbar."

1. **Why match Databricks?** Because the people who open a notebook here already know that one, and a
   different keyboard is a tax on every cell.
2. **Why does their keyboard feel like a notebook?** Because a cell is selected *or* edited, never both,
   so a letter can mean "delete" without also meaning "type a d".
3. **Why select a cell at all?** Because the unit of work is the cell, and the unit of a run is a
   *range* of cells: all, above, below, or the ones you selected.
4. **Why a range, and not nine clicks?** Because a later cell reads what an earlier one made. The run
   has an order, and a failure in the middle is the only failure worth reading.
5. **Why show the failure in a map?** Because on a long notebook the red cell is below the fold. The
   map is how you find it without scrolling blind.

## First principles

### P1. A notebook is a document of cells, not a file with a preview

The thing you operate on is a cell: its text, its output, its place. The file format is how that
document is stored. [D1](./07-architecture.md#d1).

### P2. Two modes, and they do not share a letter

Edit mode types. Command mode acts. Esc and Enter are the only door between them. A letter that does
both is a bug. [NB-1](./03-requirements.md).

### P3. A run is a list, in order, that stops

Run all, Run above, and Run below are the same function with a different list. Above does not include
the current cell. Below does. The first cell that does not succeed ends the list. [NB-2](./03-requirements.md).

### P4. Skip is a decision the author wrote down

`%skip` at the top of a cell means "not in a batch." It does not mean "this cell can never run."
Running it on its own executes what follows the directive. [NB-3](./03-requirements.md).

### P5. The result stays with the cell, and you can ask it a question

A table you cannot filter is a screenshot. Sort, filter, and copy happen in the cell, on the rows
already returned. They do not re-run the query. [NB-5](./03-requirements.md).

### P6. The map is a projection, not a second model

Every bar is a code cell. Its tone is the run the cell already has, or the plan that says it will not
run. There is no status that exists only on the map. [NB-4](./03-requirements.md), [D3](./07-architecture.md#d3).

### P7. Do not draw a control for a thing the app cannot do

No cluster picker, no debugger, no share. The compute chip names the warehouse or says the Python ran
as the app. [V1](./06-lenses.md), [09](./09-edge-cases.md).

### P8. One rule, two languages, one corpus

The client and the server both recognise `%skip`. They are checked against the same sentences, because
a client that offers Run and a server that refuses it is the inert button again. [D2](./07-architecture.md#d2).
