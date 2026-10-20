"""Deterministic demo data: 3 job descriptions and 20 synthetic resumes.

Resume *content* is hand-written per archetype (strong, alias-worded, weak bullets,
keyword-stuffed, career switcher, fresher, unrelated...). Identity fields - name, gender,
college, city, contact - are filled in by a seeded RNG so they vary independently of
quality. That independence is what lets the bias check show identity has no effect.

Every person, company and contact detail here is fictional.

    python -m resumeradar.demo      # writes data/demo.json
"""
import json
import os
import random

SEED = 2026

JDS = [
    {"id": "jd-backend", "title": "Python Backend Developer", "text": """Python Backend Developer - Product Engineering (Chennai / Hybrid)

About the role
We are a SaaS product company building billing and analytics APIs used by 2,000+ businesses. You will design, build and run backend services end to end.

Responsibilities
- Build and maintain REST APIs and background jobs in Python
- Design PostgreSQL schemas and write efficient SQL queries
- Containerise services with Docker and ship them through CI/CD pipelines
- Write unit tests, review code and improve reliability

Must have
- 1+ years of professional experience building backend services
- Strong Python and Django or Flask
- REST API design and PostgreSQL (or MySQL)
- Git, Docker and the Linux command line
- Unit testing with PyTest

Nice to have
- AWS, Redis and Celery
- CI/CD with GitHub Actions or Jenkins
- Exposure to Kubernetes

Education
- B.E./B.Tech in Computer Science, IT or a related field
- Candidates from premier institutes like IIT/NIT preferred. Age below 28 years.
"""},
    {"id": "jd-analyst", "title": "Data Analyst", "text": """Data Analyst - Business Insights Team (Bengaluru)

About the role
Turn raw sales and product data into decisions. You will own weekly dashboards and ad-hoc analysis for the leadership team.

Responsibilities
- Write SQL to extract and clean data from the warehouse
- Build dashboards in Tableau or Power BI
- Analyse A/B tests and explain results to business stakeholders

Requirements
- 0-2 years of experience (freshers with strong projects welcome)
- SQL, Excel (pivot tables, VLOOKUP) and Statistics
- Python with Pandas for data cleaning
- Tableau or Power BI
- Good communication and storytelling with data

Good to have
- A/B testing, Google Analytics, R
- Basic Machine Learning (regression, clustering)

Education
- Bachelor's degree in any discipline (Statistics, Mathematics, Engineering or Commerce preferred)
"""},
    {"id": "jd-frontend", "title": "Frontend Developer (React)", "text": """Frontend Developer (React) - Consumer Web (Remote, India)

About the role
Build fast, accessible web apps used by millions of shoppers.

Responsibilities
- Build responsive UI components in React and TypeScript
- Integrate REST APIs and manage state with Redux
- Write tests with Jest and React Testing Library
- Improve Core Web Vitals and accessibility

Must have
- 1+ years building production web apps
- JavaScript (ES6+), React, HTML5 and CSS3
- TypeScript
- REST APIs and Git
- Responsive design

Nice to have
- Next.js, Redux, Tailwind CSS
- Jest / React Testing Library
- Web accessibility (WCAG) and web performance

Education
- Degree in Computer Science or equivalent practical experience
"""},
]

# Hand-labelled relevance (0 = not relevant, 1 = weak, 2 = good, 3 = strong) for every
# resume against every JD, written by reading the resume content only (no scores seen).
# Order of the tuple: (backend, analyst, frontend).
LABELS = {
    "R01": (3, 1, 0), "R02": (3, 0, 0), "R03": (2, 0, 0), "R04": (2, 1, 0), "R05": (1, 0, 1),
    "R06": (1, 0, 0), "R07": (3, 1, 0), "R08": (0, 3, 0), "R09": (0, 2, 0), "R10": (0, 2, 0),
    "R11": (0, 2, 0), "R12": (1, 2, 0), "R13": (0, 1, 0), "R14": (0, 0, 3), "R15": (0, 0, 3),
    "R16": (0, 0, 1), "R17": (0, 0, 2), "R18": (0, 0, 2), "R19": (1, 0, 2), "R20": (0, 0, 0),
}
JD_ORDER = ["jd-backend", "jd-analyst", "jd-frontend"]

FEMALE = ["Priya", "Divya", "Lakshmi", "Ananya", "Kavya", "Meera", "Sneha", "Fathima", "Harini", "Nandhini",
          "Aishwarya", "Swathi", "Pooja", "Sowmya", "Ritika", "Janani", "Keerthana", "Ayesha", "Deepa", "Shruti"]
MALE = ["Arun", "Karthik", "Rahul", "Vignesh", "Mohammed", "Sanjay", "Pranav", "Harish", "Aditya", "Surya",
        "Rohit", "Gokul", "Naveen", "Ajay", "Dinesh", "Imran", "Varun", "Siddharth", "Manoj", "Ashwin"]
SURNAMES = ["Sharma", "Iyer", "Raman", "Krishnan", "Nair", "Reddy", "Patel", "Kumar", "Subramanian", "Joseph",
            "Fernandes", "Das", "Menon", "Rao", "Banerjee", "Khan", "Pillai", "Murugan", "Gupta", "Thomas"]
COLLEGES_TOP = ["IIT Madras", "NIT Trichy", "BITS Pilani", "IIIT Hyderabad", "IIT Bombay"]
COLLEGES_MID = ["PSG College of Technology", "Anna University", "K.S.R. College of Engineering",
                "Kongu Engineering College", "Coimbatore Institute of Technology", "SRM Institute of Science and Technology"]
COLLEGES_LOCAL = ["Government Arts College", "Sri Vidya Mandir Arts and Science College",
                  "Vivekanandha College of Engineering for Women", "St. Joseph's College",
                  "Bharathi Women's College", "Sri Ramakrishna Mission Vidyalaya College"]
CITIES = ["Chennai", "Coimbatore", "Bengaluru", "Hyderabad", "Salem", "Madurai", "Tiruchengode", "Erode", "Pune", "Kochi"]

# Templates. Placeholders: {NAME} {EMAIL} {PHONE} {CITY} {COLLEGE} {COLLEGE2} {HANDLE}
# {PRONOUN} (He/She) {GENDER} (Male/Female) {FATHER}
TEMPLATES = [
    ("R01", "Backend - strong (4 yrs Django/AWS)", "mid", """{NAME}
Backend Engineer | {CITY} | {EMAIL} | {PHONE} | linkedin.com/in/{HANDLE} | github.com/{HANDLE}

SUMMARY
Backend engineer with 3+ years of experience building Python/Django services and REST APIs on AWS.

EXPERIENCE
Software Engineer II, Finlytics Pvt Ltd - Jul 2023 - Present
- Designed and built 25+ REST APIs in Django REST Framework serving 1.2M requests/day with p95 latency under 120 ms
- Cut PostgreSQL query time by 60% by adding composite indexes and rewriting ORM queries
- Containerised 6 services with Docker and shipped them via GitHub Actions CI/CD, reducing release time from 2 days to 2 hours
- Introduced Celery + Redis background jobs for invoice generation, processing 40,000 invoices nightly
Software Engineer, CodeNest Labs - Aug 2022 - Jun 2023
- Built a Flask microservice for payment webhooks with 99.9% uptime
- Wrote PyTest suites that raised test coverage from 45% to 85%

PROJECTS
OpenLedger (Python, FastAPI, PostgreSQL)
- Open-source double-entry ledger API with 300+ GitHub stars

SKILLS
Languages: Python, SQL, Bash
Frameworks: Django, Django REST Framework, Flask, FastAPI, Celery
Data & Cloud: PostgreSQL, Redis, AWS (EC2, S3, RDS), Docker, Linux, Git, GitHub Actions
Practices: Unit testing (PyTest), code review, Agile

EDUCATION
B.Tech, Computer Science and Engineering - {COLLEGE}, 2022 - CGPA 8.4/10

CERTIFICATIONS
AWS Certified Developer - Associate
"""),
    ("R02", "Backend - alias-worded (DRF, Postgres, k8s)", "local", """{NAME}
{EMAIL} . {PHONE} . {CITY}

PROFILE
Py dev who likes clean APIs. 2 yrs building RESTful services w/ DRF + Postgres.

WORK EXPERIENCE
Associate Software Developer - Zentrix Technologies (Oct 2024 - Present)
* Developed RESTful services in DRF for a logistics platform used by 300 warehouses
* Migrated legacy MySQL tables to Postgres with zero downtime (2 TB of data)
* Wrote dockerfiles and k8s manifests; automated deploys with Jenkins pipelines on Ubuntu servers
* Added pytest tests for 40 endpoints; production bugs fell 35%
Trainee (Intern) - Zentrix Technologies (Apr 2024 - Sep 2024)
* Built internal admin dashboards with Django templates

TECHNICAL SKILLS
Py, DRF, Postgres, MySQL, Redis, docker, k8s, Jenkins, git, Linux (Ubuntu), REST

EDUCATION
B.E. Information Technology, {COLLEGE} (2024) - 7.9 CGPA
"""),
    ("R03", "Backend - medium, weak bullets (Flask)", None, """{NAME}
{CITY} | {PHONE} | {EMAIL}

Objective
To work in a challenging environment where I can use my skills for the growth of the organisation.

Experience
Python Developer, Brightwave Solutions, Mar 2025 - Present
- Responsible for developing APIs using Flask
- Worked on MySQL database
- Involved in testing and bug fixing
- Helped the team in deployment

Skills
Python, Flask, MySQL, HTML, CSS, Git, Problem solving

Education
B.Sc Computer Science, {COLLEGE}, 2024, 72%

Personal Details
Date of Birth: 14-02-2003
Gender: {GENDER}
Marital Status: Single
Languages Known: English, Tamil
"""),
    ("R04", "Backend - fresher with Django projects", "top", """{NAME}
Final-year B.Tech (CSE) student | {EMAIL} | {PHONE} | github.com/{HANDLE}

CAREER OBJECTIVE
Aspiring backend developer. {PRONOUN} has built three Django projects and completed a 6-month backend internship.

INTERNSHIP
Backend Intern, Kovai Startups Hub - Jan 2026 - Jun 2026
- Built 8 REST APIs with Django REST Framework for a food-delivery MVP
- Wrote SQL reports in PostgreSQL that the operations team used daily
- Set up Docker Compose for local development, cutting onboarding time from 1 day to 1 hour

PROJECTS
CampusConnect - Django, PostgreSQL, Bootstrap
- Event portal used by 1,500 students across 4 departments
- Implemented JWT login and role-based access
LibraryBot - Python, Flask, SQLite
- Chat bot that answers library queries; handles 200 queries a week

TECHNICAL SKILLS
Python, Django, Flask, SQL, PostgreSQL, SQLite, Git, Docker, HTML, CSS, Linux
Data Structures and Algorithms (300+ LeetCode problems)

EDUCATION
B.Tech Computer Science and Engineering, {COLLEGE} - 2027 (expected), CGPA 8.9/10

CERTIFICATIONS
NPTEL - Programming, Data Structures and Algorithms using Python (Elite)
"""),
    ("R05", "Keyword-stuffed, no evidence", "top", """{NAME}
{EMAIL} {PHONE}

SKILLS
Python, Java, C, C++, C#, JavaScript, TypeScript, Go, Rust, Kotlin, Swift, PHP, Ruby, Scala, R, MATLAB, Django, Flask, FastAPI, Spring Boot, Node.js, Express, React, Angular, Vue.js, Next.js, PostgreSQL, MySQL, MongoDB, Redis, Cassandra, AWS, Azure, GCP, Docker, Kubernetes, Terraform, Jenkins, Kafka, Spark, Hadoop, TensorFlow, PyTorch, Machine Learning, Deep Learning, NLP, Blockchain, Linux, Git

EXPERIENCE
Customer Support Executive, QuickServe BPO - Jun 2025 - Mar 2026
- Handled customer calls and emails
- Maintained records in Excel

EDUCATION
BCA, {COLLEGE}, 2025

Photo: attached
Age: 23
"""),
    ("R06", "Java backend (Spring Boot), no Python", None, """{NAME}
Java Backend Developer - {CITY}
{EMAIL} | {PHONE}

SUMMARY
Java developer with 4 years of experience in Spring Boot microservices for banking clients.

EXPERIENCE
Senior Software Engineer, Northbridge Banking Software - May 2023 - Present
- Built 15 Spring Boot microservices handling 3M transactions a month
- Reduced API response time by 40% through Redis caching
- Wrote JUnit and Mockito tests, keeping coverage above 80%
- Deployed services to Kubernetes on Azure with Jenkins pipelines
Software Engineer, Northbridge Banking Software - Jul 2022 - Apr 2023
- Developed REST APIs with Spring MVC and Hibernate on MySQL

SKILLS
Java, Spring Boot, Hibernate, MySQL, Oracle, Redis, REST APIs, Microservices, Docker, Kubernetes, Jenkins, Azure, Git, Linux

EDUCATION
B.E. Electronics and Communication Engineering, {COLLEGE}, 2022
"""),
    ("R07", "Senior backend (8 yrs Python/Go)", "local", """{NAME}
Staff Engineer . Distributed Systems . {CITY} . {EMAIL} . {PHONE}

SUMMARY
Engineer with 8 years of experience designing high-scale Python and Go services; led teams of up to 6 engineers.

EXPERIENCE
Staff Software Engineer, Streamline Commerce - Jan 2022 - Present
- Led a team of 6 engineers to re-architect the order platform into 30 microservices, cutting infrastructure cost by 28%
- Designed event-driven pipelines on Kafka processing 50M events a day
- Mentored 9 engineers; 4 were promoted
Senior Software Engineer, Streamline Commerce - Jun 2019 - Dec 2021
- Built Django and FastAPI services on PostgreSQL with 99.95% availability
- Introduced Kubernetes and Terraform on AWS, reducing deployment failures by 70%
Software Engineer, ByteForge - Jul 2018 - May 2019
- Developed Flask APIs and Celery workers for report generation

SKILLS
Python, Go, SQL, Django, FastAPI, Flask, Celery, PostgreSQL, Redis, Kafka, Docker, Kubernetes, Terraform, AWS, Prometheus, Grafana, Git, Linux, System Design, CI/CD

EDUCATION
M.Tech Computer Science, {COLLEGE}, 2018
B.Tech Information Technology, {COLLEGE2}, 2016
"""),
    ("R08", "Data analyst - strong (SQL/Tableau/A-B tests)", "local", """{NAME}
Data Analyst | {EMAIL} | {PHONE} | {CITY} | linkedin.com/in/{HANDLE}

SUMMARY
Data analyst with 2 years of experience turning sales data into decisions using SQL, Python and Tableau.

EXPERIENCE
Data Analyst, RetailPulse Analytics - Sep 2024 - Present
- Built 12 Tableau dashboards tracking Rs 40 crore of monthly sales, used by 60 managers
- Wrote SQL (window functions, CTEs) on BigQuery to automate weekly reporting, saving 10 hours a week
- Analysed 18 A/B tests on checkout flows with hypothesis testing; one change lifted conversion by 4.2%
- Cleaned 5M-row sales data with Python and Pandas (deduplication, missing values)
Analytics Intern, RetailPulse Analytics - Mar 2024 - Aug 2024
- Automated Excel reports with pivot tables and VLOOKUP, cutting preparation time by 50%

PROJECTS
Churn Drivers Analysis (Python, Pandas, scikit-learn)
- Logistic regression model that identified the top 5 churn drivers (AUC 0.81); presented to leadership

SKILLS
SQL, Python, Pandas, NumPy, Excel, Tableau, Power BI, Statistics, A/B Testing, BigQuery, Matplotlib, Data Storytelling

EDUCATION
B.Sc Statistics, {COLLEGE}, 2024 - 86%
"""),
    ("R09", "Data analyst - medium (MIS, Excel/Power BI)", None, """{NAME}
{PHONE} | {EMAIL}

PROFILE
MIS executive with 1 year of experience preparing reports in Excel and Power BI.

EXPERIENCE
MIS Executive, Sunrise Logistics - Aug 2025 - Present
- Prepared daily MIS reports in Excel
- Responsible for maintaining Power BI dashboard
- Worked on data cleaning of shipment data

SKILLS
MS Excel (VLOOKUP, Pivot Tables), Power BI, SQL (basic), MS Office, Communication

EDUCATION
B.Com, {COLLEGE}, 2025, 68%

PERSONAL DETAILS
Father's Name: {FATHER}
Age: 22
Gender: {GENDER}
"""),
    ("R10", "Data analyst - fresher (Statistics, R, Python)", "mid", """{NAME}
{EMAIL} . {PHONE} . github.com/{HANDLE}

OBJECTIVE
Statistics graduate seeking an entry-level data analyst role.

PROJECTS
Cricket Match Outcome Analysis (R, ggplot2)
- Analysed 1,000+ matches and identified toss and venue effects with chi-square tests
Restaurant Ratings Insights (Python, Pandas, Matplotlib, Seaborn)
- Cleaned 50,000 rows of raw data and built a dashboard of rating drivers
- Built a linear regression model predicting ratings (R-squared 0.64)

SKILLS
Python, R, SQL, Pandas, Excel, Statistics, Hypothesis Testing, Tableau (basic), Jupyter

EDUCATION
B.Sc Statistics, {COLLEGE}, 2026 - CGPA 8.7/10

CERTIFICATIONS
Google Data Analytics Professional Certificate (Coursera)
"""),
    ("R11", "Career switcher: mechanical engineer to analytics", "local", """{NAME}
{CITY} | {EMAIL} | {PHONE}

SUMMARY
Mechanical engineer moving into analytics. 3 years in production planning, where {PRONOUN_LOWER} built Excel and SQL tools to track plant KPIs.

EXPERIENCE
Production Planning Engineer, Apex Auto Components - Jun 2023 - Present
- Built an SQL + Excel tracker for 120 machines, reducing unplanned downtime by 18%
- Created a Tableau dashboard for daily OEE reporting used by 3 plant heads
- Led a Six Sigma project that cut scrap by 12%

PROJECTS
Supply Delay Prediction (Python, Pandas)
- Analysed 2 years of supplier data to flag late deliveries 5 days early

SKILLS
Excel, SQL, Tableau, Python, Pandas, Statistics, Six Sigma, AutoCAD, SolidWorks

EDUCATION
B.E. Mechanical Engineering, {COLLEGE}, 2023

CERTIFICATIONS
Google Data Analytics Professional Certificate
"""),
    ("R12", "ML engineer (PyTorch, NLP)", "top", """{NAME}
Machine Learning Engineer | {EMAIL} | {PHONE} | github.com/{HANDLE}

SUMMARY
ML engineer with 2 years of experience shipping NLP and recommendation models to production.

EXPERIENCE
ML Engineer, Insightly Labs - Jul 2024 - Present
- Trained and deployed a BERT-based ticket classifier with PyTorch, automating 65% of support triage
- Built feature pipelines in Python, Pandas and SQL over 20M rows
- Served models with FastAPI and Docker at 80 ms p95 latency
- Ran offline A/B evaluations and reported results to product teams

PROJECTS
Movie Recommender (scikit-learn, Flask)
- Collaborative filtering recommender; improved precision@10 by 22% over a popularity baseline

SKILLS
Python, SQL, PyTorch, TensorFlow, scikit-learn, Pandas, NumPy, NLP, Transformers, Docker, FastAPI, Git, Statistics, Machine Learning

EDUCATION
M.Sc Data Science, {COLLEGE}, 2024
"""),
    ("R13", "Weak: B.Com, office skills", None, """{NAME}
{PHONE}

Career Objective: Seeking a job in a reputed company.

Education: B.Com (Computer Applications), {COLLEGE}, 2025

Skills: MS Office, Tally ERP, Typing (40 wpm), Excel basics

Experience: Accounts assistant (6 months) - did data entry and billing.

Personal Details: Age: 21, Marital Status: Unmarried, Nationality: Indian
Declaration: I hereby declare that the above information is true.
"""),
    ("R14", "Frontend - strong (React/TS/Next.js)", "local", """{NAME}
Frontend Engineer | {CITY} | {EMAIL} | {PHONE} | {HANDLE}.dev

SUMMARY
Frontend engineer with 3 years of experience building fast, accessible React and TypeScript apps.

EXPERIENCE
Frontend Engineer, ShopSphere - Jun 2023 - Present
- Rebuilt the product listing page in React, TypeScript and Next.js, improving LCP from 4.1 s to 1.8 s for 2M monthly users
- Migrated global state to Redux Toolkit, removing 3,000 lines of prop-drilling code
- Raised Jest and React Testing Library coverage from 30% to 82%
- Led a WCAG 2.1 AA accessibility audit and fixed 140 issues
Frontend Developer, PixelCraft Studio - Jul 2022 - May 2023
- Built 20+ responsive landing pages with Tailwind CSS and integrated REST APIs

SKILLS
JavaScript (ES6+), TypeScript, React, Next.js, Redux, HTML5, CSS3, Tailwind CSS, Jest, React Testing Library, Webpack, Git, Figma, Web Accessibility, Responsive Design

EDUCATION
B.E. Computer Science, {COLLEGE}, 2022
"""),
    ("R15", "Frontend - alias-worded (ReactJS, JS, TS)", "mid", """{NAME}
UI Developer - {EMAIL} - {PHONE}

ABOUT
UI developer (2 yrs) working with ReactJS, JS/ES6, TS and HTML5/CSS3.

WORK HISTORY
UI Developer, Webverse Digital | Nov 2024 - Present
- Built 30+ reusable ReactJS components with TS for a fintech dashboard used by 50k users
- Hooked up RESTful endpoints with Axios and RTK; page load time fell 35%
- Wrote unit tests in Jest and set up Storybook for the design system
Junior Web Developer, Webverse Digital | May 2024 - Oct 2024
- Converted Figma designs into responsive HTML5/CSS3 pages (mobile-first)

SKILLS
ReactJS, JS (ES6), TS, HTML5, CSS3, SCSS, RTK, Jest, git, Figma, mobile-first design

EDUCATION
BCA, {COLLEGE}, 2024
"""),
    ("R16", "Web developer - jQuery, no React", None, """{NAME}
Web Developer | {EMAIL} | {PHONE}

SUMMARY
Web developer with 2 years of experience in HTML, CSS, JavaScript and jQuery for corporate websites.

EXPERIENCE
Web Developer, BlueLeaf Infotech - Oct 2024 - Present
- Worked on company websites using HTML, CSS and jQuery
- Responsible for making pages responsive using Bootstrap
- Fixed bugs reported by clients

SKILLS
HTML, CSS, JavaScript, jQuery, Bootstrap, PHP, MySQL, WordPress

EDUCATION
Diploma in Computer Engineering, {COLLEGE}, 2022
"""),
    ("R17", "Angular developer (related framework)", "mid", """{NAME}
Angular Developer . {CITY} . {EMAIL} . {PHONE}

SUMMARY
Frontend developer with 3 years of experience building enterprise dashboards in Angular and TypeScript.

EXPERIENCE
Software Engineer (Frontend), Corvus Enterprise Apps - Apr 2023 - Present
- Built 40+ Angular components and RxJS data streams for an ERP used by 8,000 employees
- Reduced bundle size by 45% with lazy loading and Webpack tuning
- Integrated REST APIs and wrote Jasmine/Karma unit tests (75% coverage)
- Mentored 2 interns on TypeScript best practices

SKILLS
Angular, TypeScript, RxJS, JavaScript, HTML, CSS, SCSS, REST APIs, Git, Agile, Responsive Design

EDUCATION
B.Tech Information Technology, {COLLEGE}, 2023
"""),
    ("R18", "Frontend - fresher with React projects", None, """{NAME}
{EMAIL} | {PHONE} | github.com/{HANDLE}

OBJECTIVE
Final-year student who enjoys building web apps with React.

INTERNSHIP
Web Development Intern, LaunchPad Labs - May 2026 - Jul 2026
- Built 6 React pages for a startup landing site and connected them to REST APIs
- Improved the Lighthouse performance score from 62 to 91

PROJECTS
StudyBuddy (React, JavaScript, Firebase)
- Group study planner with real-time chat, used by 400 students on campus
Weatherly (HTML, CSS, JavaScript)
- Responsive weather app built on a public REST API

SKILLS
JavaScript, React, HTML, CSS, Firebase, Git, Tailwind CSS, Responsive Design

EDUCATION
B.E. Computer Science and Engineering, {COLLEGE}, 2027 (expected) - CGPA 8.1

PERSONAL DETAILS
Date of Birth: 09-11-2004
Photo: attached
"""),
    ("R19", "Full-stack MERN developer", "top", """{NAME}
Full Stack Developer (MERN) - {CITY} - {EMAIL} - {PHONE}

SUMMARY
Full-stack developer with 2 years of experience on MongoDB, Express, React and Node.js.

EXPERIENCE
Full Stack Developer, Craftly Commerce - Sep 2024 - Present
- Developed a React storefront and Node.js/Express APIs for 120 small merchants
- Designed MongoDB schemas and cut checkout API latency by 30% with Redis caching
- Set up GitHub Actions CI and Docker-based deploys on AWS

PROJECTS
DevChat (React, Node.js, Socket.io)
- Real-time chat app handling 1,000+ messages a day in beta

SKILLS
JavaScript, React, Node.js, Express.js, MongoDB, Redis, HTML, CSS, Git, Docker, AWS, REST APIs

EDUCATION
B.Tech Computer Science, {COLLEGE}, 2024
"""),
    ("R20", "Unrelated: civil site engineer", None, """{NAME}
Site Engineer | {PHONE} | {EMAIL}

SUMMARY
Civil engineer with 2 years of site execution experience in residential projects.

EXPERIENCE
Site Engineer, Greenfield Constructions - Jul 2024 - Present
- Supervised construction of 3 residential towers (240 flats) on schedule
- Prepared bar bending schedules and quantity estimates in Excel
- Coordinated with 40+ workers and subcontractors daily

SKILLS
AutoCAD, STAAD Pro, Excel, Project Management, Quantity Surveying

EDUCATION
B.E. Civil Engineering, {COLLEGE}, 2024
"""),
]


def _identity(rng, tier):
    female = rng.random() < 0.5
    first = rng.choice(FEMALE if female else MALE)
    last = rng.choice(SURNAMES)
    tier = tier or rng.choice(["top", "mid", "local"])
    pool = {"top": COLLEGES_TOP, "mid": COLLEGES_MID, "local": COLLEGES_LOCAL}[tier]
    college = rng.choice(pool)
    if female is False:
        # avoid putting a man in a women's college: re-draw from non-women colleges
        choices = [c for c in pool if "Women" not in c] or COLLEGES_MID
        college = rng.choice(choices)
    handle = (first + "-" + last).lower()
    return {
        "NAME": "%s %s" % (first, last),
        "EMAIL": "%s.%s%d@mail.example" % (first.lower(), last.lower(), rng.randint(1, 99)),
        "PHONE": "+91 9%04d %05d" % (rng.randint(0, 9999), rng.randint(0, 99999)),
        "CITY": rng.choice(CITIES),
        "COLLEGE": college,
        "COLLEGE2": rng.choice(COLLEGES_MID),
        "HANDLE": handle,
        "PRONOUN": "She" if female else "He",
        "PRONOUN_LOWER": "she" if female else "he",
        "GENDER": "Female" if female else "Male",
        "FATHER": "%s %s" % (rng.choice(MALE), last),
        "gender": "female" if female else "male",
        "tier": tier,
    }


def fill(template, ident):
    out = template
    for k, v in ident.items():
        if k.isupper():
            out = out.replace("{" + k + "}", v)
    return out


def build_demo(seed=SEED):
    rng = random.Random(seed)
    resumes = []
    for rid, archetype, tier, tpl in TEMPLATES:
        ident = _identity(rng, tier)
        resumes.append({"id": rid, "name": ident["NAME"], "archetype": archetype, "text": fill(tpl, ident),
                        "gender": ident["gender"], "college_tier": ident["tier"]})
    labels = {jd: {rid: LABELS[rid][i] for rid in LABELS} for i, jd in enumerate(JD_ORDER)}
    return {"seed": seed, "jds": [dict(j) for j in JDS], "resumes": resumes, "labels": labels,
            "note": "Synthetic, fictional data generated by resumeradar/demo.py"}


def synthetic_batch(n=100, seed=7):
    """n varied resumes for latency tests: templates with fresh identities and dropped bullets."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        rid, _arch, tier, tpl = TEMPLATES[i % len(TEMPLATES)]
        ident = _identity(rng, None)
        lines = fill(tpl, ident).split("\n")
        kept = [ln for ln in lines if not (ln.startswith("- ") and rng.random() < 0.25)]
        out.append({"id": "S%03d" % (i + 1), "text": "\n".join(kept)})
    return out


_CACHE = {}


def get_demo():
    if "demo" not in _CACHE:
        _CACHE["demo"] = build_demo()
    return _CACHE["demo"]


def write_demo(path=None):
    path = path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "demo.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(build_demo(), f, indent=2, ensure_ascii=False)
    return path


if __name__ == "__main__":
    print("wrote", write_demo())
