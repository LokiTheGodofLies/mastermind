from datetime import datetime
from modules.database.user_db import (
    get_user_role_db,
    get_quota_record_db,
    update_quota_counts_db,
    increment_search_used_db,
    increment_request_used_db,
    add_quota_limits_db
)

def check_and_reset_quota(user_id):
    """Checks if a new calendar day has started and resets daily usage counts to 0."""
    today_str = datetime.now().strftime('%Y-%m-%d')
    row = get_quota_record_db(user_id)
    
    if row:
        _, _, _, _, last_reset = row
        if last_reset != today_str:
            update_quota_counts_db(user_id, 0, 0, today_str)

def can_user_search(user_id):
    """Validates if a user has remaining search quota for the day."""
    role = get_user_role_db(user_id)
    if role in ['Admin', 'Owner']:
        return True  # Unlimited access
        
    check_and_reset_quota(user_id)
    row = get_quota_record_db(user_id)
    if not row:
        return True
        
    searches_used, searches_limit, _, _, _ = row
    return searches_used < searches_limit

def can_user_request(user_id):
    """Validates if a user has remaining request quota for the day."""
    role = get_user_role_db(user_id)
    if role in ['Admin', 'Owner']:
        return True  # Unlimited access
        
    check_and_reset_quota(user_id)
    row = get_quota_record_db(user_id)
    if not row:
        return True
        
    _, _, requests_used, requests_limit, _ = row
    return requests_used < requests_limit

def deduct_search_quota(user_id):
    """Deducts 1 search allowance ONLY after a successful search."""
    role = get_user_role_db(user_id)
    if role in ['Admin', 'Owner']:
        return  # Unlimited users do not consume quota
    increment_search_used_db(user_id)

def deduct_request_quota(user_id):
    """Deducts 1 request allowance ONLY after a successful request submission."""
    role = get_user_role_db(user_id)
    if role in ['Admin', 'Owner']:
        return  # Unlimited users do not consume quota
    increment_request_used_db(user_id)

def get_user_quota_summary(user_id):
    """Retrieves and formats the user's role and remaining quotas for the /quota command."""
    check_and_reset_quota(user_id)
    role = get_user_role_db(user_id)
    row = get_quota_record_db(user_id)
    
    if role in ['Admin', 'Owner']:
        return {
            "role": role,
            "unlimited": True,
            "searches_left": "Unlimited",
            "searches_limit": "Unlimited",
            "requests_left": "Unlimited",
            "requests_limit": "Unlimited"
        }
        
    if row:
        searches_used, searches_limit, requests_used, requests_limit, _ = row
        searches_left = max(0, searches_limit - searches_used)
        requests_left = max(0, requests_limit - requests_used)
        return {
            "role": role,
            "unlimited": False,
            "searches_left": searches_left,
            "searches_limit": searches_limit,
            "requests_left": requests_left,
            "requests_limit": requests_limit
        }
    return None

def gift_quota(admin_user_id, target_user_id, search_bonus=0, request_bonus=0):
    """Allows Admins or Owners to increase a target user's quota limits via /gift <n>."""
    admin_role = get_user_role_db(admin_user_id)
    if admin_role not in ['Admin', 'Owner']:
        return False, "❌ You do not have permission to use the gift command."
        
    add_quota_limits_db(target_user_id, search_bonus, request_bonus)
    return True, f"🎁 Successfully added +{search_bonus} search limit and +{request_bonus} request limit to user `{target_user_id}`."
