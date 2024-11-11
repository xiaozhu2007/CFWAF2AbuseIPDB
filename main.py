import json
import requests
import time
import sys
import random
from typing import Dict

# 常量定义
CLOUDFLARE_ZONE_ID = sys.argv[1]
CLOUDFLARE_EMAIL = sys.argv[2]
CLOUDFLARE_API_KEY = sys.argv[3]
ABUSEIPDB_API_KEYS = sys.argv[4]

# GraphQL 查询
QUERY = """
query ListFirewallEvents($zoneTag: string, $filter: FirewallEventsAdaptiveFilter_InputObject) {
  viewer {
    zones(filter: { zoneTag: $zoneTag }) {
      firewallEventsAdaptive(
        filter: $filter
        limit: 10000
        orderBy: [datetime_DESC]
      ) {
        action
        clientASNDescription
        clientAsn
        clientCountryName
        clientIP
        clientRequestHTTPHost
        clientRequestHTTPMethodName
        clientRequestHTTPProtocol
        clientRequestPath
        clientRequestQuery
        datetime
        rayName
        ruleId
        source
        userAgent
      }
    }
  }
}
"""

def prepare_query_variables() -> dict:
    return {
        "zoneTag": CLOUDFLARE_ZONE_ID,
        "filter": {
            "datetime_geq": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.localtime(time.time() - 60 * 60 * 4)),
            "datetime_leq": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.localtime(time.time())),
            "AND": [{"action_neq": action} for action in ["allow", "skip", "challenge_solved", "challenge_failed", "challenge_bypassed", "jschallenge_solved", "jschallenge_failed", "jschallenge_bypassed", "managed_challenge_skipped", "managed_challenge_non_interactive_solved", "managed_challenge_interactive_solved", "managed_challenge_bypassed"]],
        },
    }

def fetch_blocked_ips() -> dict:
    payload = {"query": QUERY, "variables": prepare_query_variables()}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CLOUDFLARE_API_KEY}",
        "X-Auth-Email": CLOUDFLARE_EMAIL,
    }
    response = requests.post("https://api.cloudflare.com/client/v4/graphql/", headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

def generate_comment(event: Dict) -> str:
    return f"""
IP: {event['clientIP']} [Country: {event['clientCountryName']}] triggered WAF ({event['source']}).
Action: {event['action']}
ASN: {event['clientAsn']} ({event['clientASNDescription']})
Protocol: {event['clientRequestHTTPProtocol']} (method {event['clientRequestHTTPMethodName']})
Endpoint: {event['clientRequestPath']}{event['clientRequestQuery']}
Time: {event['datetime']}
User Agent: {event['userAgent']}
Report generated by CFWAF2AbuseIPDB(https://github.com/xiaozhu2007/CFWAF2AbuseIPDB).
"""

def report_ip_to_abuseipdb(event: Dict):
    categories = "13,21"
    if event["source"] == "l7ddos":
        categories = "4,10,21"
    elif event["source"] == "firewallCustom":
        categories = "18,19,21"
    elif event["source"] == "asn":
        categories = "18,21"
    elif event["source"] == "securitylevel":
        categories = "21"
    elif event["clientCountryName"] == "T1":  # Tor
        categories = "4,9,10,13,18,19,21"

    headers = {
        "Accept": "application/json",
        "Key": random.choice(ABUSEIPDB_API_KEYS.split(","))
    }
    params = {
        "ip": event["clientIP"],
        "categories": categories,
        "comment": generate_comment(event),
    }
    response = requests.post("https://api.abuseipdb.com/api/v2/report", headers=headers, params=params)
    if response.status_code == 200:
        print(f"[DEBUG] Reported IP: {event['clientIP']} scores {response.json()['data']['abuseConfidenceScore']}")
    elif response.status_code == 429:
        print(f"Error while reporting IP (429): {event['clientIP']}")
    else:
        print(f"Error status: {response.status_code}")

def main():
    excluded_rule_ids = ["9b9dc6522cb14b0e98e4f841e8242abd"]
    try:
        blocked_ips_response = fetch_blocked_ips()
        ip_events = blocked_ips_response["data"]["viewer"]["zones"][0]["firewallEventsAdaptive"]
        print(f"[DEBUG] Bad IP num to report: {len(ip_events)}")
        reported_ips = set()
        for event in ip_events:
            if event["ruleId"] not in excluded_rule_ids and event["clientIP"] not in reported_ips:
                report_ip_to_abuseipdb(event)
                reported_ips.add(event["clientIP"])
        print(f"Reported IP num: {len(reported_ips)}")
    except requests.RequestException as e:
        print(f"Request error: {e}")
    except KeyError as e:
        print(f"Data structure error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
