"""Skill ontology: ~220 skills with aliases, categories, prerequisites and families.

Table format (one skill per line):
    Name | Category | aliases | prerequisites | family | learning hours

Alias flags:
    =Go     case-sensitive everywhere ("Go" the language, not the verb "go")
    ~React  ambiguous word: any case inside a Skills section or a JD, exact case elsewhere
    react   plain alias, any case, anywhere

Prerequisites drive two things: the learning-path graph (topological sort) and implied
credit (knowing Django implies knowing Python). Skills in the same family are "related"
(Flask ~ Django) and earn partial credit. Learning hours are rough, approx. estimates
of time to job-ready basics, used only to pace a study plan.
"""
import re
from collections import OrderedDict

from .text import tokens_with_case

SKILL_TABLE = r"""
# ---- CS fundamentals
Programming Basics | CS Fundamentals | programming fundamentals, coding fundamentals, basics of programming | | | 20
Data Structures | CS Fundamentals | data structure | Programming Basics | | 40
Algorithms | CS Fundamentals | algorithm design, competitive programming, leetcode, codechef, codeforces | Data Structures | | 40
OOP | CS Fundamentals | object oriented programming, object-oriented programming, oops, oop concepts, object oriented design | Programming Basics | | 15
Design Patterns | CS Fundamentals | solid principles, gang of four | OOP | | 15
Operating Systems | CS Fundamentals | operating system, operating system concepts | Programming Basics | | 30
Computer Networks | CS Fundamentals | computer networking, networking fundamentals, tcp/ip, osi model | | | 30
Multithreading | CS Fundamentals | concurrency, multi-threading, multithreaded, parallel programming | Operating Systems | | 15
Asynchronous Programming | CS Fundamentals | asyncio, async/await, event loop | Programming Basics | | 8
System Design | CS Fundamentals | high level design, low level design, scalable systems, =HLD, =LLD | Database Fundamentals, Computer Networks | | 40
Distributed Systems | CS Fundamentals | distributed computing, event-driven architecture, event driven architecture | System Design | | 40
HTTP | CS Fundamentals | http protocol, http/https, https protocol | | | 6
# ---- Mathematics
Statistics | Mathematics | statistical analysis, descriptive statistics, inferential statistics, applied statistics | | | 40
Probability | Mathematics | probability theory, probability distributions | | | 20
Hypothesis Testing | Mathematics | t-test, chi-square, anova, significance testing, statistical tests, statistical testing | Statistics | | 12
Linear Algebra | Mathematics | matrix algebra | | | 30
Calculus | Mathematics | differential calculus | | | 30
Discrete Mathematics | Mathematics | discrete maths, discrete math | | | 25
Regression Analysis | Mathematics | linear regression, logistic regression, regression models, multiple regression | Statistics | | 12
# ---- Languages
Python | Languages | python3, python 3, py | Programming Basics | | 40
Java | Languages | core java, java 8, java 11, java 17, j2ee, java ee | Programming Basics | jvm | 50
JavaScript | Languages | js, ecmascript, es6, es2015, vanilla js, vanilla javascript, java script | Programming Basics | | 40
TypeScript | Languages | =TS | JavaScript | | 20
C | Languages | =C, c language, c programming | Programming Basics | | 40
C++ | Languages | cpp, c plus plus | Programming Basics | | 50
C# | Languages | c sharp, csharp | Programming Basics | | 40
Go | Languages | =Go, golang, go lang | Programming Basics | | 30
Rust | Languages | ~Rust | Programming Basics | | 60
Kotlin | Languages | | Programming Basics | jvm | 30
Swift | Languages | ~Swift | Programming Basics | | 30
Dart | Languages | ~Dart | Programming Basics | | 20
PHP | Languages | php7, php 8 | Programming Basics | | 30
Ruby | Languages | ~Ruby | Programming Basics | | 30
Scala | Languages | | Java | jvm | 40
R | Languages | =R, r programming, r language, rstudio, r studio, ggplot2, tidyverse, dplyr | Programming Basics | | 30
MATLAB | Languages | | Programming Basics | | 20
Bash | Languages | shell scripting, shell script, shell scripts, bash scripting, =Shell | Linux | | 15
SQL | Databases | structured query language, sql queries, sql query, window functions, ctes | Database Fundamentals | | 25
# ---- Frontend
HTML | Frontend | html5, html 5 | | | 10
CSS | Frontend | css3, css 3 | HTML | | 15
React | Frontend | ~React, reactjs, react.js, react js, react hooks, react 18 | JavaScript, HTML, CSS | frontend-fw | 40
Angular | Frontend | ~Angular, angularjs, angular.js | TypeScript, HTML, CSS | frontend-fw | 45
Vue.js | Frontend | ~Vue, vuejs, vue.js, vue js, vue 3, nuxt, nuxt.js | JavaScript, HTML, CSS | frontend-fw | 30
Svelte | Frontend | sveltekit | JavaScript, HTML, CSS | frontend-fw | 20
Next.js | Frontend | nextjs, next js | React | | 20
Redux | Frontend | redux toolkit, rtk, zustand | React | | 15
jQuery | Frontend | | JavaScript | | 8
Bootstrap | Frontend | ~Bootstrap, bootstrap 5, bootstrap 4 | CSS | css-fw | 6
Tailwind CSS | Frontend | tailwind, tailwindcss | CSS | css-fw | 8
Material UI | Frontend | mui, material-ui, material ui | React | css-fw | 6
Sass | Frontend | ~Sass, scss | CSS | | 6
Webpack | Frontend | | JavaScript | bundler | 10
Vite | Frontend | vitejs | JavaScript | bundler | 5
Responsive Design | Frontend | responsive web design, responsive ui, responsive pages, responsive layouts, mobile-first, mobile first, media queries, responsive | CSS | | 10
Web Accessibility | Frontend | accessibility, a11y, wcag, aria, screen reader support | HTML | | 12
Web Performance | Frontend | core web vitals, lighthouse, page speed, lcp, lazy loading, code splitting | JavaScript | | 12
DOM | Frontend | dom manipulation, document object model | JavaScript | | 8
AJAX | Frontend | fetch api, axios, xhr | JavaScript | | 4
RxJS | Frontend | | JavaScript | | 12
D3.js | Frontend | d3, d3js | JavaScript | js-viz | 15
Chart.js | Frontend | chartjs | JavaScript | js-viz | 4
Storybook | Frontend | | React | | 4
PWA | Frontend | progressive web apps, progressive web app, service workers | JavaScript | | 8
WordPress | Frontend | | PHP | | 10
# ---- Design
Figma | Design | | | design-tool | 10
Adobe XD | Design | | | design-tool | 8
Photoshop | Design | adobe photoshop | | | 15
UI/UX Design | Design | ui/ux, ux design, ui design, user experience design, user interface design, ux research | | | 30
Wireframing | Design | wireframes, prototyping, mockups | | | 6
# ---- Backend
Node.js | Backend | ~Node, nodejs, node.js, node js | JavaScript | js-backend | 30
Express.js | Backend | ~Express, expressjs, express.js, express js | Node.js | js-backend | 15
Django | Backend | django orm | Python | py-web | 35
Flask | Backend | | Python | py-web | 20
FastAPI | Backend | fast api | Python | py-web | 15
Django REST Framework | Backend | drf, django rest, django-rest-framework | Django, REST APIs | | 15
Spring Boot | Backend | ~Spring, springboot, spring framework, spring mvc, spring cloud | Java | java-web | 40
Hibernate | Backend | jpa | Java, SQL | orm | 15
.NET | Backend | dotnet, asp.net, .net core, asp.net core | C# | | 40
Laravel | Backend | | PHP | | 25
Ruby on Rails | Backend | ror, =Rails | Ruby | | 30
REST APIs | Backend | =REST, rest api, rest apis, restful, restful api, restful apis, restful services, rest endpoints, restful endpoints, api development, apis, web apis, api design, rest api design | HTTP | api-style | 15
GraphQL | Backend | graph ql, apollo graphql | HTTP | api-style | 15
gRPC | Backend | protocol buffers, protobuf | HTTP | api-style | 12
Microservices | Backend | microservice, microservices architecture, micro services, micro-services, service oriented architecture | REST APIs, Docker | | 25
Celery | Backend | | Python | task-queue | 10
SQLAlchemy | Backend | sql alchemy | Python, SQL | orm | 10
WebSockets | Backend | websocket, web sockets, socket.io, socketio | HTTP | | 8
API Documentation | Backend | swagger, openapi, open api, api docs | REST APIs | | 4
RabbitMQ | Backend | rabbit mq | | message-queue | 10
Apache Kafka | Big Data | kafka | | message-queue | 20
# ---- Databases
Database Fundamentals | Databases | dbms, rdbms, database management systems, database management, database design, normalization, relational databases, relational database | | | 15
MySQL | Databases | my sql | SQL | sql-db | 12
PostgreSQL | Databases | postgres, psql | SQL | sql-db | 15
SQLite | Databases | sqlite3 | SQL | sql-db | 5
Oracle Database | Databases | ~Oracle, oracle db, pl/sql, plsql | SQL | sql-db | 20
SQL Server | Databases | ms sql, mssql, microsoft sql server, ms sql server, t-sql, tsql | SQL | sql-db | 15
NoSQL | Databases | non-relational databases, nosql databases | Database Fundamentals | | 10
MongoDB | Databases | mongo, mongo db, mongoose | NoSQL | nosql-db | 15
Redis | Databases | redis cache | Database Fundamentals | | 8
Cassandra | Databases | ~Cassandra, apache cassandra | NoSQL | nosql-db | 15
DynamoDB | Databases | dynamo db, amazon dynamodb | NoSQL, AWS | nosql-db | 8
Elasticsearch | Databases | elastic search, elk stack, opensearch, kibana | | | 15
Firebase | Databases | firestore | | | 8
Data Modeling | Databases | data modelling, er diagrams, er diagram, entity relationship, schema design | Database Fundamentals | | 12
# ---- Data & analytics
Excel | Data & Analytics | ~Excel, ms excel, microsoft excel, advanced excel, excel basics, spreadsheets, vlookup, xlookup, pivot tables, pivot table, excel macros, vba | | spreadsheet | 15
Google Sheets | Data & Analytics | google spreadsheets | | spreadsheet | 5
Pandas | Data & Analytics | | Python | | 20
NumPy | Data & Analytics | | Python | | 10
Data Analysis | Data & Analytics | data analytics, analyzing data, analysing data, exploratory data analysis, =EDA | Statistics | | 30
Data Visualization | Data & Analytics | data visualisation, visualization, visualisation, dashboards, dashboard, dashboarding, data viz | | | 15
Tableau | Data & Analytics | tableau desktop, tableau public | Data Visualization | bi-tool | 20
Power BI | Data & Analytics | powerbi, power-bi, =DAX, power query | Data Visualization | bi-tool | 20
Looker | Data & Analytics | looker studio, google data studio, data studio | Data Visualization | bi-tool | 10
Matplotlib | Data & Analytics | | Python | py-viz | 8
Seaborn | Data & Analytics | | Matplotlib | py-viz | 5
Plotly | Data & Analytics | plotly dash | Python | py-viz | 6
Data Cleaning | Data & Analytics | data cleansing, data wrangling, data preprocessing, data preparation, cleaned data, cleaning data, clean data, deduplication, missing values, outlier treatment | | | 10
Reporting | Data & Analytics | =MIS, mis reports, mis reporting, business reporting, weekly reporting, kpi reporting, kpi dashboards | | | 8
Google Analytics | Data & Analytics | =GA4, google analytics 4 | | | 8
Data Storytelling | Data & Analytics | storytelling with data, presenting insights, insight communication | Data Visualization | | 8
A/B Testing | Data & Analytics | ab testing, a/b tests, a/b test, split testing, experimentation, online experiments | Hypothesis Testing | | 12
SAS | Data & Analytics | =SAS, sas programming | Statistics | stats-tool | 20
SPSS | Data & Analytics | ibm spss | Statistics | stats-tool | 15
Jupyter | Tools & Practices | jupyter notebook, jupyter notebooks, jupyterlab, google colab, colab, ipython | Python | | 3
# ---- Data engineering / big data
ETL | Data Engineering | etl pipelines, etl pipeline, extract transform load, data pipelines, data pipeline, =ELT | SQL | | 20
Data Warehousing | Data Engineering | data warehouse, star schema, snowflake schema, =DWH, dimensional modeling | SQL, Data Modeling | | 20
Snowflake | Data Engineering | ~Snowflake | SQL | cloud-dwh | 12
BigQuery | Data Engineering | google bigquery, big query | SQL | cloud-dwh | 10
Redshift | Data Engineering | ~Redshift, amazon redshift, aws redshift | SQL | cloud-dwh | 10
Airflow | Data Engineering | ~Airflow, apache airflow | Python | | 12
dbt | Data Engineering | =dbt, data build tool | SQL | | 10
Apache Spark | Big Data | ~Spark, pyspark, apache spark, spark sql, spark streaming | Python, SQL | big-data | 30
Hadoop | Big Data | hdfs, mapreduce, map reduce, apache hive, ~Hive, apache hadoop | Java | big-data | 30
# ---- ML & AI
Machine Learning | ML & AI | =ML, machine-learning, ml models, ml model, ml algorithms, supervised learning, unsupervised learning | Python, Statistics, Linear Algebra | | 60
Artificial Intelligence | ML & AI | =AI, artificial-intelligence | Programming Basics | | 30
Deep Learning | ML & AI | neural networks, neural network, deep neural networks, =CNN, =CNNs, =RNN, =LSTM | Machine Learning | | 50
scikit-learn | ML & AI | sklearn, scikit learn | Python, Machine Learning | | 15
TensorFlow | ML & AI | tensorflow 2 | Deep Learning | dl-fw | 25
PyTorch | ML & AI | pytorch lightning | Deep Learning | dl-fw | 25
Keras | ML & AI | | Deep Learning | dl-fw | 10
NLP | ML & AI | natural language processing, text mining, text analytics, text classification, sentiment analysis, named entity recognition | Machine Learning | | 40
Computer Vision | ML & AI | image processing, image classification, object detection, yolo | Deep Learning | | 40
OpenCV | ML & AI | open cv, cv2 | Python | | 12
Transformers | ML & AI | hugging face, huggingface, bert, gpt, attention mechanism, transformer models | Deep Learning, NLP | | 25
LLMs | ML & AI | llm, large language models, large language model, generative ai, genai, gen ai | Transformers | | 20
Prompt Engineering | ML & AI | prompting, prompt design | LLMs | | 6
RAG | ML & AI | =RAG, retrieval augmented generation, retrieval-augmented generation, vector database, vector databases, vector search | LLMs | | 12
LangChain | ML & AI | llamaindex | LLMs, Python | | 10
Tree Ensembles | ML & AI | xgboost, xgb, lightgbm, catboost, gradient boosting, random forest, random forests, decision tree, decision trees | Machine Learning | | 10
Feature Engineering | ML & AI | feature selection, feature extraction, feature pipelines, feature store | Machine Learning | | 15
MLOps | ML & AI | model deployment, model serving, ml deployment, mlflow, deployed models, served models | Machine Learning, Docker | | 20
Time Series | ML & AI | time series analysis, time-series, forecasting, arima | Statistics | | 20
Recommendation Systems | ML & AI | recommender systems, recommender system, recommendation engine, collaborative filtering, recommender | Machine Learning | | 20
Reinforcement Learning | ML & AI | | Machine Learning | | 40
Clustering | ML & AI | k-means, kmeans, hierarchical clustering, dbscan, customer segmentation | Machine Learning | | 10
Data Science | ML & AI | | Statistics, Python | | 40
Model Evaluation | ML & AI | cross-validation, cross validation, roc auc, =AUC, confusion matrix, f1 score, precision@10 | Machine Learning | | 8
# ---- Cloud & DevOps
Linux | Cloud & DevOps | ubuntu, unix, centos, red hat, rhel, debian, linux administration, linux command line | | | 20
Git | Tools & Practices | version control, gitflow, git flow, github, gitlab, bitbucket | | | 8
Docker | Cloud & DevOps | containers, containerization, containerisation, containerised, containerized, containerise, dockerfile, dockerfiles, docker compose, docker-compose | Linux | | 15
Kubernetes | Cloud & DevOps | k8s, kubectl, ~Helm, helm charts, =EKS, =AKS, =GKE, openshift | Docker | | 30
AWS | Cloud & DevOps | amazon web services, ec2, s3, rds, aws cloud | Cloud Computing | cloud | 40
Azure | Cloud & DevOps | microsoft azure, azure cloud, azure devops | Cloud Computing | cloud | 40
GCP | Cloud & DevOps | google cloud, google cloud platform | Cloud Computing | cloud | 40
Cloud Computing | Cloud & DevOps | cloud, cloud services, cloud platforms, cloud infrastructure | | | 15
CI/CD | Cloud & DevOps | ci/cd pipelines, cicd, continuous integration, continuous delivery, continuous deployment, =CI | Git | | 12
Jenkins | Cloud & DevOps | ~Jenkins, jenkins pipelines | CI/CD | ci-tool | 10
GitHub Actions | Cloud & DevOps | gh actions, github workflows | CI/CD | ci-tool | 6
GitLab CI | Cloud & DevOps | gitlab ci/cd, gitlab-ci, gitlab pipelines | CI/CD | ci-tool | 6
Terraform | Cloud & DevOps | infrastructure as code, =IaC | Cloud Computing | iac | 20
Ansible | Cloud & DevOps | | Linux | iac | 15
Prometheus | Cloud & DevOps | ~Prometheus | Linux | monitoring | 10
Grafana | Cloud & DevOps | | | monitoring | 6
Serverless | Cloud & DevOps | aws lambda, azure functions, cloud functions, lambda functions | Cloud Computing | | 10
Nginx | Cloud & DevOps | | Linux | | 8
Heroku | Cloud & DevOps | | | | 3
# ---- Mobile
Android | Mobile | android development, android sdk, android studio, android apps | Kotlin | mobile-native | 40
iOS | Mobile | =iOS, ios development, xcode, ios apps | Swift | mobile-native | 40
Flutter | Mobile | ~Flutter | Dart | cross-platform | 30
React Native | Mobile | react-native | React | cross-platform | 25
SwiftUI | Mobile | | Swift | | 15
Jetpack Compose | Mobile | | Kotlin, Android | | 15
# ---- Testing
Unit Testing | Testing | unit tests, unit test, unittest, mockito, jasmine, karma, test coverage | Programming Basics | | 10
TDD | Testing | test driven development, test-driven development | Unit Testing | | 8
PyTest | Testing | | Python, Unit Testing | unit-test-fw | 6
JUnit | Testing | junit5, junit 5 | Java, Unit Testing | unit-test-fw | 6
Jest | Testing | jestjs | JavaScript, Unit Testing | unit-test-fw | 6
React Testing Library | Testing | =RTL, testing library | Jest, React | | 6
Cypress | Testing | ~Cypress, cypress.io | JavaScript | e2e-test | 8
Selenium | Testing | ~Selenium, selenium webdriver, webdriver | Programming Basics | e2e-test | 12
Playwright | Testing | ~Playwright | JavaScript | e2e-test | 8
Postman | Testing | postman collections | REST APIs | | 4
Manual Testing | Testing | test cases, test case design, functional testing, regression testing, bug tracking, test plans | | | 10
Integration Testing | Testing | integration tests, end-to-end testing, end to end testing, e2e testing, e2e tests | Unit Testing | | 8
Performance Testing | Testing | load testing, stress testing, jmeter, locust | | | 10
# ---- Tools & practices
Agile | Tools & Practices | scrum, kanban, agile methodology, agile methodologies, sprint planning, sprints | | | 6
JIRA | Tools & Practices | confluence | Agile | | 3
Code Review | Tools & Practices | code reviews, peer code review, reviewed code, pull request reviews | Git | | 4
Debugging | Tools & Practices | troubleshooting, root cause analysis, bug fixing, fixed bugs | Programming Basics | | 10
Technical Documentation | Tools & Practices | technical writing, documentation | | | 6
# ---- Business & office
Microsoft Office | Business | ms office, microsoft office, ms word, microsoft word, ms powerpoint, powerpoint, ms-office | | | 6
Tally | Business | tally erp, tally erp 9, tally prime | | | 15
SAP | Business | =SAP, sap erp, sap fico, sap mm, sap sd | | | 40
Salesforce | Business | salesforce crm, sfdc | | | 25
Accounting | Business | bookkeeping, accounts payable, accounts receivable, =GST | | | 30
Data Entry | Business | typing | | | 5
Project Management | Business | =PMP, project planning, project coordination | | | 20
Six Sigma | Business | lean six sigma, six sigma green belt, =DMAIC | | | 20
Digital Marketing | Business | =SEO, =SEM, social media marketing, search engine optimization, content marketing | | | 20
# ---- Core engineering
AutoCAD | Core Engineering | auto cad, autocad 2d | | cad | 20
SolidWorks | Core Engineering | solid works | | cad | 25
STAAD Pro | Core Engineering | staad, staad.pro | | | 20
ANSYS | Core Engineering | | | | 25
Quantity Surveying | Core Engineering | quantity estimates, quantity estimation, bar bending schedules, estimation and costing | | | 20
Embedded Systems | Core Engineering | embedded c, microcontrollers, microcontroller, arduino, raspberry pi, arm cortex | C | | 40
IoT | Core Engineering | internet of things, =IoT | Embedded Systems | | 30
VLSI | Core Engineering | verilog, vhdl, systemverilog, fpga | | | 50
PLC | Core Engineering | =PLC, plc programming, scada | | | 30
# ---- Security
OAuth & JWT | Security | oauth, oauth2, oauth 2.0, jwt, json web tokens, json web token | HTTP | | 10
Web Security | Security | owasp, owasp top 10, xss, csrf, sql injection, application security, appsec | HTTP | | 20
Cybersecurity | Security | cyber security, information security, infosec | Computer Networks | | 40
Network Security | Security | firewalls, firewall, =VPN | Computer Networks | | 30
Penetration Testing | Security | pen testing, pentesting, ethical hacking, burp suite, metasploit, =VAPT | Network Security, Web Security | | 40
Cryptography | Security | encryption, hashing algorithms | | | 30
# ---- Soft skills (reported, never scored: judged in interview, not from keywords)
Communication | Soft Skills | communication skills, verbal communication, written communication, good communication, excellent communication | | | 10
Teamwork | Soft Skills | team player, collaboration, cross-functional collaboration, team work | | | 5
Leadership | Soft Skills | team lead, led a team, led team, mentoring, mentored, people management | | | 10
Problem Solving | Soft Skills | problem-solving, problem solving skills, analytical thinking, critical thinking, analytical skills | | | 10
Stakeholder Management | Soft Skills | stakeholder communication, client communication, stakeholders, client handling | Communication | | 10
Time Management | Soft Skills | | | | 4
Presentation Skills | Soft Skills | public speaking, presentations, presented to | Communication | | 6
"""

# One phrase that legitimately names two skills at once.
MULTI_ALIASES = {
    "data structures and algorithms": ["Data Structures", "Algorithms"],
    "data structures algorithms": ["Data Structures", "Algorithms"],
    "dsa": ["Data Structures", "Algorithms"],
    "ds algo": ["Data Structures", "Algorithms"],
    "mern": ["MongoDB", "Express.js", "React", "Node.js"],
    "mean stack": ["MongoDB", "Express.js", "Angular", "Node.js"],
    "ai/ml": ["Artificial Intelligence", "Machine Learning"],
}

SOFT_CATEGORY = "Soft Skills"


def slug(name):
    s = name.lower().replace("c++", "cpp").replace("c#", "csharp").replace(".net", "dotnet")
    s = s.replace("/", " ").replace("&", " and ").replace(".", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


class Skill(object):
    __slots__ = ("id", "name", "category", "prereqs", "family", "hours", "aliases")

    def __init__(self, sid, name, category, prereqs, family, hours, aliases):
        self.id, self.name, self.category = sid, name, category
        self.prereqs, self.family, self.hours, self.aliases = prereqs, family, hours, aliases

    def to_dict(self):
        return {"id": self.id, "name": self.name, "category": self.category,
                "prereqs": list(self.prereqs), "family": self.family, "hours": self.hours,
                "aliases": [a for a, _ in self.aliases]}


class OntologyError(ValueError):
    pass


def _parse_table(table):
    rows = []
    for raw in table.strip().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 6:
            raise OntologyError("bad ontology row: %r" % line)
        rows.append(parts)
    return rows


def build(table=SKILL_TABLE, multi=MULTI_ALIASES):
    """Parse the table into skills + an alias index keyed by lower-case token tuples."""
    rows = _parse_table(table)
    by_name = OrderedDict()
    for name, cat, aliases, _pre, _fam, _hrs in rows:
        if name in by_name:
            raise OntologyError("duplicate skill %s" % name)
        by_name[name] = None
    skills = OrderedDict()
    name_to_id = {}
    for name, cat, aliases, pre, fam, hrs in rows:
        sid = slug(name)
        if sid in skills:
            raise OntologyError("duplicate skill id %s" % sid)
        prereqs = [p.strip() for p in pre.split(",") if p.strip()]
        for p in prereqs:
            if p not in by_name:
                raise OntologyError("%s: unknown prerequisite %s" % (name, p))
        alias_list = []
        flagged = set()
        for a in [x.strip() for x in aliases.split(",") if x.strip()]:
            mode = "any"
            if a[0] in "=~":
                mode = "cs" if a[0] == "=" else "amb"
                a = a[1:]
            alias_list.append((a, mode))
            if a.lower() == name.lower():
                flagged.add(a.lower())
        if name.lower() not in flagged:
            alias_list.insert(0, (name, "any"))
        skills[sid] = Skill(sid, name, cat, prereqs, fam or None, float(hrs or 10), alias_list)
        name_to_id[name] = sid
    for s in skills.values():
        s.prereqs = tuple(name_to_id[p] for p in s.prereqs)

    index = {}

    def add(alias, mode, targets, owner):
        toks = tokens_with_case(alias)
        if not toks:
            return
        key = tuple(t.lower() for t in toks)
        entry = (tuple(targets), mode, tuple(toks))
        existing = index.setdefault(key, [])
        for e in existing:
            if e[0] == entry[0] and e[1] == entry[1]:
                return
            if e[1] == mode and e[0] != entry[0]:
                raise OntologyError("alias %r used by %s and %s" % (alias, e[0], owner))
        existing.append(entry)

    for s in skills.values():
        for a, mode in s.aliases:
            add(a, mode, [s.id], s.name)
    for phrase, names in multi.items():
        add(phrase, "any", [name_to_id[n] for n in names], phrase)
    first = {}
    for key in index:
        first[key[0]] = max(first.get(key[0], 0), len(key))
    return skills, index, first, name_to_id


SKILLS, ALIAS_INDEX, FIRST_TOKEN_MAXLEN, NAME_TO_ID = build()
CATEGORIES = sorted({s.category for s in SKILLS.values()})


def get(sid):
    return SKILLS[sid]


def name_of(sid):
    return SKILLS[sid].name


def is_soft(sid):
    return SKILLS[sid].category == SOFT_CATEGORY


def prereq_closure(sid):
    """{prereq_id: depth} for every transitive prerequisite of a skill."""
    out = {}
    frontier = [(p, 1) for p in SKILLS[sid].prereqs]
    while frontier:
        nxt = []
        for p, d in frontier:
            if p not in out or d < out[p]:
                out[p] = d
                nxt.extend((q, d + 1) for q in SKILLS[p].prereqs)
        frontier = nxt
    return out


def dependents():
    """Reverse prerequisite edges: {skill: [skills that require it]}."""
    rev = {sid: [] for sid in SKILLS}
    for s in SKILLS.values():
        for p in s.prereqs:
            rev[p].append(s.id)
    return rev


def stats():
    by_cat = OrderedDict()
    for c in CATEGORIES:
        by_cat[c] = sum(1 for s in SKILLS.values() if s.category == c)
    return {
        "skills": len(SKILLS),
        "aliases": sum(len(v) for v in ALIAS_INDEX.values()),
        "prerequisite_edges": sum(len(s.prereqs) for s in SKILLS.values()),
        "families": len({s.family for s in SKILLS.values() if s.family}),
        "by_category": by_cat,
    }
