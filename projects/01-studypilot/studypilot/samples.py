"""Bundled demo note sets (hand-written study notes, textbook-level facts only).

They are also written to data/samples/*.md on first run so they can be uploaded
through the file picker during a demo.
"""
import os

SAMPLES = [
    {
        "id": "os-deadlocks",
        "title": "Operating Systems – Deadlocks",
        "subject": "Operating Systems",
        "text": """# Operating Systems: Deadlocks

A deadlock is a situation in which a set of processes are blocked because each process is holding a resource and waiting for another resource held by some other process in the set. None of the deadlocked processes can proceed, release its resources or be woken up, so the system makes no progress on that work. Deadlocks are a classic problem in multiprogramming systems, where several processes compete for a finite number of resources such as memory, files, printers and locks.

A process uses a resource in a fixed sequence: it requests the resource, uses it and then releases it. If the resource is not available when it is requested, the requesting process must wait. A resource allocation graph is a directed graph that models this situation: request edges point from a process to a resource type, and assignment edges point from a resource instance to the process holding it. If the resource allocation graph contains no cycle, no deadlock exists. If every resource type has exactly one instance, a cycle in the graph means that a deadlock has occurred. With multiple instances per resource type, a cycle is necessary but not sufficient for a deadlock.

The Coffman conditions are four necessary conditions that must hold simultaneously for a deadlock to occur. Mutual exclusion means at least one resource must be held in a non-sharable mode, so only one process can use it at a time. Hold and wait means a process is holding at least one resource while waiting to acquire additional resources held by other processes. No preemption means a resource can be released only voluntarily by the process holding it, after that process has completed its task. Circular wait means there exists a set of waiting processes P0 to Pn such that each process waits for a resource held by the next process, and the last process waits for a resource held by the first.

Operating systems handle deadlocks in one of four ways: prevention, avoidance, detection with recovery, or simply ignoring the problem. Deadlock prevention ensures that at least one of the four necessary conditions can never hold. The hold and wait condition can be broken by requiring a process to request all of its resources before it begins execution, although this leads to low resource utilization and possible starvation. Circular wait can be prevented by imposing a total ordering on all resource types and requiring every process to request resources in increasing order of enumeration. Preemption can be allowed for resources whose state is easy to save and restore, such as CPU registers and memory.

Deadlock avoidance requires the operating system to know in advance the maximum number of resources each process may request. The system then grants a request only if the resulting state is a safe state. A state is safe if there exists a safe sequence, an ordering of all processes in which each process can obtain its maximum remaining need using the currently available resources plus the resources held by all earlier processes. An unsafe state is not necessarily a deadlock, but it may lead to one. The Banker's algorithm, proposed by Edsger Dijkstra, is the best-known avoidance algorithm for resources with multiple instances. It maintains the Available vector and the Max, Allocation and Need matrices, where Need equals Max minus Allocation, and it runs a safety algorithm before granting each request.

Deadlock detection allows the system to enter a deadlocked state and then finds it. For single-instance resources the system maintains a wait-for graph, obtained by removing the resource nodes from the resource allocation graph, and periodically searches it for a cycle. For multiple instances, a detection algorithm similar to the safety algorithm of the Banker's algorithm is used. How often detection runs is a trade-off between overhead and how long deadlocked processes stay stuck.

Once a deadlock is detected, the system must recover. Process termination aborts either all deadlocked processes or one process at a time until the deadlock cycle is eliminated. Resource preemption takes resources away from some processes and gives them to others; it requires selecting a victim to minimise cost, rolling the victim back to a safe state, and ensuring that the same process is not always chosen, which would cause starvation.

Many general-purpose operating systems, including Linux and Windows, largely ignore deadlocks and leave them to application developers, because prevention and avoidance are expensive and deadlocks are rare in practice. This approach is often called the ostrich algorithm. Deadlock is different from livelock, where processes keep changing state in response to each other without making progress, and from starvation, where a process waits indefinitely because other processes are always favoured.
""",
    },
    {
        "id": "ml-basics",
        "title": "Machine Learning – Basics",
        "subject": "Artificial Intelligence & Machine Learning",
        "text": """# Machine Learning Basics

Machine learning is a branch of artificial intelligence in which computer systems learn patterns from data instead of being explicitly programmed with rules. A learning algorithm takes a training dataset and produces a model that can make predictions on new, unseen examples. Each example is described by features, which are measurable input variables, and in many problems by a label, which is the output we want to predict.

Supervised learning uses labelled data, where every training example has a known correct output. Classification is a supervised task in which the label is a discrete category, such as spam or not spam. Regression is a supervised task in which the label is a continuous value, such as the price of a house. Unsupervised learning works with unlabelled data and tries to discover structure, for example grouping similar customers with clustering or reducing the number of features with dimensionality reduction. Reinforcement learning trains an agent to take actions in an environment so that it maximises a cumulative reward signal.

Linear regression models the target as a weighted sum of the input features plus a bias term. Its parameters are usually fitted by minimising the mean squared error between predictions and true values. Logistic regression, despite its name, is a classification algorithm: it passes a linear combination of features through the sigmoid function to output a probability between 0 and 1. The k-nearest neighbours algorithm classifies a new point by the majority label of the k closest training points under a distance metric such as Euclidean distance. A decision tree splits the data recursively on feature thresholds chosen to maximise information gain or to reduce Gini impurity. K-means clustering partitions data into k clusters by repeatedly assigning points to the nearest centroid and recomputing each centroid as the mean of its points.

Gradient descent is an iterative optimisation algorithm that updates model parameters in the direction opposite to the gradient of the loss function. The learning rate controls the size of each update step: if it is too large the algorithm may diverge, and if it is too small training becomes very slow. Stochastic gradient descent estimates the gradient from a single example or a small mini-batch, which makes each step cheaper and adds noise that can help escape poor regions of the loss surface.

Overfitting happens when a model learns noise and accidental details of the training data, so it performs well on training data but poorly on new data. Underfitting happens when a model is too simple to capture the underlying pattern and performs poorly even on the training data. The bias-variance trade-off describes this tension: high bias causes underfitting, while high variance causes overfitting. Regularisation reduces overfitting by adding a penalty on large weights to the loss function; L1 regularisation can drive some weights to exactly zero, while L2 regularisation shrinks all weights smoothly.

To estimate how well a model generalises, the data is split into a training set, a validation set and a test set. The validation set is used to tune hyperparameters, such as the learning rate or the depth of a decision tree, and the test set is used only once for the final evaluation. Cross-validation divides the data into k folds, trains on k minus 1 folds and validates on the remaining fold, repeating the process k times and averaging the results.

Accuracy is the fraction of predictions that are correct, but it can be misleading when the classes are imbalanced. Precision is the fraction of predicted positives that are truly positive, and recall is the fraction of actual positives that the model finds. The F1 score is the harmonic mean of precision and recall. A confusion matrix tabulates true positives, false positives, true negatives and false negatives, and all of these metrics can be computed from it.
""",
    },
    {
        "id": "cn-tcpip",
        "title": "Computer Networks – TCP/IP",
        "subject": "Computer Networks",
        "text": """# Computer Networks: The TCP/IP Model

The TCP/IP model is the layered architecture on which the Internet is built. It is usually described with four layers: the link layer, the internet layer, the transport layer and the application layer. Each layer provides services to the layer above it and uses the services of the layer below, which lets each layer change independently. The OSI reference model, by comparison, has seven layers and is mainly used as a teaching and design reference.

The link layer moves frames between devices on the same physical network, such as an Ethernet segment or a Wi-Fi network. Devices on a local network are identified by a MAC address, a 48-bit hardware address assigned to each network interface. The Address Resolution Protocol (ARP) maps an IPv4 address to the MAC address of a host on the local network.

The internet layer is responsible for logical addressing and for routing packets across multiple networks. The Internet Protocol (IP) is a connectionless, best-effort protocol: it does not guarantee delivery, ordering or freedom from duplication. An IPv4 address is 32 bits long and is usually written in dotted-decimal notation, while an IPv6 address is 128 bits long. A subnet mask divides an IP address into a network part and a host part. Routers forward packets hop by hop using routing tables, and the time-to-live field is decremented at each hop so that packets cannot loop forever. ICMP carries error and diagnostic messages, and tools such as ping rely on it.

The transport layer provides end-to-end communication between processes, which are identified by port numbers. The Transmission Control Protocol (TCP) is a connection-oriented, reliable protocol that delivers a byte stream in order. TCP establishes a connection with a three-way handshake: the client sends a SYN segment, the server replies with a SYN-ACK segment, and the client answers with an ACK segment. TCP uses sequence numbers and acknowledgements to detect lost data, and it retransmits segments when a retransmission timer expires. Flow control uses a sliding window advertised by the receiver so that a fast sender does not overwhelm a slow receiver. Congestion control, using mechanisms such as slow start and congestion avoidance, adjusts the congestion window so that senders do not overload the network itself. A connection is normally closed with an exchange of FIN and ACK segments.

The User Datagram Protocol (UDP) is a connectionless transport protocol that sends independent datagrams without handshakes, acknowledgements or retransmission. UDP has lower overhead and latency than TCP, so it is preferred for real-time applications such as voice calls, online games and live video, and for simple request-response protocols such as DNS queries. Applications that use UDP must tolerate or handle packet loss themselves.

The application layer contains the protocols that users and programs interact with directly. HTTP transfers web pages and API data, and HTTPS adds encryption using TLS. The Domain Name System (DNS) translates human-readable domain names into IP addresses. SMTP sends email between mail servers, while DHCP automatically assigns IP addresses and other configuration to hosts when they join a network. Well-known port numbers include 80 for HTTP, 443 for HTTPS, 53 for DNS and 25 for SMTP.

Encapsulation is the process by which each layer adds its own header to the data received from the layer above. Application data becomes a TCP segment or UDP datagram at the transport layer, an IP packet at the internet layer and a frame at the link layer. At the receiver, decapsulation removes the headers in the reverse order until the original data reaches the application.
""",
    },
]

BY_ID = {s["id"]: s for s in SAMPLES}


def write_sample_files(folder):
    """Write each sample to <folder>/<id>.md if missing (for the upload demo)."""
    os.makedirs(folder, exist_ok=True)
    for s in SAMPLES:
        path = os.path.join(folder, s["id"] + ".md")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(s["text"])
