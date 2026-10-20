"""Hand-written demo messages and the 'Spot the scam' quiz.

These are NOT part of the training corpus (they were written separately) so
the demo also shows behaviour on text the model has never seen.
Phone numbers / UPI IDs are made up.
"""

DEMO_SAMPLES = [
    {"id": "kyc", "label": "KYC block SMS",
     "text": "Dear SBI customer, your YONO account will be blocked today due to pending KYC. "
             "Update your PAN immediately: http://sbi-kyc-update.xyz/login.php"},
    {"id": "eb", "label": "EB disconnection",
     "text": "Dear Consumer, your electricity power will be disconnected tonight at 9.30 PM because your "
             "previous month bill was not updated. Please contact our electricity officer 9876543210 immediately."},
    {"id": "job", "label": "Fake internship",
     "text": "Congratulations Priya! You are selected for a work from home Data Analyst internship at Amazon. "
             "Stipend Rs.15,000/month. Pay refundable registration fee Rs.1,999 to hr.recruit@ybl to confirm your slot."},
    {"id": "upi", "label": "UPI collect trick",
     "text": "You have received a collect request of Rs.5,000 from refund.help@ybl. Enter your UPI PIN to receive the amount."},
    {"id": "tanglish", "label": "Tanglish scam",
     "text": "Unga Indian Bank account innaiku block aagum. Udane KYC update pannunga: https://indianbank-kyc.online/verify"},
    {"id": "otp", "label": "Bank OTP (safe)",
     "text": "482913 is your OTP for a transaction of Rs.1,250 at Amazon. Valid for 10 mins. Do not share it with anyone. -SBI"},
    {"id": "friend", "label": "Friend chat (safe)",
     "text": "Machi, naalaiku DBMS lab record kondu vaa. Sir check pannuvaru. Canteen la 1 PM ku meet pannalam"},
    {"id": "link", "label": "Phishing link",
     "text": "http://www.onlinesbi.sbi@185.22.14.7/retail/login.php"},
    {"id": "official", "label": "Official link (safe)",
     "text": "https://www.irctc.co.in/nget/train-search"},
]

BULK_DEMO = [
    "Dear customer your HDFC Bank KYC has expired, account will be suspended in 24 hrs. Update: hdfc-kyc.top/verify",
    "482913 is your OTP for login to Flipkart. Do not share it with anyone.",
    "Bro tomorrow lab ku record kondu vaa, sir check pannuvaru",
    "Aapka bijli connection aaj raat 9:30 baje kat jayega. Turant 9123456780 par call karein.",
    "Your Swiggy order is out for delivery. Delivery partner Ravi will reach in 15 mins.",
    "Congratulations! You won Rs.25 lakh in KBC lucky draw. Pay Rs.4,999 processing fee to claim: lucky.draw@ybl",
    "https://www.amazon.in/gp/your-account/order-history",
    "http://amaz0n-offers.shop/claim?gift=iphone",
    "Placement cell: Zoho campus drive on 28-10-2026. Register on the placement portal. No fee is collected.",
    "Part time job! Earn Rs.3,000 daily by liking YouTube videos. WhatsApp HR on +91 98765 43210",
    "FedEx: parcel in your name has illegal drugs. Call 8899776655 now to avoid digital arrest.",
    "Rs.450 debited from A/c XX1234 to VPA zomato@hdfcbank. Not you? Call 1800 123 4567 -HDFC Bank",
    "bit.ly/3Kx9qPz",
    "Happy birthday da! Party eppo?",
    "Install AnyDesk and share the code so our executive can process your refund.",
]

QUIZ = [
    {"text": "Dear user, your PAN card is not updated. Your SBI YONO account will be blocked today. Update now: sbi-yono-pan.xyz",
     "answer": "scam",
     "why": "Banks never ask for PAN/KYC updates through SMS links. 'Blocked today' is pressure, and sbi-yono-pan.xyz is not SBI's domain."},
    {"text": "394817 is your OTP to log in to your Flipkart account. Do not share this OTP with anyone.",
     "answer": "safe",
     "why": "A normal one-time password you requested. It warns you NOT to share it and has no link or phone number."},
    {"text": "Hello, I am from Amazon HR. You are shortlisted for a part-time job. Earn Rs.5,000 daily by rating products. Pay Rs.999 joining fee on WhatsApp +91 90000 12345",
     "answer": "scam",
     "why": "Real employers never charge a joining fee, and 'earn daily by rating products' is a known task scam."},
    {"text": "Your Amazon order #405-7724519 has been shipped and will arrive by Thursday. Track it in the Amazon app.",
     "answer": "safe",
     "why": "No link to an unknown site, no payment request, points you to the official app."},
    {"text": "Sir, I sent Rs.2,000 to your number by mistake. I have sent you a request on PhonePe, please approve it and enter PIN to return.",
     "answer": "scam",
     "why": "Approving a 'collect' request and entering your PIN SENDS money. You never need a PIN to receive money."},
    {"text": "Dear Consumer, your electricity connection will be disconnected tonight at 9:30 PM. Contact electricity officer 9812345678 immediately.",
     "answer": "scam",
     "why": "Electricity boards don't disconnect via SMS to a personal mobile number. Classic EB-bill scam."},
    {"text": "KSRCE Placement cell: Zoho campus drive on 28 Oct. Eligible final-year students register on the placement portal. No fee is collected.",
     "answer": "safe",
     "why": "Information only, points to the college portal and explicitly says there is no fee."},
    {"text": "FedEx: a parcel booked with your Aadhaar contains illegal items. Mumbai customs officer will call you. Stay on video call to avoid digital arrest.",
     "answer": "scam",
     "why": "'Digital arrest' is not a thing. Police and customs never interrogate or arrest over video calls."},
    {"text": "Rs.250.00 debited from A/c XX4521 on 18-10-26 to VPA swiggy@icici. Not you? Call 1800 123 4567 -SBI",
     "answer": "safe",
     "why": "A normal debit alert: no link, a toll-free bank helpline, and nothing is asked of you."},
    {"text": "Hi, is this your photo in this video? lol https://bit.ly/3vXp9Qk",
     "answer": "scam",
     "why": "A curiosity bait with a shortened link that hides the real site - a common way to spread phishing and malware."},
]
