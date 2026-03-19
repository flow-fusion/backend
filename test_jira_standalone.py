#!/usr/bin/env python3
"""
FlowFusion Jira Connection Test

Tests Jira connection without database/redis dependencies.
Automatically loads .env file.

Usage:
    python test_jira_only.py
"""

import sys
import os

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Loaded .env file")
except ImportError:
    print("⚠️  python-dotenv not installed, using environment variables only")


def print_header(text: str):
    """Print formatted header."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_result(name: str, success: bool, message: str = ""):
    """Print test result."""
    status = "✅ PASS" if success else "❌ FAIL"
    msg = f" - {message}" if message else ""
    print(f"{status}: {name}{msg}")


def test_jira_connection():
    """Test Jira connection."""
    print_header("Jira Connection Test")
    
    # Check environment variables
    jira_url = os.environ.get("JIRA_URL", "")
    jira_email = os.environ.get("JIRA_EMAIL", "")
    jira_token = os.environ.get("JIRA_TOKEN", "")
    
    if not jira_url:
        print_result("Configuration", False, "JIRA_URL not set")
        return False
    
    if not jira_email:
        print_result("Configuration", False, "JIRA_EMAIL not set")
        return False
    
    if not jira_token:
        print_result("Configuration", False, "JIRA_TOKEN not set")
        return False
    
    print_result("Configuration", True, f"URL: {jira_url}")
    print(f"  Email: {jira_email}")
    print(f"  Token: {jira_token[:10]}... (hidden)")
    
    # Test connection
    try:
        from app.jira_integration.config import JiraConfig
        from app.jira_integration.jira_client import JiraClient
        
        # Check if Bearer auth should be used
        use_bearer = os.environ.get("JIRA_USE_BEARER_AUTH", "").lower() == "true"
        
        config = JiraConfig(
            url=jira_url,
            email=jira_email,
            token=jira_token
        )
        
        client = JiraClient(config, use_bearer_auth=use_bearer)
        
        # Try to get current user info
        print(f"\nTesting connection to {jira_url}...")
        print("Checking current user...")
        
        myself = client._request("GET", "myself")
        display_name = myself.get("displayName", "Unknown")
        email = myself.get("emailAddress", "Unknown")
        print(f"  ✅ Connected as: {display_name} ({email})")
        
        # Try to get a test issue
        print(f"\nChecking access to TEST-1...")
        try:
            issue = client.get_issue("TEST-1")
            summary = issue.get("fields", {}).get("summary", "Unknown")
            print_result("Jira API", True, f"Found TEST-1: {summary}")
            
            # Try to get transitions
            transitions = client.get_transitions("TEST-1")
            print(f"  Available transitions: {len(transitions)}")
            for t in transitions[:3]:
                print(f"    - {t.get('name')}")
            
            return True
            
        except Exception as e:
            error_str = str(e)
            if "404" in error_str:
                print_result("Jira API", True, "Connected! (TEST-1 not found)")
                print(f"\n💡 Tip: Create issue TEST-1 or use existing issue key")
                return True
            elif "403" in error_str:
                print_result("Jira API", False, "No permission for TEST-1")
                print(f"\n💡 Check your Jira permissions")
                return None
            else:
                print_result("Jira API", False, error_str)
                return False
        
    except Exception as e:
        print_result("Jira Client", False, str(e))
        return False


def test_jira_posting():
    """Test posting comment to Jira."""
    print_header("Jira Posting Test (Optional)")
    
    jira_url = os.environ.get("JIRA_URL", "")
    jira_email = os.environ.get("JIRA_EMAIL", "")
    jira_token = os.environ.get("JIRA_TOKEN", "")
    
    if not jira_token:
        print_result("Jira Posting", False, "JIRA_TOKEN not set - skipping")
        return None
    
    try:
        from app.jira_integration.config import JiraConfig
        from app.jira_integration.jira_client import JiraClient
        
        config = JiraConfig(
            url=jira_url,
            email=jira_email,
            token=jira_token
        )
        
        client = JiraClient(config)
        
        # Test comment
        test_comment = """🤖 FlowFusion Test Comment

This is a test comment from FlowFusion integration.

If you see this, the Jira integration is working correctly!
"""
        
        print("Attempting to post test comment to TEST-1...")
        
        result = client.add_comment("TEST-1", test_comment)
        
        if result:
            comment_id = result.get("id", "unknown")
            print_result("Jira Posting", True, f"Comment posted! ID: {comment_id}")
            return True
        else:
            print_result("Jira Posting", False, "Comment already exists (idempotent)")
            return None
            
    except Exception as e:
        error_str = str(e)
        if "404" in error_str:
            print_result("Jira Posting", False, "Issue TEST-1 not found")
            return None
        elif "401" in error_str or "403" in error_str:
            print_result("Jira Posting", False, "Authentication/Permission failed")
            return False
        else:
            print_result("Jira Posting", False, error_str)
            return False


def main():
    """Run Jira tests."""
    print("\n")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║         FlowFusion Jira Integration Test                 ║")
    print("╚══════════════════════════════════════════════════════════╝")
    
    # Test 1: Connection
    connection_ok = test_jira_connection()
    
    # Test 2: Posting (only if connection works)
    posting_ok = None
    if connection_ok:
        posting_ok = test_jira_posting()
    
    # Summary
    print_header("Test Summary")
    
    tests = [
        ("Jira Connection", connection_ok),
        ("Jira Posting", posting_ok if posting_ok is not None else True),
    ]
    
    passed = sum(1 for _, v in tests if v)
    total = len(tests)
    
    for name, result in tests:
        status = "✅" if result else "❌"
        print(f"{status} {name}: {'PASS' if result else 'FAIL/SKIP'}")
    
    print("\n" + "-" * 60)
    print(f"Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 Jira integration is working!")
        print("\nNext steps:")
        print("  1. Start PostgreSQL: docker-compose up -d postgres")
        print("  2. Start Redis: docker-compose up -d redis")
        print("  3. Run full test: python test_quick.py")
    else:
        print("\n⚠️  Jira integration has issues.")
        print("\nCommon fixes:")
        print("  - Check JIRA_URL is correct")
        print("  - Check JIRA_EMAIL is your Jira username")
        print("  - Check JIRA_TOKEN is a valid Personal Access Token")
        print("  - Make sure you have access to project TEST")
    
    print("\n")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
