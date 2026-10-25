from modules.database.user_db import (
    record_referral_db,
    add_quota_limits_db,
    get_referred_users_db
)

def process_referral(referrer_id, new_user_id):
    """
    Processes a referral when a new user starts the bot via a referral link.
    Awards +10 search and +10 request limits to BOTH the referrer and the new user.
    """
    # 1. Prevent self-referral
    if referrer_id == new_user_id:
        return False, "⚠️ You cannot refer yourself."
        
    # 2. Attempt to record the referral in the database 
    # (returns False if the new user has already claimed a referral bonus)
    success = record_referral_db(referrer_id, new_user_id)
    if not success:
        return False, "⚠️ You have already claimed a referral bonus."
        
    # 3. Reward the Referrer (+10 searches, +10 requests)
    add_quota_limits_db(referrer_id, search_bonus=10, request_bonus=10)
    
    # 4. Reward the New User (+10 searches, +10 requests)
    add_quota_limits_db(new_user_id, search_bonus=10, request_bonus=10)
    
    return True, "🎉 Referral successful! Both you and your referrer received +10 search and +10 request allowance bonuses."

def get_user_referral_stats(user_id):
    """Fetches total invite count and details of invited users for a given user ID."""
    referred_rows = get_referred_users_db(user_id)
    total_invites = len(referred_rows)
    return {
        "total_invites": total_invites,
        "referred_list": referred_rows
    }
