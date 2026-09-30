#set page(
  paper: "a4",
  margin: (top: 2.5cm, bottom: 2.5cm, left: 3cm, right: 3cm)
)
#set text(font: "DejaVu Sans", size: 11pt)
#set par(justify: true, leading: 0.7em)

= Page 1: Digital Overview

This is selectable digital text on the first page of the mixed document. Modern distributed systems rely on containerization, orchestration, and automated scaling to handle dynamic workloads.

#pagebreak()

= Page 2: Storage Architecture

Storage subsystems utilize block, file, and object interfaces to satisfy varying latency and throughput requirements. Solid state drives and non-volatile memory provide microsecond access times.

#pagebreak()

= Page 3: Visual Topology

Digital text on page 3 accompanying a system topology diagram. Network latency and bandwidth determine the optimal partitioning strategy across clusters.

#figure(
  image("sample_image.png", width: 50%),
  caption: [System Topology Overview]
)

#pagebreak()

= Page 4: Performance Monitoring

Performance monitoring continuously tracks CPU utilization, memory allocation, network throughput, and garbage collection pauses across all nodes.
