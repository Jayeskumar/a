"""Deterministic synthetic training corpus (messages + URLs).

Everything here is *synthetic*: templates written by us, filled with random
slots from a fixed seed.  Brand names are used only so the model can learn
impersonation patterns; benign URLs use the brands' real official domains,
phishing URLs are invented look-alikes.  Phone numbers and UPI IDs are random.

Run ``python -m phishguard.corpus`` to (re)write data/messages.json and
data/urls.json.
"""
import json
import os
import random
import string

from . import config

# ------------------------------------------------------------------ slot pools
BANKS = ["SBI", "HDFC Bank", "ICICI Bank", "Axis Bank", "Kotak", "Canara Bank", "PNB",
         "Bank of Baroda", "Indian Bank", "IOB", "Union Bank"]
BANK_KEYS = {"SBI": "sbi", "HDFC Bank": "hdfc", "ICICI Bank": "icici", "Axis Bank": "axis",
             "Kotak": "kotak", "Canara Bank": "canara"}
WALLETS = ["Paytm", "PhonePe", "Google Pay", "BHIM", "Amazon Pay"]
SHOPS = ["Amazon", "Flipkart", "Myntra", "Meesho", "Swiggy", "Zomato", "Ajio", "Nykaa"]
COURIERS = ["India Post", "Blue Dart", "DTDC", "Delhivery", "Ekart", "FedEx"]
EBS = ["TNEB", "BESCOM", "MSEDCL", "Electricity Board", "EB office", "TANGEDCO", "KSEB"]
COMPANIES = ["Amazon", "TCS", "Infosys", "Wipro", "Zoho", "HCL", "Accenture", "Deloitte",
             "Cognizant", "Tech Mahindra", "Flipkart", "Freshworks"]
ROLES = ["Data Analyst", "Python Developer", "HR", "Content Writer", "Web Developer",
         "Digital Marketing", "Data Entry", "Customer Support"]
NAMES = ["Priya", "Arun", "Karthik", "Divya", "Rahul", "Sneha", "Vignesh", "Anjali", "Mohammed",
         "Lakshmi", "Suresh", "Kavya", "Harish", "Pooja", "Naveen", "Meena", "Ravi", "Deepika",
         "Gokul", "Fathima", "Sanjay", "Nithya", "Ajay", "Swathi"]
PLACES = ["Erode", "Salem", "Coimbatore", "Chennai", "Tiruchengode", "Namakkal", "Madurai",
          "Bengaluru", "Trichy", "the hostel", "the bus stand", "home"]
FOODS = ["biryani", "parotta", "pizza", "dosa", "shawarma", "fried rice", "momos"]
EVENTS = ["paper presentation", "coding contest", "quiz", "hackathon", "project expo", "debate"]
SUBJECTS = ["DBMS", "Maths", "OS", "Networks", "AI", "Java", "Physics", "Compiler Design"]
TELCOS = ["Jio", "Airtel", "Vi", "BSNL"]
PSPS = ["ybl", "okaxis", "oksbi", "okhdfcbank", "paytm", "ibl", "axl", "upi", "okicici", "apl"]
SCAM_UPI_LOCAL = ["kyc.update", "refund.help", "sbi.care", "reward.claim", "helpdesk.bank",
                  "cashback.offer", "lucky.draw", "prize.dept", "hr.recruit", "eb.billpay",
                  "customer.support", "govt.scheme", "tax.refund", "jobs.hr", "loan.approve"]

SUSP_TLDS = ["xyz", "top", "club", "online", "site", "live", "icu", "buzz", "click", "link",
             "shop", "vip", "cyou", "sbs", "in", "com", "info", "net"]
PHISH_KW = ["kyc", "update", "verify", "secure", "login", "reward", "refund", "bonus",
            "support", "care", "help", "online", "service", "portal", "alert", "auth", "pay"]
SHORTENER_HOSTS = ["bit.ly", "tinyurl.com", "cutt.ly", "is.gd", "rb.gy", "t.ly", "shorturl.at", "tiny.cc"]
FREE_HOSTS = ["weebly.com", "000webhostapp.com", "firebaseapp.com", "web.app", "netlify.app",
              "blogspot.com", "ngrok-free.app", "vercel.app", "glitch.me", "pages.dev"]
GOV_FAKE = ["pmkisan", "govt-scheme", "yojana", "sarkari", "tneb-bill", "eb-billpay", "indiapost-track",
            "incometax-refund", "aadhaar-update", "epfo-claim", "uidai-verify"]
WORDS = ["green", "leaf", "sun", "rise", "river", "stone", "bright", "metro", "star", "lotus",
         "nova", "peak", "smart", "fresh", "urban", "royal", "silver", "tiger", "spark", "blue",
         "kovai", "chennai", "erode", "tech", "labs", "foods", "mart", "hub", "works", "studio",
         "media", "learn", "garden", "craft", "travels", "clinic", "books", "tutor", "agro"]
SLUG = ["best-budget-phones", "exam-timetable", "how-to-learn-python", "monsoon-tips",
        "placement-results", "college-fest-2026", "new-arrivals", "contact-us", "about",
        "admission-2026", "fee-structure", "notice-board", "events", "gallery", "menu",
        "blog/weekly-update", "products/organic-honey", "courses/data-science", "careers"]

BENIGN_BRAND_URLS = [
    "https://www.amazon.in/dp/B0{A8}", "https://www.amazon.in/gp/your-account/order-history",
    "https://www.flipkart.com/{slug}/p/itm{h12}", "https://www.flipkart.com/account/orders",
    "https://www.irctc.co.in/nget/train-search", "https://www.irctc.co.in/nget/profile/user-registration",
    "https://www.onlinesbi.sbi/", "https://retail.onlinesbi.sbi/retail/login.htm",
    "https://sbi.co.in/web/personal-banking/accounts", "https://netbanking.hdfcbank.com/netbanking/",
    "https://www.hdfcbank.com/personal/pay/cards/credit-cards", "https://www.icicibank.com/personal-banking/cards",
    "https://www.axisbank.com/retail/loans", "https://www.incometax.gov.in/iec/foportal/",
    "https://uidai.gov.in/en/my-aadhaar/update-aadhaar.html", "https://www.indiapost.gov.in/",
    "https://www.youtube.com/watch?v={yt}", "https://youtu.be/{yt}", "https://amzn.to/{s7}",
    "https://github.com/{user}/{repo}", "https://en.wikipedia.org/wiki/{wiki}",
    "https://docs.python.org/3/library/{mod}.html", "https://www.google.com/search?q={q}",
    "https://maps.google.com/?q={place}", "https://www.linkedin.com/in/{user}-{n4}",
    "https://drive.google.com/file/d/{drive}/view", "https://forms.gle/{s10}",
    "https://paytm.com/recharge", "https://www.phonepe.com/business-solutions/",
    "https://www.swiggy.com/restaurants/{slug}-{n6}", "https://www.zomato.com/coimbatore/{slug}",
    "https://www.myntra.com/{slug}/{n6}/buy", "https://www.airtel.in/prepaid-recharge",
    "https://www.jio.com/selfcare/plans/mobility/", "https://www.epfindia.gov.in/site_en/index.php",
    "https://nptel.ac.in/courses/{n6}", "https://www.ksrce.ac.in/{slug}", "https://swayam.gov.in/explorer",
    "https://www.netflix.com/browse", "https://support.google.com/accounts/answer/{n6}",
    "https://www.npci.org.in/what-we-do/upi/product-overview", "https://cybercrime.gov.in/",
]

HAM_TEMPLATES = [
    # --- bank / payment alerts
    "{otp} is your OTP for a transaction of Rs.{amt} at {shop}. Valid for 10 mins. Do not share it with anyone. -{bank}",
    "Dear Customer, Rs.{amt} debited from A/c XX{n4} on {date} to VPA {upi_ok}. Not you? Call {tollfree} -{bank}",
    "Rs.{amt} credited to your A/c XX{n4} on {date} by UPI Ref {n12}. Avl Bal Rs.{amt2} -{bank}",
    "Your {bank} credit card statement is ready. Total due Rs.{amt}, due by {date}. Pay via net banking or the official app.",
    "OTP for {shop} login is {otp}. Never share your OTP or UPI PIN with anyone. {bank} never asks for it.",
    "{otp} is the OTP to verify your mobile number on {shop}. Do not share this code with anyone.",
    "You have paid Rs.{amt} to {name} via {wallet}. UPI Ref No {n12}.",
    "Received Rs.{amt} from {name} on {wallet}. Check your balance in the app.",
    "Your {wallet} cashback of Rs.{small} has been credited to your wallet for your recent recharge.",
    "Your refund of Rs.{amt} for order #{order} has been initiated and will reflect in 5-7 working days.",
    "{bank}: Your FD of Rs.{amt_big} has been renewed for 1 year at the existing rate. Visit the branch for details.",
    "Your {bank} debit card ending {n4} was used for Rs.{amt} at {shop} on {date}. If not you, block it from the official app.",
    "{bank}: Your EMI of Rs.{amt} for loan a/c XX{n4} is due on {date}. Please keep sufficient balance.",
    # --- shopping / delivery
    "Your {shop} order #{order} has been shipped and will arrive by {date}. Track: {benign}",
    "Your {courier} parcel {awb} will be delivered today between 2 PM and 6 PM.",
    "Delivered: your {shop} package was handed to {name} at {time}. Rate your experience in the app.",
    "{shop}: Your order of {food} is out for delivery. Delivery partner {name} will reach in 15 mins.",
    "Your {shop} return pickup is scheduled for {date}. Keep the item ready with tags.",
    # --- utilities / telecom / travel
    "Electricity bill for service no {n9} is Rs.{amt}. Due date {date}. Pay through the official app or portal. Ignore if already paid.",
    "Reminder: your {eb} bill due date is {date}. Pay online through the official website to avoid late fee.",
    "Power shutdown on {date} from 9 AM to 2 PM in {place} for maintenance work. - {eb}",
    "Your {telco} recharge of Rs.{small} is successful. Validity {days} days. Data 1.5GB/day.",
    "IRCTC: PNR {n10} confirmed. Train {n5} on {date}, coach B{d1} berth {n2}. Happy journey.",
    "Your {telco} bill of Rs.{amt} is generated. Pay by {date} using the official app.",
    "Link your PAN with Aadhaar before the deadline using the official income tax portal incometax.gov.in.",
    # --- college / jobs (genuine)
    "KSRCE: Internal assessment II starts on {date}. Check the timetable on the college portal.",
    "Placement cell: {company} campus drive on {date}. Eligible students register on the placement portal. No fee is collected.",
    "Hi {name}, your interview with {company} for the {role} intern role is on {date} at {time}. The link is in your official email.",
    "Congrats {name}! You won first prize in the {event} at the symposium. Collect your certificate tomorrow.",
    "Urgent: {subject} lab record submission is tomorrow, please complete it tonight.",
    "Reminder: {subject} assignment due on {date}. Upload the PDF in the LMS.",
    "Dear students, the library will remain closed on {date} due to stock verification.",
    "{company} careers: Thank you for applying for {role}. We will contact you if shortlisted.",
    "Your NPTEL exam hall ticket is available. Download it from the official NPTEL portal.",
    "Subject: Team meeting moved to {time}\nHi all, the weekly sync is moved to {time} tomorrow. Agenda attached. Thanks, {name}",
    "Subject: Your {shop} invoice\nThank you for shopping with us. Your invoice for order #{order} is attached. Details: {benign}",
    "Subject: Project review\nHi {name}, please share the final slides for the {event} by {date}. Regards, Project Coordinator",
    "Subject: Hostel fee receipt\nDear parent, the hostel fee receipt for this semester is attached. Contact the office for queries.",
    # --- friends & family (English / Tanglish / Hinglish)
    "Machi class ku varriya? {time} ku {subject} lab irukku",
    "Da, assignment submit panniya? Last date {date} nu sir sonnaru",
    "Amma, naan {place} reach aayitten. Bus konjam late aachu",
    "Bro {food} order pannalama? {shop} la offer irukku",
    "Bhai kal ka lab record leke aana, sir check karenge",
    "Kal milte hai canteen mein, {time} baje",
    "Mummy ne bola ghar jaldi aana, guests aa rahe hai",
    "Happy birthday {name}! Have a great year ahead",
    "Can you send me the {subject} notes? I missed yesterday's class",
    "Reached {place} safely. Will call you after dinner",
    "Hey, the {event} results are out! Check the notice board",
    "Ok da, naan {time} ku bus stand la wait panren",
    "Call me when you are free, need to discuss the project",
    "Paisa bhej diya {wallet} pe, check kar le",
    "Dei, {food} semma taste! Next time namma ellarum polam",
    "Sir, I will be on leave tomorrow due to fever. Kindly grant permission.",
    "Here is the {event} registration form, fill it before {date}: {benign}",
    "Watch this, the {subject} explanation is really good {benign}",
    "Sent you Rs.{small} for the {food}, split equally",
    "Appa, fees kattiyacha? Office la ketanga",
    "Bhaiya {otp} wala code mat bhejna kisi ko, mummy ka phone hai",
    "Please share your {subject} lab output screenshot when free",
    "Hello {name}, how are you? Long time no see",
    "Good morning da, coming to college today?",
    "Hi sir, I have sent the {subject} file to your mail",
    "Ok, see you at {time}",
    "Hello bro, free ah? Call me once",
    "Hi, reached {place}?",
    "Thanks da, got it",
    "Hello madam, I will be 10 minutes late today",
]

SCAM_TEMPLATES = [
    # --- KYC / account block
    "Dear Customer, your {bank} KYC has expired. Your account will be blocked within 24 hours. Update now: {phish}",
    "{bank}: Your account is suspended due to incomplete PAN update. Click {phish} to reactivate.",
    "Dear user your {bank} YONO account will be blocked today. Please update your PAN card immediately {phish}",
    "Your {bank} net banking is locked due to KYC pending. Verify Aadhaar at {phish} to avoid suspension.",
    "ALERT: {bank} A/c XX{n4} will be deactivated tonight. Complete e-KYC here {phish}",
    "Dear Customer, your SIM will be blocked in 2 hours due to KYC verification pending. Call {phone} immediately.",
    # --- electricity
    "Dear Consumer, your electricity power will be disconnected tonight at {time} because your previous month bill was not updated. Please contact our electricity officer {phone} immediately.",
    "{eb}: Your power connection will be disconnected today at {time}. Pay pending bill Rs.{small} now: {phish}",
    "Dear customer your electricity connection will be disconnected tonight. Update your bill details by calling {phone}",
    # --- lottery / prize / refund
    "Congratulations! You have won Rs.{amt_big} in the {shop} lucky draw. To claim, pay processing fee of Rs.{fee} to {upi_scam}",
    "You are the lucky winner of KBC lottery worth Rs.{lakhs} lakh. Contact our manager on WhatsApp {phone} to claim.",
    "Your {wallet} cashback of Rs.{amt} is pending. Click {phish} to claim before midnight.",
    "Income Tax Dept: you are eligible for a tax refund of Rs.{amt}. Verify your account at {phish}",
    "Dear customer, your credit card reward points ({n4}) expire today. Redeem now: {phish}",
    "Congrats! Your number won an iPhone 15 in the {telco} anniversary contest. Pay delivery charges of Rs.{fee} at {phish}",
    # --- UPI collect
    "You have received a payment request of Rs.{amt} from {upi_scam}. Enter your UPI PIN to receive the money.",
    "Hi, I sent Rs.{amt} to you by mistake. Please approve the request I sent on {wallet} to return it.",
    "Your {shop} refund of Rs.{amt} is ready. Scan this QR code to receive the refund in your account.",
    "OLX buyer here, I will pay advance Rs.{amt}. Accept the collect request and enter PIN to get money.",
    # --- OTP / remote access
    "This is {company} customer care. To process your refund please share the OTP sent to your phone.",
    "Sir, I am calling from {bank} head office. Your card is being upgraded, kindly tell the OTP you just received.",
    "Install AnyDesk and share the code so our executive can help you complete the refund.",
    "To unblock your {wallet} wallet, download QuickSupport and share the 9-digit code with our agent.",
    "Dear customer, your debit card will be blocked. Share card number, CVV and expiry date to reactivate.",
    # --- parcel / authority
    "{courier}: Your parcel is on hold due to incomplete address. Update within 12 hours: {phish}",
    "India Post: your package could not be delivered because the address is incomplete. Update details at {phish}",
    "FedEx: A parcel in your name contains illegal drugs. Customs officer will call you. Call {phone} to avoid digital arrest.",
    "This is CBI cyber cell. An arrest warrant is issued against your Aadhaar for money laundering. Call {phone} now.",
    "Your parcel from {shop} is held at customs. Pay customs duty Rs.{fee} at {phish} to release it.",
    # --- jobs / internships / easy money
    "Hello {name}, you are selected for a work from home internship at {company}. Stipend Rs.{amt}/month. Pay refundable registration fee Rs.{fee} to {upi_scam} to confirm your slot.",
    "Part time job offer! Earn Rs.{small} daily by liking YouTube videos. Contact HR on WhatsApp {phone}",
    "Subject: Offer letter - {company}\nCongratulations {name}, you are selected for the role of {role} intern. Kindly pay Rs.{fee} towards laptop and training charges to {upi_scam} to receive your offer letter.",
    "Earn money from home! Simple tasks, 10 min per day, Rs.{small} guaranteed income. Message us on Telegram",
    "Dear student, your scholarship of Rs.{amt} is approved. Pay a processing fee of Rs.{fee} to {upi_scam} to receive it.",
    "{company} HR: We saw your resume on Naukri. Data entry job, earn up to Rs.{amt} per week. Joining fee Rs.{fee} only. Reply YES",
    # --- investment / loans / malware
    "Invest Rs.{amt} and get guaranteed returns of 30% weekly. Join our Telegram group: {short}",
    "Double your money in 7 days with crypto trading. Limited slots, join VIP group {short}",
    "Get pre-approved instant loan of Rs.{amt_big} without documents. Apply now: {short}",
    "Download the {bank} rewards app to redeem your reward points worth Rs.{amt}: {apk}",
    "Your {wallet} account needs an update. Install the new app from this link {apk}",
    # --- subtle
    "Hi, is this you in this video? {short}",
    "{bank} alert: Rs.{amt} debited. If not done by you, click {phish} to cancel the transaction.",
    "Your Netflix subscription payment failed. Update your card details at {phish} to avoid suspension.",
    "Subject: Account verification required\nDear user, we detected unusual sign-in activity on your {bank} net banking. Verify your identity within 24 hours at {phish} or your account will be locked.",
    "Dear {name}, your {shop} account has been selected for a free gift. Claim it here {phish}",
    "Your Aadhaar is linked to a suspicious SIM. TRAI will disconnect all your numbers in 2 hours. Press 9 or call {phone}",
    # --- Hinglish / Tanglish scams
    "Aapka {bank} account aaj band ho jayega. Turant KYC update karein: {phish}",
    "Unga {bank} account block aagum. KYC update pannunga link: {phish}",
    "Bijli vibhag: aapka bijli connection aaj raat {time} baje kat jayega. Turant {phone} par call karein.",
    "Congratulations! Aapne KBC lottery mein Rs.{lakhs} lakh jeete hai. Claim karne ke liye {phone} par WhatsApp karein.",
    "Machi, intha link la register pannu, daily Rs.{small} earn pannalam: {short}",
    "Sir aapke number par Rs.{amt} ka refund aaya hai, receive karne ke liye UPI PIN daalein",
    "Aapka parcel customs mein ruka hai, Rs.{fee} customs duty bhejiye {upi_scam} par",
    "Unga EB connection innaiku night cut aagum. Udane {phone} ku call pannunga",
    "Bhai mera phone kharab hai, ek OTP aaya hoga tumhare number pe, please bata do",
    "Ungalukku Rs.{lakhs} lakh lottery vizhunthurukku! Processing fee Rs.{fee} anuppunga {upi_scam}",
]

PREFIXES_SCAM = ["", "", "", "Dear Customer, ", "URGENT: ", "Alert! ", "Dear user, "]
SUFFIXES_SCAM = ["", "", "", " Thank you.", " -Team Support", "!!", " Regards."]
# Ham gets similar sign-offs so the model cannot learn "has a sign-off" = scam.
SUFFIXES_HAM = ["", "", "", "", " Thank you.", " Regards.", " Thanks!", " -Team"]


# ----------------------------------------------------------------- helpers
def _rand_str(rng, n, alphabet=string.ascii_letters + string.digits):
    return "".join(rng.choice(alphabet) for _ in range(n))


def _digits(rng, n):
    return "".join(rng.choice(string.digits) for _ in range(n))


def _mobile(rng):
    num = rng.choice("6789") + _digits(rng, 9)
    style = rng.random()
    if style < 0.3:
        return "+91 " + num[:5] + " " + num[5:]
    if style < 0.5:
        return "+91" + num
    return num


def _amount(rng, lo, hi):
    v = rng.randint(lo, hi)
    if v >= 1000 and rng.random() < 0.6:
        return "{:,}".format(v)
    return str(v)


def _lookalike(rng, brand):
    tricks = [
        lambda b: b.replace("o", "0", 1) if "o" in b else b + "1",
        lambda b: b.replace("m", "rn", 1) if "m" in b else b + b[-1],
        lambda b: b[:-1] + b[-1] * 2,
        lambda b: b.replace("i", "1", 1) if "i" in b else b.replace("a", "4", 1),
        lambda b: b.replace("l", "1", 1) if "l" in b else b + "s",
    ]
    return rng.choice(tricks)(brand)


PHISH_BRANDS = ["sbi", "hdfc", "icici", "axis", "paytm", "phonepe", "amazon", "flipkart", "irctc",
                "airtel", "jio", "netflix", "indiapost", "kotak", "yono", "meesho", "myntra", "aadhaar"]


def phishing_url(rng, brand=None):
    brand = brand or rng.choice(PHISH_BRANDS)
    kw, kw2 = rng.sample(PHISH_KW, 2)
    tld = rng.choice(SUSP_TLDS)
    ip = ".".join(str(rng.randint(11, 223)) for _ in range(4))
    scheme = rng.choice(["http://", "https://", "https://", ""])
    page = rng.choice(["login.php", "verify.html", "index.php", "kyc", "update", "secure/login",
                       "account/verify", "", "auth", "claim", "reward.html", "pay"])
    kind = rng.randint(0, 11)
    if kind == 0:
        return "{}{}-{}-{}.{}/{}".format(scheme, brand, kw, kw2, tld, page)
    if kind == 1:
        return "{}{}.{}-{}.{}/{}".format(scheme, brand, kw, rng.choice(WORDS), tld, page)
    if kind == 2:
        return "http://{}/{}/{}".format(ip, brand, page or "login.php")
    if kind == 3:
        off = {"sbi": "www.onlinesbi.sbi", "hdfc": "netbanking.hdfcbank.com", "amazon": "www.amazon.in"}
        return "http://{}@{}/{}".format(off.get(brand, "www.{}.com".format(brand)), ip, page or "login")
    if kind == 4:
        return "{}{}.{}/{}".format(scheme or "https://", _lookalike(rng, brand), rng.choice(["com", "in", "net", tld]), page or kw)
    if kind == 5:
        return "https://xn--{}-{}.{}/{}/{}".format(brand[:3] + _rand_str(rng, 3, string.ascii_lowercase),
                                                 _rand_str(rng, 4, string.ascii_lowercase + string.digits), tld, brand, page or "login")
    if kind == 6:
        return "https://{}/{}".format(rng.choice(SHORTENER_HOSTS), _rand_str(rng, rng.randint(5, 8)))
    if kind == 7:
        return "http://{}{}.{}/download/{}_{}.apk".format(rng.choice(WORDS), _digits(rng, 2), tld,
                                                         brand.upper(), rng.choice(["Rewards", "Update", "KYC", "Support"]))
    if kind == 8:
        return "{}{}-{}.{}/{}".format(scheme, rng.choice(GOV_FAKE), kw, tld, page)
    if kind == 9:
        return "https://{}-{}.{}/{}".format(brand, kw, rng.choice(FREE_HOSTS), page)
    if kind == 10:
        return "https://{}.{}/{}?id={}&session={}".format(_rand_str(rng, rng.randint(10, 16), string.ascii_lowercase + string.digits),
                                                          tld, kw, _rand_str(rng, 16), _rand_str(rng, 10))
    return "{}{}{}{}.{}/{}/{}".format(scheme or "https://", rng.choice(["secure", "my", "e", "online", "get"]), kw,
                                      rng.choice(["now", "pay", "desk", "point", "24x7"]), rng.choice(["com", "in", tld]), kw2, page)


def benign_url(rng):
    r = rng.random()
    if r < 0.6:
        t = rng.choice(BENIGN_BRAND_URLS)
    elif r < 0.68:
        t = "https://bit.ly/{s7}"  # genuine shortened links exist too (college forms etc.)
    elif r < 0.84:
        t = rng.choice(["https://www.{w1}{w2}.in/{slug}", "https://{w1}{w2}.com/{slug}", "http://www.{w1}{w2}.com/",
                        "https://{w1}-{w2}.com/{slug}", "https://shop.{w1}{w2}.in/{slug}",
                        "https://{w1}{w2}.org/{slug}", "https://www.{w1}{w2}.co.in/{slug}"])
    else:
        t = rng.choice(["https://{w1}{w2}.blogspot.com/2026/{n2}/{slug}.html", "https://www.thehindu.com/news/national/{slug}/article{n8}.ece",
                        "https://timesofindia.indiatimes.com/city/{city}/{slug}/articleshow/{n8}.cms",
                        "https://stackoverflow.com/questions/{n8}/{slug}", "https://medium.com/@{user}/{slug}-{h12}",
                        "https://www.geeksforgeeks.org/{slug}/", "https://www.w3schools.com/python/python_{mod}.asp",
                        "https://www.{w1}{w2}.com/login", "https://portal.{w1}{w2}.ac.in/student/login",
                        "https://erp.{w1}{w2}.edu.in/fees/pay"])
    slots = {
        "A8": _rand_str(rng, 8, string.ascii_uppercase + string.digits),
        "h12": _rand_str(rng, 12, "0123456789abcdef"),
        "slug": rng.choice(SLUG), "yt": _rand_str(rng, 11), "s7": _rand_str(rng, 7), "s10": _rand_str(rng, 10),
        "user": rng.choice(NAMES).lower() + rng.choice(["", "dev", "k", "_r", "2026"]),
        "repo": rng.choice(["hackathon-app", "dsa-notes", "portfolio", "ml-projects", "attendance-bot"]),
        "wiki": rng.choice(["Phishing", "Unified_Payments_Interface", "Erode", "Machine_learning", "Naive_Bayes_classifier"]),
        "mod": rng.choice(["json", "re", "random", "http", "statistics", "lists", "functions"]),
        "q": rng.choice(["upi+fraud+helpline", "ksrce+timetable", "weather+erode", "python+tutorial"]),
        "place": rng.choice(PLACES).replace(" ", "+"), "n4": _digits(rng, 4), "n6": _digits(rng, 6), "n8": _digits(rng, 8),
        "n2": "{:02d}".format(rng.randint(1, 12)), "drive": _rand_str(rng, 28),
        "w1": rng.choice(WORDS), "w2": rng.choice(WORDS), "city": rng.choice(["chennai", "coimbatore", "madurai", "bengaluru"]),
    }
    return t.format(**slots)


def _date(rng):
    return "{:02d}-{:02d}-2026".format(rng.randint(1, 28), rng.randint(1, 12))


def _time(rng):
    h = rng.randint(1, 12)
    return "{}:{} {}".format(h, rng.choice(["00", "30", "15", "45"]), rng.choice(["AM", "PM"]))


def _slots(rng):
    bank = rng.choice(BANKS)
    return {
        "bank": bank, "wallet": rng.choice(WALLETS), "shop": rng.choice(SHOPS),
        "courier": rng.choice(COURIERS), "eb": rng.choice(EBS), "company": rng.choice(COMPANIES),
        "role": rng.choice(ROLES), "name": rng.choice(NAMES), "place": rng.choice(PLACES),
        "food": rng.choice(FOODS), "event": rng.choice(EVENTS), "subject": rng.choice(SUBJECTS),
        "telco": rng.choice(TELCOS),
        "amt": _amount(rng, 99, 49999), "amt2": _amount(rng, 1000, 250000), "small": _amount(rng, 49, 2999),
        "amt_big": _amount(rng, 50000, 2500000), "fee": _amount(rng, 99, 4999), "lakhs": str(rng.choice([5, 10, 25, 50])),
        "otp": _digits(rng, 6), "n2": str(rng.randint(1, 72)), "n4": _digits(rng, 4), "n5": _digits(rng, 5),
        "n9": _digits(rng, 9), "n10": _digits(rng, 10), "n12": _digits(rng, 12), "d1": str(rng.randint(1, 6)),
        "order": "{}-{}".format(_digits(rng, 3), _digits(rng, 7)), "awb": "EZ" + _digits(rng, 9) + "IN",
        "date": _date(rng), "time": _time(rng), "days": str(rng.choice([28, 56, 84])),
        "phone": _mobile(rng), "tollfree": "1800" + _digits(rng, 3) + _digits(rng, 4),
        "upi_ok": "{}{}@{}".format(rng.choice(NAMES).lower(), _digits(rng, 2), rng.choice(PSPS)),
        "upi_scam": "{}{}@{}".format(rng.choice(SCAM_UPI_LOCAL), rng.choice(["", _digits(rng, 2)]), rng.choice(PSPS)),
        "phish": phishing_url(rng, BANK_KEYS.get(bank)), "short": "https://{}/{}".format(rng.choice(SHORTENER_HOSTS), _rand_str(rng, 6)),
        "apk": phishing_url(rng) if rng.random() < 0.3 else "http://{}{}.{}/app/{}_{}.apk".format(
            rng.choice(WORDS), _digits(rng, 2), rng.choice(SUSP_TLDS), BANK_KEYS.get(bank, "bank").upper(), rng.choice(["Rewards", "Update"])),
        "benign": benign_url(rng),
    }


def _style_scam(rng, text):
    text = rng.choice(PREFIXES_SCAM) + text + rng.choice(SUFFIXES_SCAM)
    if rng.random() < 0.08:
        text = text.upper()
    return text


def _style_ham(rng, text):
    text = text + rng.choice(SUFFIXES_HAM)
    if rng.random() < 0.15:
        text = text.lower()
    return text


def generate_messages(n_per_class=380, seed=None):
    rng = random.Random(config.SEED if seed is None else seed)
    out, seen = [], set()
    for label, templates, styler in ((1, SCAM_TEMPLATES, _style_scam), (0, HAM_TEMPLATES, _style_ham)):
        count, guard = 0, 0
        while count < n_per_class and guard < n_per_class * 20:
            guard += 1
            tid = count % len(templates) if count < len(templates) else rng.randrange(len(templates))
            text = styler(rng, templates[tid].format(**_slots(rng)))
            if text in seen:
                continue
            seen.add(text)
            out.append({"text": text, "label": label, "template": "{}{}".format("s" if label else "h", tid)})
            count += 1
    return out


def generate_urls(n_per_class=220, seed=None):
    rng = random.Random((config.SEED if seed is None else seed) + 7)
    out, seen = [], set()
    for label, gen in ((1, phishing_url), (0, benign_url)):
        count, guard = 0, 0
        while count < n_per_class and guard < n_per_class * 50:
            guard += 1
            u = gen(rng)
            if u in seen:
                continue
            seen.add(u)
            out.append({"url": u, "label": label})
            count += 1
    return out


def split(items, test_fraction=None, seed=None, key="label"):
    """Stratified, seeded train/test split. Returns (train, test)."""
    test_fraction = config.TEST_FRACTION if test_fraction is None else test_fraction
    rng = random.Random((config.SEED if seed is None else seed) + 1)
    train, test = [], []
    for lab in sorted({it[key] for it in items}):
        group = [it for it in items if it[key] == lab]
        rng.shuffle(group)
        k = int(round(len(group) * test_fraction))
        test.extend(group[:k])
        train.extend(group[k:])
    return train, test


def template_split(items, fraction=None, seed=None):
    """Hold out whole templates so test messages use phrasing never seen in training."""
    fraction = config.HELDOUT_TEMPLATE_FRACTION if fraction is None else fraction
    rng = random.Random((config.SEED if seed is None else seed) + 2)
    held = set()
    for lab in (0, 1):
        tids = sorted({it["template"] for it in items if it["label"] == lab})
        rng.shuffle(tids)
        held.update(tids[: max(1, int(round(len(tids) * fraction)))])
    train = [it for it in items if it["template"] not in held]
    test = [it for it in items if it["template"] in held]
    return train, test


DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def write_data(data_dir=DATA_DIR):
    os.makedirs(data_dir, exist_ok=True)
    msgs, urls = generate_messages(), generate_urls()
    with open(os.path.join(data_dir, "messages.json"), "w", encoding="utf-8") as f:
        json.dump(msgs, f, ensure_ascii=False, indent=1)
    with open(os.path.join(data_dir, "urls.json"), "w", encoding="utf-8") as f:
        json.dump(urls, f, ensure_ascii=False, indent=1)
    return msgs, urls


if __name__ == "__main__":
    m, u = write_data()
    print("wrote {} messages and {} urls to {}".format(len(m), len(u), DATA_DIR))
