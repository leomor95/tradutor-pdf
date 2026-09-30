#set page(
  paper: "a4",
  margin: (top: 2.5cm, bottom: 2.5cm, left: 3cm, right: 3cm),
  header: align(center)[_Distributed Systems Architecture_],
  footer: context align(center)[Page #counter(page).display()]
)
#set text(font: "DejaVu Sans", size: 11pt)
#set par(justify: true, leading: 0.7em)

= Chapter 1: Cloud and Distributed Architectures

Cloud computing offers on-demand availability of system resources, especially data storage and computing power, without direct active management by the user. Large clusters distribute tasks across multiple nodes.

A distributed system consists of autonomous computing entities that communicate over a network. The fundamental challenge is coordinating their actions to present a unified service to the end user.

#pagebreak()

= Chapter 2: Scalability and High Availability

Scalability is the capability of a system to handle a growing amount of work by adding resources to the system. Horizontal scalability involves adding more nodes to the pool of resources.

High availability ensures that a system remains operational and accessible even during hardware faults, network partitions, or routine software updates across data centers.

#pagebreak()

= Chapter 3: Concurrency Control and Mutexes

Concurrent systems execute multiple computing paths simultaneously. Mutual exclusion ensures that concurrent processes do not simultaneously execute their critical sections.

Deadlock prevention and lock-free data structures allow multiple threads to access shared memory efficiently without data corruption.

#pagebreak()

= Chapter 4: Message Queues and Event Streaming

Message queues decouple producers and consumers, enabling asynchronous communication and backpressure management. Events flow continuously through broker topics.

Distributed streaming platforms provide fault-tolerant message logs that can be replayed to reconstruct state across replicas.

#pagebreak()

= Chapter 5: Data Partitioning and Sharding

Partitioning divides large databases into smaller, faster, and more manageable pieces called shards. Each shard is held on a separate database server instance.

Consistent hashing minimizes the reorganization of keys when nodes are added or removed from the cluster topology.

#pagebreak()

= Chapter 6: Consensus Algorithms: Raft and Paxos

Reaching agreement in an untrusted network requires robust consensus algorithms. Raft decomposes consensus into leader election, log replication, and safety invariants.

By electing a distinguished leader, Raft simplifies cluster coordination and ensures deterministic state machine replication across all servers.

#pagebreak()

= Chapter 7: Microservices Communication and RPC

Modern service architectures rely on lightweight Remote Procedure Calls (RPC) using binary protocols like Protocol Buffers.

Service meshes provide load balancing, circuit breaking, and secure mutual TLS communication between microservices without changing application code.

#pagebreak()

= Chapter 8: Observability, Metrics, and Tracing

Observability requires telemetry data across three core pillars: metrics, logs, and distributed traces. Correlating these signals allows engineers to detect performance regressions.

OpenTelemetry provides vendor-neutral APIs to collect and export latency spans across complex asynchronous service graphs.

#pagebreak()

= Chapter 9: Fault Tolerance and Chaos Engineering

Fault tolerance allows a distributed system to continue operating properly in the event of failure of some of its components.

Chaos engineering proactively injects turbulent conditions into production environments to discover systemic weaknesses before they cause outages.

#pagebreak()

= Chapter 10: Deployment Pipelines and CI/CD

Automated deployment pipelines validate code changes through automated unit testing, static linting, and staged deployments.

Continuous integration and deployment pipelines ensure that software updates are delivered safely, reliably, and with minimal manual intervention.
