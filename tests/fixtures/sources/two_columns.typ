#set page(paper: "a4", columns: 2, margin: (x: 2cm, y: 2.5cm))
#set text(font: "Liberation Sans", size: 10pt)
#set par(justify: true, leading: 0.7em)

= Left Column Architecture

Distributed storage systems partition datasets across multiple physical storage servers using hash rings.
Every incoming write request is mapped to a primary coordinator node responsible for durability and replication.

== Primary Replication Path

When a write transaction arrives at the coordinator node, it is immediately recorded in an append-only transaction log.
Once local storage confirms the disk write, the record is forwarded to replica nodes according to the configured quorum policy.

#colbreak()

= Right Column Failover

When a primary node fails to respond to periodic heartbeat probes, the remaining cluster peers initiate an election round.
Nodes verify the latest log term before casting votes to avoid stale data propagation across partition boundaries.

== Recovery and Compaction

After electing a new coordinator, replica nodes perform log reconciliation to synchronize uncommitted records.
Background compaction processes merge immutable SSTables to reclaim disk space and reduce read amplification.
