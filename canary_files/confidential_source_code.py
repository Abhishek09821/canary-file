#!/usr/bin/env python3
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
