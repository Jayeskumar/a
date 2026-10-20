"""Interview prep: technical questions keyed by skill, picked from the match result.

Matched skills -> deeper questions (you claimed it, expect probing).
Missing must-haves -> fundamentals (likely asked; prepare before the interview).
Projects -> deep-dive prompts. A couple of behavioural questions close the set.
"""
from . import ontology

# skill name -> [(difficulty, question)]
BANK = {
    "Python": [("medium", "What is the difference between a list and a tuple, and when would you choose each?"),
               ("medium", "Explain how Python's GIL affects multithreaded and multiprocess code."),
               ("hard", "How do generators work, and when would you use one instead of building a list?")],
    "Java": [("medium", "Compare HashMap and ConcurrentHashMap. When is each appropriate?"),
             ("medium", "Explain the difference between checked and unchecked exceptions."),
             ("hard", "How does garbage collection decide which objects to free?")],
    "JavaScript": [("medium", "Explain closures with an example where they cause a bug."),
                   ("medium", "What is the event loop, and how do microtasks differ from macrotasks?"),
                   ("hard", "Compare == and ===, and explain how 'this' is bound in arrow vs normal functions.")],
    "TypeScript": [("medium", "What is the difference between an interface and a type alias?"),
                   ("hard", "How would you type a function that accepts any object and returns one of its keys?")],
    "Go": [("medium", "How do goroutines and channels differ from OS threads and locks?"),
           ("hard", "When would you use a buffered channel, and what can go wrong with it?")],
    "C++": [("medium", "Explain RAII and how smart pointers implement it."),
            ("hard", "What is the difference between move and copy semantics?")],
    "SQL": [("easy", "What is the difference between INNER JOIN and LEFT JOIN?"),
            ("medium", "Write a query for the second-highest salary in each department."),
            ("hard", "Explain window functions with ROW_NUMBER vs RANK vs DENSE_RANK.")],
    "HTML": [("easy", "What are semantic HTML elements and why do they matter for accessibility and SEO?")],
    "CSS": [("medium", "Explain the box model and the difference between flexbox and grid."),
            ("medium", "How does CSS specificity decide which rule wins?")],
    "React": [("medium", "What problem do keys solve when rendering lists?"),
              ("medium", "Explain useEffect dependencies and a bug caused by a missing dependency."),
              ("hard", "How would you find and fix unnecessary re-renders in a large component tree?")],
    "Angular": [("medium", "Explain change detection and when you would use OnPush."),
                ("medium", "How do services and dependency injection work in Angular?")],
    "Vue.js": [("medium", "How does Vue's reactivity system track dependencies?")],
    "Next.js": [("medium", "Compare SSR, SSG and client-side rendering. When would you use each?")],
    "Redux": [("medium", "Why must reducers be pure, and how does Redux Toolkit help?"),
              ("hard", "When is global state the wrong choice compared to local or server state?")],
    "Node.js": [("medium", "Why is Node.js good at I/O-bound work but not CPU-bound work?"),
                ("hard", "How would you handle a memory leak in a long-running Node service?")],
    "Express.js": [("medium", "How does middleware ordering affect request handling in Express?")],
    "Django": [("medium", "Explain the N+1 query problem and how select_related/prefetch_related fix it."),
               ("medium", "How do Django migrations work, and how do you handle a migration conflict?"),
               ("hard", "How would you make a slow Django view 10x faster?")],
    "Django REST Framework": [("medium", "Compare APIView, GenericAPIView and ViewSets."),
                              ("medium", "How do serializers validate nested data?")],
    "Flask": [("medium", "How do application and request contexts work in Flask?"),
              ("medium", "How would you structure a large Flask app with blueprints?")],
    "FastAPI": [("medium", "How does FastAPI use type hints and Pydantic for validation?"),
                ("hard", "When should a FastAPI endpoint be async def vs def?")],
    "Spring Boot": [("medium", "What does @SpringBootApplication do under the hood?"),
                    ("medium", "Explain bean scopes and dependency injection in Spring.")],
    "REST APIs": [("easy", "What makes an API RESTful? Explain resources, verbs and status codes."),
                  ("medium", "How would you version and paginate a public REST API?"),
                  ("hard", "Which HTTP methods are idempotent, and why does it matter for retries?")],
    "GraphQL": [("medium", "What problems does GraphQL solve compared to REST, and what new ones does it add?")],
    "Microservices": [("medium", "How do you keep data consistent across services without distributed transactions?"),
                      ("hard", "When is a monolith the better choice?")],
    "PostgreSQL": [("medium", "How do indexes work, and when does Postgres ignore one?"),
                   ("hard", "Explain transaction isolation levels and a bug each one prevents.")],
    "MySQL": [("medium", "Compare InnoDB row-level locking with table locking."),
              ("medium", "How would you find and fix a slow query?")],
    "MongoDB": [("medium", "When would you embed documents vs reference them?"),
                ("medium", "How do indexes and the aggregation pipeline work?")],
    "Redis": [("medium", "What are common caching strategies (cache-aside, write-through) and their risks?"),
              ("hard", "How do you prevent a cache stampede?")],
    "Celery": [("medium", "How do you make Celery tasks idempotent and retry-safe?")],
    "Docker": [("easy", "What is the difference between an image and a container?"),
               ("medium", "How do you keep Docker images small and builds fast?"),
               ("hard", "Explain how layers and the build cache work.")],
    "Kubernetes": [("medium", "Explain pods, deployments and services."),
                   ("hard", "How do liveness and readiness probes differ, and what happens if they are wrong?")],
    "AWS": [("medium", "Compare EC2, Lambda and containers for running an API."),
            ("medium", "How would you store user uploads securely in S3?")],
    "CI/CD": [("medium", "Describe a CI/CD pipeline you would set up for a web service, stage by stage."),
              ("hard", "How do you roll back a bad deployment safely?")],
    "Git": [("easy", "What is the difference between merge and rebase?"),
            ("medium", "How would you recover a commit you accidentally reset?")],
    "Linux": [("easy", "How do you find which process is using a port and stop it?"),
              ("medium", "Explain file permissions (chmod 755) and users/groups.")],
    "Unit Testing": [("medium", "What makes a good unit test? How do you test code that calls an external API?")],
    "PyTest": [("medium", "How do pytest fixtures work, and what are fixture scopes?"),
               ("medium", "How do you mock a network call in pytest?")],
    "Jest": [("medium", "How do you mock a module and test async code in Jest?")],
    "React Testing Library": [("medium", "Why does Testing Library prefer queries by role over test IDs?")],
    "Responsive Design": [("medium", "How do you design mobile-first, and what breakpoints would you pick?")],
    "Web Accessibility": [("medium", "How would you make a custom dropdown accessible to keyboard and screen-reader users?")],
    "Web Performance": [("medium", "What are LCP, CLS and INP, and how would you improve each?")],
    "Tailwind CSS": [("medium", "What are the trade-offs of utility-first CSS?")],
    "Excel": [("easy", "When would you use VLOOKUP vs INDEX-MATCH vs XLOOKUP?"),
              ("medium", "How would you build a pivot table to compare monthly sales by region?")],
    "Pandas": [("medium", "How do you handle missing values in a DataFrame, and how do you choose a strategy?"),
               ("medium", "Explain groupby-apply and how merge differs from concat."),
               ("hard", "How would you process a CSV too large to fit in memory?")],
    "NumPy": [("medium", "What is broadcasting, and why is vectorised code faster than loops?")],
    "Statistics": [("easy", "Explain mean vs median and when the median is the better summary."),
                   ("medium", "What is a p-value, and what does it not tell you?"),
                   ("medium", "Explain correlation vs causation with a business example.")],
    "Hypothesis Testing": [("medium", "When would you use a t-test vs a chi-square test?")],
    "A/B Testing": [("medium", "How do you decide the sample size and duration of an A/B test?"),
                    ("hard", "What is peeking, and why does it inflate false positives?")],
    "Tableau": [("medium", "How would you design a dashboard so a manager understands it in 10 seconds?"),
                ("medium", "What are LOD expressions and when do you need them?")],
    "Power BI": [("medium", "What is the difference between a calculated column and a measure in DAX?")],
    "Data Visualization": [("medium", "Which chart would you use for trend, share and distribution, and why?")],
    "Data Cleaning": [("medium", "Walk through how you would clean a messy sales export before analysis.")],
    "Data Storytelling": [("medium", "Tell me about a time your analysis changed a decision. How did you present it?")],
    "Machine Learning": [("medium", "Explain the bias-variance trade-off."),
                         ("medium", "How do you detect and handle overfitting?"),
                         ("hard", "How would you choose an evaluation metric for an imbalanced classification problem?")],
    "Deep Learning": [("medium", "What causes vanishing gradients, and how do modern networks avoid them?")],
    "scikit-learn": [("medium", "Why use a Pipeline, and how does it prevent data leakage?")],
    "PyTorch": [("medium", "Walk through a PyTorch training loop. What does zero_grad do?")],
    "TensorFlow": [("medium", "How do you save, load and serve a trained TensorFlow model?")],
    "NLP": [("medium", "Compare TF-IDF features with transformer embeddings for text classification.")],
    "R": [("medium", "How do you reshape and summarise data with dplyr?")],
    "Data Structures": [("easy", "When would you use a hash map vs a balanced tree?"),
                        ("medium", "How would you detect a cycle in a linked list?")],
    "Algorithms": [("medium", "Explain the time complexity of quicksort and when it degrades."),
                   ("medium", "How would you find the shortest path in an unweighted graph?")],
    "OOP": [("easy", "Explain encapsulation, inheritance and polymorphism with a real example.")],
    "System Design": [("hard", "Design a URL shortener: API, storage, scaling and caching.")],
    "Apache Kafka": [("medium", "How do partitions and consumer groups give Kafka its scalability?")],
}

GENERIC = [
    ("medium", "Walk me through a real problem you solved with {s}. What would you do differently today?"),
    ("medium", "What are the main limitations of {s}, and when would you pick an alternative?"),
]
GAP_GENERIC = ("easy", "What do you know about {s}, and how would you get productive with it in your first month?")
BEHAVIOURAL = [
    ("behavioural", "Tell me about a time you disagreed with a teammate on a technical decision. What happened?"),
    ("behavioural", "Describe a deadline you nearly missed. What did you change afterwards?"),
]


def _questions_for(name, count, prefer=("medium", "hard", "easy")):
    bank = BANK.get(name) or []
    ordered = sorted(bank, key=lambda q: prefer.index(q[0]) if q[0] in prefer else 9)
    out = ordered[:count]
    if len(out) < count:
        out += [(d, q.format(s=name)) for d, q in GENERIC][:count - len(out)]
    return out


CAPS = {"deep-dive": 5, "gap": 3, "nice-to-have": 1, "project": 2, "behavioural": 1}


def generate(profile, jd, match, limit=12):
    """Up to `limit` questions, with a cap per type so every category is represented."""
    qs = []
    seen = set()
    count = {k: 0 for k in CAPS}

    def add(skill, kind, diff, text, why):
        if text in seen or count[kind] >= CAPS[kind]:
            return
        seen.add(text)
        count[kind] += 1
        qs.append({"skill": skill, "type": kind, "difficulty": diff, "question": text, "why": why})

    matched = sorted([r for r in match["must"] if r["credit"] >= 1.0], key=lambda r: (-r["weight"], r["label"]))
    for r in matched:
        n = 2 if r["weight"] > 1 else 1
        for d, q in _questions_for(r["skill_name"], n):
            add(r["skill_name"], "deep-dive", d, q, "Must-have you claim - expect probing")
    gaps = [r for r in match["must"] if r["credit"] < 0.5]
    for r in gaps:
        bank = BANK.get(r["skill_name"])
        if bank:
            d, q = sorted(bank, key=lambda x: ("easy", "medium", "hard").index(x[0]))[0]
        else:
            d, q = GAP_GENERIC[0], GAP_GENERIC[1].format(s=r["skill_name"])
        add(r["skill_name"], "gap", d, q, "Missing must-have - prepare the fundamentals")
    for r in [r for r in match["nice"] if r["credit"] >= 1.0]:
        for d, q in _questions_for(r["skill_name"], 1):
            add(r["skill_name"], "nice-to-have", d, q, "Nice-to-have you have - a chance to stand out")
    projects = profile.get("projects") or []
    roles = profile["experience"]["entries"]
    subjects = [p["title"] for p in projects[:1]] or [e["title"] for e in roles[:1] if e["title"]]
    if subjects:
        add(None, "project", "medium", "Walk me through \"%s\": what exactly did you build, and how did you measure "
            "success?" % subjects[0], "From your resume - interviewers start here")
        add(None, "project", "hard", "If \"%s\" had 10x more users tomorrow, what would break first and how would "
            "you fix it?" % subjects[0], "Tests depth beyond the happy path")
    for d, q in BEHAVIOURAL:
        add(None, "behavioural", "medium", q, "Asked in most interviews")
    order = {"deep-dive": 0, "gap": 1, "nice-to-have": 2, "project": 3, "behavioural": 4}
    qs.sort(key=lambda q: order[q["type"]])
    return qs[:limit]


def bank_stats():
    return {"skills_with_questions": sum(1 for v in BANK.values() if v),
            "questions": sum(len(v) for v in BANK.values())}


def _check_bank():
    for name in BANK:
        if BANK[name] and name not in ontology.NAME_TO_ID:
            raise ValueError("question bank skill not in ontology: " + name)


_check_bank()
