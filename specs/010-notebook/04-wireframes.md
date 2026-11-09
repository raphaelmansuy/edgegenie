# 04. Wireframes

[Index](README.md) · requirements [03](03-requirements.md) · diagrams [05](05-diagrams.md)

The notebook column, after a run that stopped on the fourth cell. The map is the narrow rail on the
right of this column in the product; it is drawn beside the document here so both fit one review.

```text
┌────────────────────────────────────────────────────────────────┐
│ Run all    2 cells can run · 1 skipped     Serverless SQL      │
├────────────────────────────────────────────────────────────────┤
│ 1  md    Revenue by hour                                       │
│ 2  sql   -- trips by hour                         Run  v       │
│        period    trips    fare                                 │
│        morning   40       80.00                                │
│        evening   10       12.50                                │
│        filter [ night________ ]   1 of 3   Copy                │
│ 3  sql   %skip                          skipped in batch       │
│ 4  sql   select * from missing_table            failed         │
│        Fix with agent                                          │
└────────────────────────────────────────────────────────────────┘
```

[NB-2](03-requirements.md) is the bar. [NB-3](03-requirements.md) is cell 3: it has no output, because
a batch did not run it. [NB-5](03-requirements.md) is the filter, which shows one of three rows and
copies only those. [NB-10](03-requirements.md) is the absence of a cluster menu; the chip says where
SQL ran.

## The map, opened

One bar per code cell. Cell 1 is markdown, so it is not in the list. The pin keeps the list open;
hover does the same. [NB-4](03-requirements.md), [NB-14](03-requirements.md).

```text
┌────────────────────────────────────────────────────────────────┐
│ Cells                              3                           │
├────────────────────────────────────────────────────────────────┤
│  * 2   trips by hour            done                           │
│  * 3   %skip                  skipped                          │
│  * 4   missing_table          failed                           │
├────────────────────────────────────────────────────────────────┤
│  [ First failed ]   [ Last run ]                               │
└────────────────────────────────────────────────────────────────┘
```

## Run, above, and below

The chevron on Run opens this. Above is disabled on the first runnable cell, and the disabled item
says why. [NB-2](03-requirements.md).

```text
┌────────────────────────────────────────────────────────────────┐
│ Run                                                            │
│ Run all above                                                  │
│ Run all below                                                  │
└────────────────────────────────────────────────────────────────┘
```

## Command mode

Esc moves the blue bar onto the cell itself. The next letter is a command, not text. H opens the
sheet, which has a Command mode section. [NB-1](03-requirements.md), [NB-9](03-requirements.md).

```text
┌────────────────────────────────────────────────────────────────┐
│  2 |  sql   -- trips by hour                                   │
│    |  select period, trips, fare                               │
│    |                                                           │
│    the bar on the left means the cell is selected              │
└────────────────────────────────────────────────────────────────┘
```
