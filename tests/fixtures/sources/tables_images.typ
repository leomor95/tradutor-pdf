#set page(paper: "a4", margin: (x: 2cm, y: 2.5cm))
#set text(font: "Liberation Sans", size: 11pt)
#set par(justify: true, leading: 0.8em)

= Performance Evaluation and Benchmarks

This document reports the empirical benchmarking results comparing key-value storage engines under high concurrency workloads.

== Configuration Matrix

The experimental evaluation parameters are summarized in the table below:

#table(
  columns: (1.5fr, 1fr, 2fr),
  fill: (col, row) => if row == 0 { rgb("e8eef5") } else { none },
  stroke: 0.5pt + rgb("bdc3c7"),
  inset: 8pt,
  [Component], [Default Value], [Description],
  [Connection Pool], [64 connections], [Maximum concurrent database connections per node],
  [Write Buffer], [128 MB], [In-memory write ahead log buffer capacity],
  [Heartbeat Interval], [500 ms], [Consensus leader ping interval for failover detection],
  [Compaction Threads], [4 threads], [Background threads dedicated to LSM-tree SSTable compaction]
)

== Architecture Overview

The following diagram illustrates the cluster topology and data synchronization path between active replicas:

#align(center)[
  #figure(
    image("sample_image.png", width: 70%),
    caption: [Cluster replication and failover architecture diagram]
  )
]

All replica nodes stream write operations asynchronously while retaining quorum verification for consensus.
