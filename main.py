import json
import requests
import time
import os
import sys

CLOUDFLARE_ZONE_ID = sys.argv[1]
CLOUDFLARE_EMAIL = sys.argv[2]
CLOUDFLARE_API_KEY = sys.argv[3]
ABUSEIPDB_API_KEY = sys.argv[4]

PAYLOAD={
  "query": """query ListFirewallEvents($zoneTag: string, $filter: FirewallEventsAdaptiveFilter_InputObject) {
    viewer {
      zones(filter: { zoneTag: $zoneTag }) {
        firewallEventsAdaptive(
          filter: $filter
          limit: 1000
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
  }""",
  "variables": {
    "zoneTag": CLOUDFLARE_ZONE_ID,
    "filter": {
      "datetime_geq": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.localtime(time.time()-60*60*8-60*60*4)),
      "datetime_leq": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.localtime(time.time()-60*60*8)),
      # "OR":[{"action": "block"}, {"action": "managed_challenge"}, {"action": "jschallenge"}],
      "AND":[
          {"action_neq": "allow"},
          {"action_neq": "skip"},
          {"action_neq": "challenge_solved"},
          {"action_neq": "challenge_failed"},
          {"action_neq": "challenge_bypassed"},
          {"action_neq": "jschallenge_solved"},
          {"action_neq": "jschallenge_failed"},
          {"action_neq": "jschallenge_bypassed"},
          {"action_neq": "managed_challenge_skipped"},
          {"action_neq": "managed_challenge_non_interactive_solved"},
          {"action_neq": "managed_challenge_interactive_solved"},
          {"action_neq": "managed_challenge_bypassed"},
      ]
    }
  }
}
PAYLOAD = json.dumps(PAYLOAD)
headers={"Content-Type":"application/json","Authorization":"Bearer "+CLOUDFLARE_API_KEY,"X-Auth-Email":CLOUDFLARE_EMAIL}

ttl=60
def get_blocked_ip():
  global ttl
  ttl=ttl-1
  print("ttl:",ttl)
  if ttl<=0:
    return []
  try:
    r=requests.post("https://api.cloudflare.com/client/v4/graphql/",headers=headers,data=PAYLOAD)
    if str(type(r.json())) == "<class 'NoneType'>":
      get_blocked_ip()
    else:
      return r.json()
  except Exception as e:
    get_blocked_ip()

def get_comment(it):
  return f"""IP:{it['clientIP']} [Country: {it['clientCountryName']}] triggered Cloudflare WAF ({it['source']}).
  Action: {it['action']}
  ASN: {it['clientAsn']}
  Protocol: {it['clientRequestHTTPProtocol']} (method {it['clientRequestHTTPMethodName']})
  Endpoint: {it['clientRequestPath']}{it['clientRequestQuery']}
  Time: {it['datetime']}
  User-Agent: {it['userAgent']}
  Report generated by CFWAF2AbuseIPDB.
  """

def report_bad_ip(it):
  try:
    url = 'https://api.abuseipdb.com/api/v2/report'
    params = {
      'ip': it['clientIP'],
      'categories': '13,21',
      'comment': get_comment(it)
    }
    headers = {
      'Accept': 'application/json',
      'Key': ABUSEIPDB_API_KEY
    }
    r=requests.post(url=url, headers=headers, params=params)
    if r.status_code==200:
      print("Reported IP:", it['clientIP'])
    else:
      if r.status_code==429:
        print("Error while reporting IP (429): ", it['clientIP'])
      else:
        print("Error status:", r.status_code)
    decodedResponse = json.loads(r.text)
    print(json.dumps(decodedResponse, sort_keys=True, indent=4))
  except Exception as e:
    print("error:",e)

# 排除配置错误的规则
excepted_ruleId = ["9b9dc6522cb14b0e98e4f841e8242abd"]

print("==================== Start ====================")
# print(str(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()-60*60*8))))
a=get_blocked_ip()
print(str(type(a)))
if str(type(a)) == "<class 'dict'>" and len(a)>0:
  ip_bad_list=a["data"]["viewer"]["zones"][0]["firewallEventsAdaptive"]
  print("Bad IP to report:" + str(len(ip_bad_list)))
  
  reported_ip_list=[]
  for i in ip_bad_list:
    if i['ruleId'] not in excepted_ruleId:
      if i['clientIP'] not in reported_ip_list:
        report_bad_ip(i)
        reported_ip_list.append(i['clientIP'])

  print("Reported IP:" + str(len(reported_ip_list)))
print("==================== End ====================")
