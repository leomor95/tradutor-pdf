#set page(paper: "a4", margin: (x: 2cm, y: 2.5cm))
#set text(font: "Liberation Sans", size: 11pt)
#set par(justify: true, leading: 0.8em)

= Consensus Protocols in Distributed Computing

Distributed consensus protocols ensure that multiple nodes in an asynchronous network agree on shared state values despite node crashes and packet delays.
Early algorithms like Paxos established theoretical foundations for state machine replication#footnote[Lamport, L. (1998). The Part-Time Parliament. ACM Transactions on Computer Systems.].

== Practical Implementations

Modern systems frequently adopt consensus alternatives that are deliberately designed for higher understandability and operational ergonomics.
The Raft consensus algorithm decomposes state machine replication into distinct leader election, log replication, and safety subproblems#footnote[Ongaro, D., & Ousterhout, J. (2014). In Search of an Understandable Consensus Algorithm. USENIX ATC.].

By enforcing strong leader invariants, Raft significantly simplifies reasoning about cluster membership changes and crash recovery.
