import os
import random
import string
from datetime import datetime, timedelta

# Realistic fake data templates for decoy files
FAKE_PASSWORDS = """# Internal Passwords - CONFIDENTIAL
# Last Updated: {date}

[Database Servers]
prod-db-01: admin / Pr0d@2024!Secure
prod-db-02: dbadmin / DB$ecure#99
staging-db: devuser / St@g1ng2024

[Admin Panels]
main-admin: superadmin / @dm1nP@ss2024
hr-portal: hradmin / HR#Secure789
finance-panel: financeadmin / F1n@nce!2024

[API Keys]
stripe_live: sk_live_4xK9mN2pQ7rT1wYz
aws_access: AKIAIOSFODNN7EXAMPLE
aws_secret: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
sendgrid: SG.fake_key_here_do_not_use

[VPN Credentials]
vpn-server: vpnuser / V@PNaccess2024!
backup-vpn: vpnadmin / B@ckup#VPN99

[Email Accounts]
ceo@company.com: Execut1ve!Pass2024
cfo@company.com: F1nanc3#Chief99
"""

FAKE_SALARY = """{date} - Q4 Salary Data - STRICTLY CONFIDENTIAL

Employee ID | Name              | Department    | Salary (INR/Month) | Bonus
-----------|-------------------|---------------|-------------------|-------
EMP001     | Rajesh Kumar      | Engineering   | 85,000            | 15%
EMP002     | Priya Sharma      | Product       | 92,000            | 18%
EMP003     | Amit Verma        | Sales         | 62,000            | 22%
EMP004     | Neha Singh        | HR            | 58,000            | 10%
EMP005     | Vikram Patel      | Engineering   | 1,10,000          | 20%
EMP006     | Anjali Mehta      | Finance       | 78,000            | 12%
EMP007     | Suresh Reddy      | DevOps        | 95,000            | 15%
EMP008     | Kavya Nair        | Design        | 70,000            | 14%
EMP009     | Rahul Gupta       | Engineering   | 88,000            | 16%
EMP010     | Deepika Joshi     | Marketing     | 65,000            | 13%
EMP011     | Arun Krishnan     | CTO           | 2,50,000          | 25%
EMP012     | Meera Pillai      | CEO           | 3,20,000          | 30%

Total Monthly Payroll: 14,73,000 INR
Annual Cost (CTC): 2,18,45,640 INR

PREPARED BY: HR Department
AUTHORIZED BY: CFO
"""

FAKE_EXAM_PAPER = """UNIVERSITY EXAMINATION - {year}
Subject: Advanced Computer Networks (CS-501)
Date: {exam_date}    Time: 3 Hours    Max Marks: 100

=== SECTION A - COMPULSORY (20 Marks) ===

Q1. Answer all parts: (2 marks each)
(a) Define OSI model and explain each layer briefly.
(b) What is subnetting? Calculate subnet for 192.168.10.0/26
(c) Explain TCP three-way handshake.
(d) Difference between hub, switch, and router.
(e) What is CIDR notation? Give examples.

=== SECTION B - Attempt any 3 (60 Marks) ===

Q2. (20 marks)
(a) Explain OSPF routing protocol with diagram. Compare with RIP.
(b) Describe BGP and its role in internet routing.

Q3. (20 marks)
(a) Explain TCP congestion control mechanisms.
(b) Compare TCP vs UDP with real-world use cases.

Q4. (20 marks)
(a) Describe VLAN configuration on Cisco switches.
(b) Explain STP (Spanning Tree Protocol).

Q5. (20 marks)
(a) Explain IPv6 addressing with diagram.
(b) Describe transition mechanisms from IPv4 to IPv6.

=== SECTION C - Case Study (20 Marks) ===

Q6. A company has 500 employees across 3 floors. Design complete network topology...

*** ANSWER KEY ATTACHED - INTERNAL USE ONLY ***
Q1a: 7 layers - Physical, Data Link, Network, Transport, Session, Presentation, Application
Q1b: 192.168.10.0 - 64 hosts per subnet, .0, .64, .128, .192
Q1c: SYN -> SYN-ACK -> ACK sequence
"""

FAKE_SOURCE_CODE = """#!/usr/bin/env python3
# payment_gateway.py - PROPRIETARY SOURCE CODE
# Company: TechCorp Solutions Pvt Ltd
# Author: Backend Team
# CONFIDENTIAL - DO NOT DISTRIBUTE

import hashlib
import hmac
import requests
from cryptography.fernet import Fernet

# Production API Configuration
PAYMENT_GATEWAY_URL = "https://api.paymentgateway.com/v2"
MERCHANT_ID = "MID_PROD_9x7K2mN4pQ8r"
SECRET_KEY = b"production_secret_key_do_not_share_32chars"
WEBHOOK_SECRET = "whsec_prod_9xKmNpQrTwYz1234567890"

# Encryption key for stored card data
ENCRYPTION_KEY = Fernet.generate_key()
cipher_suite = Fernet(ENCRYPTION_KEY)

def process_payment(amount, card_number, cvv, expiry, customer_id):
    '''Process payment through gateway'''
    
    # Hash sensitive data
    card_hash = hashlib.sha256(card_number.encode()).hexdigest()
    
    # Create HMAC signature
    payload = f"{{amount}}:{{customer_id}}:{{card_hash}}"
    signature = hmac.new(SECRET_KEY, payload.encode(), hashlib.sha256).hexdigest()
    
    headers = {{
        'Authorization': f'Bearer {{SECRET_KEY.decode()}}',
        'X-Merchant-ID': MERCHANT_ID,
        'X-Signature': signature,
        'Content-Type': 'application/json'
    }}
    
    encrypted_card = cipher_suite.encrypt(card_number.encode()).decode()
    
    response = requests.post(f"{{PAYMENT_GATEWAY_URL}}/charge", 
        json={{
            'amount': amount,
            'card_data': encrypted_card,
            'customer': customer_id,
            'signature': signature
        }},
        headers=headers
    )
    
    return response.json()

# Database connection string (PRODUCTION)
DB_CONNECTION = "postgresql://produser:Pr0d@DB#2024@prod-db.internal:5432/payments_db"

# AWS Production Credentials  
AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
AWS_SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
S3_BUCKET = "company-prod-transactions"
"""

FAKE_CUSTOMER_DB = """{date} - Customer Database Export - CONFIDENTIAL
Export Type: Full Dump | Total Records: {count}

ID    | Name              | Email                        | Phone        | Balance   | Card (Last 4)
------|-------------------|------------------------------|--------------|-----------|---------------
1001  | Arjun Malhotra    | arjun.m@gmail.com           | 9876543210   | ₹15,420   | 4532
1002  | Sunita Rao        | sunita.rao@yahoo.com         | 8765432109   | ₹8,900    | 6011
1003  | Kiran Bhat        | kiran.b@hotmail.com          | 7654321098   | ₹23,750   | 3782
1004  | Pooja Iyer        | pooja.iyer@gmail.com         | 6543210987   | ₹5,200    | 5424
1005  | Mohit Aggarwal    | mohit.a@company.com          | 9988776655   | ₹42,100   | 4916
1006  | Shalini Devi      | shalini.d@email.com          | 8877665544   | ₹11,350   | 5610
1007  | Tarun Seth        | tarun.seth@startup.io        | 7766554433   | ₹67,890   | 4539
1008  | Nandini Kapoor    | nandini.k@work.com           | 6655443322   | ₹3,450    | 3714
1009  | Aditya Bose       | aditya.bose@tech.com         | 9543210876   | ₹29,600   | 5200
1010  | Rekha Pillai      | rekha.p@gmail.com            | 8432109765   | ₹18,750   | 4485

[... 10,245 more records truncated ...]

EXPORTED BY: System Administrator
TIMESTAMP: {date} 03:47:22 IST
"""


def _rand_str(n=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))


def generate_canary_file(filename: str, file_type: str, save_dir: str) -> dict:
    """
    Generate a realistic-looking canary file with decoy content.
    Returns dict with file info.
    """
    os.makedirs(save_dir, exist_ok=True)

    today = datetime.now().strftime('%d-%m-%Y')
    year = datetime.now().year
    exam_date = (datetime.now() + timedelta(days=random.randint(10, 30))).strftime('%d/%m/%Y')
    record_count = random.randint(8500, 15000)

    content_map = {
        'passwords.txt': FAKE_PASSWORDS.format(date=today),
        'salary_data.txt': FAKE_SALARY.format(date=today),
        'salary_data.csv': FAKE_SALARY.format(date=today),
        'exam_paper.txt': FAKE_EXAM_PAPER.format(year=year, exam_date=exam_date),
        'confidential_source_code.py': FAKE_SOURCE_CODE,
        'customer_database.txt': FAKE_CUSTOMER_DB.format(date=today, count=record_count),
        'customer_database.csv': FAKE_CUSTOMER_DB.format(date=today, count=record_count),
    }

    # Match best content template
    content = None
    fn_lower = filename.lower()
    if 'password' in fn_lower or 'pass' in fn_lower or 'cred' in fn_lower:
        content = FAKE_PASSWORDS.format(date=today)
    elif 'salary' in fn_lower or 'payroll' in fn_lower or 'pay' in fn_lower:
        content = FAKE_SALARY.format(date=today)
    elif 'exam' in fn_lower or 'paper' in fn_lower or 'question' in fn_lower:
        content = FAKE_EXAM_PAPER.format(year=year, exam_date=exam_date)
    elif 'source' in fn_lower or 'code' in fn_lower or '.py' in fn_lower:
        content = FAKE_SOURCE_CODE
    elif 'customer' in fn_lower or 'client' in fn_lower or 'database' in fn_lower:
        content = FAKE_CUSTOMER_DB.format(date=today, count=record_count)
    else:
        content = FAKE_PASSWORDS.format(date=today)

    # Ensure proper extension
    if '.' not in filename:
        filename = filename + f'.{file_type}'

    filepath = os.path.join(save_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    return {
        'filename': filename,
        'file_path': filepath,
        'decoy_content': content[:200],
        'file_type': file_type,
    }
