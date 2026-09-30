#set page(paper: "a4", margin: (x: 2cm, y: 2.5cm))
#set text(font: "Liberation Sans", size: 11pt)
#set par(justify: true, leading: 0.8em)
#set list(spacing: 1.5em)
#set enum(spacing: 1.5em)

= Main Document Title

This is an introductory paragraph explaining distributed system fundamentals and architectural patterns.

== Section One: Core Features

The primary features of our architecture are outlined in the following list:

- High availability through multi-region replication.
- Fault tolerance with automated leader election.
- Low-latency data replication using consistent hashing.

== Section Two: Operational Procedures

Follow these numbered steps in sequence to perform an orderly rolling upgrade:

+ Stop incoming traffic by updating the reverse proxy routing rules.
+ Drain active worker connections and wait for pending tasks to finish.
+ Upgrade the binary executable to the target release version.
+ Restart the node service and verify the health check endpoint.

=== Subsection: Monitoring and Telemetry

Ensure all Prometheus metrics report steady state before proceeding to the next cluster node.
